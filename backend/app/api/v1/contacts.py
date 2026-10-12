"""Router de clientes (contactos de WhatsApp) del panel."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas.contacts import ContactDetail, ContactOut, ContactPage, ContactUpdate
from app.services import contacts as contacts_service

router = APIRouter()


@router.get("", response_model=ContactPage)
async def list_contacts(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    search: str | None = Query(None, max_length=100),
    active_only: bool = Query(True),
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
    )
    return ContactPage(items=items, total=total, skip=skip, limit=limit)


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
