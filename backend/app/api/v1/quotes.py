"""Router para cotizaciones, ítems, extracción con IA y generación de PDF."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Contact, QuoteItem, Tenant, TenantBranding, User
from app.schemas.quotes import (
    ExtractRequest,
    ExtractResponse,
    QuoteCreate,
    QuoteDetail,
    QuoteItemCreate,
    QuoteItemOut,
    QuoteItemUpdate,
    QuoteOut,
    QuotePage,
    QuoteUpdate,
)
from app.services import ai_extraction as ai_service
from app.services import pdf_generator as pdf_service
from app.services import quotes as quotes_service
from app.services.quotes import CrossTenantReference
from app.services.usage import log_service_usage

router = APIRouter()


@router.get("", response_model=QuotePage)
async def list_quotes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuotePage:
    """Lista las cotizaciones del tenant."""
    return await quotes_service.list_quotes(
        db=db,
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=limit,
        status=status_filter,
    )


@router.post("", response_model=QuoteDetail, status_code=status.HTTP_201_CREATED)
async def create_quote(
    body: QuoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuoteDetail:
    """Crea una nueva cotización con ítems opcionales."""
    try:
        quote = await quotes_service.create_quote(
            db=db,
            tenant_id=current_user.tenant_id,
            data=body,
        )
    except CrossTenantReference as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    await log_service_usage(
        db,
        tenant_id=current_user.tenant_id,
        module_key="quoter",
        kind="quote_created",
        contact_id=body.contact_id,
    )
    return quote


@router.post("/extract", response_model=ExtractResponse)
async def extract_items(
    body: ExtractRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExtractResponse:
    """Extrae materiales/servicios con IA (OpenRouter/NVIDIA) y los busca en el catálogo."""
    result = await ai_service.extract_items_from_text(
        db=db,
        tenant_id=current_user.tenant_id,
        text=body.text,
    )
    await log_service_usage(
        db,
        tenant_id=current_user.tenant_id,
        module_key="quoter",
        kind="extraction",
    )
    return result


@router.get("/{quote_id}", response_model=QuoteDetail)
async def get_quote(
    quote_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuoteDetail:
    """Obtiene una cotización con todos sus ítems."""
    quote = await quotes_service.get_quote(
        db=db,
        tenant_id=current_user.tenant_id,
        quote_id=quote_id,
    )
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cotización no encontrada",
        )
    return quote


@router.put("/{quote_id}", response_model=QuoteOut)
async def update_quote(
    quote_id: UUID,
    body: QuoteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuoteOut:
    """Actualiza datos generales de una cotización (estado, notas, vigencia)."""
    quote = await quotes_service.get_quote_raw(
        db=db,
        tenant_id=current_user.tenant_id,
        quote_id=quote_id,
    )
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cotización no encontrada",
        )
    updated = await quotes_service.update_quote(db=db, quote=quote, data=body)
    return QuoteOut.model_validate(updated)


@router.post("/{quote_id}/items", response_model=QuoteItemOut, status_code=status.HTTP_201_CREATED)
async def add_item(
    quote_id: UUID,
    body: QuoteItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuoteItemOut:
    """Agrega un ítem a la cotización y recalcula su total."""
    quote = await quotes_service.get_quote_raw(
        db=db,
        tenant_id=current_user.tenant_id,
        quote_id=quote_id,
    )
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cotización no encontrada",
        )
    try:
        item = await quotes_service.add_quote_item(
            db=db,
            tenant_id=current_user.tenant_id,
            quote=quote,
            data=body,
        )
    except CrossTenantReference as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return QuoteItemOut.model_validate(item)


@router.put("/{quote_id}/items/{item_id}", response_model=QuoteItemOut)
async def update_item(
    quote_id: UUID,
    item_id: UUID,
    body: QuoteItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuoteItemOut:
    """Modifica un ítem de la cotización y recalcula el total."""
    quote = await quotes_service.get_quote_raw(
        db=db,
        tenant_id=current_user.tenant_id,
        quote_id=quote_id,
    )
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cotización no encontrada",
        )
    item = await quotes_service.get_quote_item(
        db=db,
        tenant_id=current_user.tenant_id,
        quote_id=quote_id,
        item_id=item_id,
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ítem no encontrado en esta cotización",
        )
    updated_item = await quotes_service.update_quote_item(
        db=db,
        quote=quote,
        item=item,
        data=body,
    )
    return QuoteItemOut.model_validate(updated_item)


@router.delete("/{quote_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    quote_id: UUID,
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Elimina un ítem de la cotización y recalcula el total."""
    quote = await quotes_service.get_quote_raw(
        db=db,
        tenant_id=current_user.tenant_id,
        quote_id=quote_id,
    )
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cotización no encontrada",
        )
    item = await quotes_service.get_quote_item(
        db=db,
        tenant_id=current_user.tenant_id,
        quote_id=quote_id,
        item_id=item_id,
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ítem no encontrado en esta cotización",
        )
    await quotes_service.delete_quote_item(db=db, quote=quote, item=item)


@router.get("/{quote_id}/pdf")
async def download_quote_pdf(
    quote_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Genera y descarga la cotización en formato PDF."""
    quote = await quotes_service.get_quote_raw(
        db=db,
        tenant_id=current_user.tenant_id,
        quote_id=quote_id,
    )
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cotización no encontrada",
        )

    # Cargar ítems
    items_stmt = (
        select(QuoteItem)
        .where(QuoteItem.quote_id == quote.id)
        .order_by(QuoteItem.position, QuoteItem.created_at)
    )
    items = list((await db.execute(items_stmt)).scalars().all())

    # Cargar Tenant
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one_or_none()

    # Cargar Contacto si existe
    contact = None
    if quote.contact_id:
        contact = (
            await db.execute(select(Contact).where(Contact.id == quote.contact_id))
        ).scalar_one_or_none()

    # Cargar branding para el logo del encabezado
    branding = (
        await db.execute(
            select(TenantBranding).where(
                TenantBranding.tenant_id == current_user.tenant_id
            )
        )
    ).scalar_one_or_none()

    pdf_buffer = pdf_service.generate_quote_pdf(
        quote=quote,
        items=items,
        tenant=tenant,
        contact=contact,
        logo_bytes=branding.logo_bytes if branding else None,
    )
    await log_service_usage(
        db,
        tenant_id=current_user.tenant_id,
        module_key="quoter",
        kind="pdf",
        contact_id=quote.contact_id,
    )

    filename = f"cotizacion_{str(quote.id)[:8]}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
