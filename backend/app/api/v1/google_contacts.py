"""Contactos de Google en el CRM: estado de la conexión e importación."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import google_contacts, google_oauth

logger = logging.getLogger(__name__)
router = APIRouter()


class ContactsStatusOut(BaseModel):
    connected: bool
    contacts_permission: bool
    google_email: str | None = None


class ImportOut(BaseModel):
    total: int
    created: int
    updated: int
    unchanged: int
    skipped_no_phone: int


@router.get("/status", response_model=ContactsStatusOut)
async def contacts_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactsStatusOut:
    """¿Hay cuenta de Google conectada y con permiso de contactos?"""
    conn = await google_oauth.get_connection(db, tenant_id=user.tenant_id)
    if conn is None:
        return ContactsStatusOut(connected=False, contacts_permission=False)
    return ContactsStatusOut(
        connected=True,
        contacts_permission=google_contacts.CONTACTS_SCOPE in (conn.scopes or []),
        google_email=conn.google_email,
    )


@router.post("/import", response_model=ImportOut)
async def import_contacts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportOut:
    """Trae los contactos de Google al CRM (agrega nuevos, completa vacíos)."""
    try:
        result = await google_contacts.import_google_contacts(
            db, tenant_id=user.tenant_id
        )
    except (
        google_oauth.GoogleNotConnected,
        google_oauth.GoogleAuthError,
        google_contacts.GoogleContactsScopeMissing,
    ) as exc:
        # El dueño puede resolverlo reconectando su cuenta
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except google_contacts.GoogleContactsError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return ImportOut(
        total=result.total,
        created=result.created,
        updated=result.updated,
        unchanged=result.unchanged,
        skipped_no_phone=result.skipped_no_phone,
    )
