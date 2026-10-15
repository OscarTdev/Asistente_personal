"""Router de clientes (contactos de WhatsApp) del panel."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas.contacts import (
    ContactDetail,
    ContactMessage,
    ContactMessagesPage,
    ContactNoteCreate,
    ContactNoteOut,
    ContactOut,
    ContactPage,
    ContactQuoteOut,
    ContactUpdate,
)
from app.services import contacts as contacts_service

router = APIRouter()


@router.get("", response_model=ContactPage)
async def list_contacts(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    search: str | None = Query(None, max_length=100),
    active_only: bool = Query(True),
    tag: str | None = Query(None, max_length=30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactPage:
    """Lista los clientes del asistente con su última interacción."""
    items, total = await contacts_service.list_contacts(
        db,
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=limit,
        search=search,
        active_only=active_only,
        tag=tag,
    )
    return ContactPage(items=items, total=total, skip=skip, limit=limit)


@router.get("/tags", response_model=list[str])
async def list_tags(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """Etiquetas distintas del negocio (para el filtro del listado)."""
    return await contacts_service.list_distinct_tags(
        db, tenant_id=current_user.tenant_id
    )


@router.get("/{contact_id}", response_model=ContactDetail)
async def get_contact(
    contact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactDetail:
    """Ficha del cliente con sus mensajes recientes."""
    detail = await contacts_service.get_contact(
        db, tenant_id=current_user.tenant_id, contact_id=contact_id
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )
    return detail


@router.get("/{contact_id}/messages", response_model=ContactMessagesPage)
async def list_contact_messages(
    contact_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactMessagesPage:
    """Historial de conversación del cliente (paginado, más reciente primero)."""
    result = await contacts_service.list_contact_messages(
        db,
        tenant_id=current_user.tenant_id,
        contact_id=contact_id,
        skip=skip,
        limit=limit,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )
    messages, total = result
    return ContactMessagesPage(
        items=[ContactMessage.model_validate(m) for m in messages],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{contact_id}/notes", response_model=list[ContactNoteOut])
async def list_contact_notes(
    contact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContactNoteOut]:
    """Notas del cliente (mini CRM), más recientes primero."""
    notes = await contacts_service.list_contact_notes(
        db, tenant_id=current_user.tenant_id, contact_id=contact_id
    )
    if notes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )
    return [ContactNoteOut.model_validate(n) for n in notes]


@router.post(
    "/{contact_id}/notes",
    response_model=ContactNoteOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_contact_note(
    contact_id: UUID,
    body: ContactNoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactNoteOut:
    """Agrega una nota al cliente (con fecha, visible en su ficha)."""
    note = await contacts_service.create_contact_note(
        db,
        tenant_id=current_user.tenant_id,
        contact_id=contact_id,
        content=body.content,
    )
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )
    return ContactNoteOut.model_validate(note)


@router.delete(
    "/{contact_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_contact_note(
    contact_id: UUID,
    note_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Borrado lógico de una nota del cliente (recuperable, spec §13)."""
    deleted = await contacts_service.delete_contact_note(
        db,
        tenant_id=current_user.tenant_id,
        contact_id=contact_id,
        note_id=note_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota no encontrada",
        )


@router.get("/{contact_id}/quotes", response_model=list[ContactQuoteOut])
async def list_contact_quotes(
    contact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContactQuoteOut]:
    """Cotizaciones del cliente (historial de la ficha)."""
    quotes = await contacts_service.list_contact_quotes(
        db, tenant_id=current_user.tenant_id, contact_id=contact_id
    )
    if quotes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )
    return [ContactQuoteOut.model_validate(q) for q in quotes]


@router.put("/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: UUID,
    body: ContactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactOut:
    """Actualiza nombre, notas o estado del cliente."""
    contact = await contacts_service.update_contact(
        db,
        tenant_id=current_user.tenant_id,
        contact_id=contact_id,
        data=body,
    )
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )
    return ContactOut.model_validate(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Retira al cliente (soft delete): sale del panel, conserva historial."""
    deleted = await contacts_service.deactivate_contact(
        db, tenant_id=current_user.tenant_id, contact_id=contact_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente no encontrado",
        )
