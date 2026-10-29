"""Obras (bitácora de obra): gestión completa desde el panel.

El bot ya abre obras, registra avances y las cierra por chat. Este router
permite lo mismo desde el panel y además VER y EDITAR: la obra es el
título principal y sus registros diarios cuelgan de ella.

Todos los queries son por tenant (del token, nunca del request). Un
contacto u obra de otro negocio responde 404, igual que si no existiera.
"""

import logging
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Contact, User
from app.models.site_log import SiteLog
from app.models.site_log_entry import SiteLogEntry

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Esquemas ──────────────────────────────────────────────────────────────


class ObraEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    note: str
    entry_date: datetime
    created_at: datetime | None = None


class ObraOut(BaseModel):
    id: UUID
    contact_id: UUID
    contact_name: str | None = None
    contact_wa_id: str | None = None
    title: str
    status: str
    closed_at: datetime | None = None
    created_at: datetime | None = None
    entries_count: int = 0
    last_entry_at: datetime | None = None


class ObraDetailOut(ObraOut):
    entries: list[ObraEntryOut] = []


class ObraCreate(BaseModel):
    contact_id: UUID
    title: str = Field(min_length=1, max_length=300)


class ObraUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    status: Literal["open", "closed"] | None = None
    contact_id: UUID | None = None


class EntryCreate(BaseModel):
    note: str = Field(min_length=1, max_length=4000)
    entry_date: datetime | None = None


class EntryUpdate(BaseModel):
    note: str | None = Field(default=None, min_length=1, max_length=4000)
    entry_date: datetime | None = None


# ── Helpers ────────────────────────────────────────────────────────────────


async def _get_contact(db: AsyncSession, tenant_id: UUID, contact_id: UUID) -> Contact:
    contact = (
        await db.execute(
            select(Contact).where(
                Contact.id == contact_id, Contact.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contacto no encontrado")
    return contact


async def _get_site(db: AsyncSession, tenant_id: UUID, site_id: UUID) -> SiteLog:
    site = (
        await db.execute(
            select(SiteLog).where(SiteLog.id == site_id, SiteLog.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Obra no encontrada")
    return site


async def _get_entry(db: AsyncSession, site_id: UUID, entry_id: UUID) -> SiteLogEntry:
    entry = (
        await db.execute(
            select(SiteLogEntry).where(
                SiteLogEntry.id == entry_id, SiteLogEntry.site_id == site_id
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro no encontrado")
    return entry


async def _to_out(
    db: AsyncSession, tenant_id: UUID, sites: list[SiteLog]
) -> list[ObraOut]:
    """Obras con nombre del cliente y resumen de sus registros (2 queries)."""
    if not sites:
        return []
    site_ids = [s.id for s in sites]
    stats = {
        row.site_id: (row.n, row.last)
        for row in (
            await db.execute(
                select(
                    SiteLogEntry.site_id,
                    func.count(SiteLogEntry.id).label("n"),
                    func.max(SiteLogEntry.entry_date).label("last"),
                )
                .where(SiteLogEntry.site_id.in_(site_ids))
                .group_by(SiteLogEntry.site_id)
            )
        ).all()
    }
    contacts = {
        c.id: c
        for c in (
            await db.execute(
                select(Contact).where(
                    Contact.tenant_id == tenant_id,
                    Contact.id.in_({s.contact_id for s in sites}),
                )
            )
        )
        .scalars()
        .all()
    }
    result: list[ObraOut] = []
    for s in sites:
        contact = contacts.get(s.contact_id)
        count, last = stats.get(s.id, (0, None))
        result.append(
            ObraOut(
                id=s.id,
                contact_id=s.contact_id,
                contact_name=(contact.name or contact.wa_id) if contact else None,
                contact_wa_id=contact.wa_id if contact else None,
                title=s.title,
                status=s.status,
                closed_at=s.closed_at,
                created_at=s.created_at,
                entries_count=count,
                last_entry_at=last,
            )
        )
    return result


async def _detail(db: AsyncSession, tenant_id: UUID, site: SiteLog) -> ObraDetailOut:
    base = (await _to_out(db, tenant_id, [site]))[0]
    entries = (
        (
            await db.execute(
                select(SiteLogEntry)
                .where(SiteLogEntry.site_id == site.id)
                .order_by(SiteLogEntry.entry_date.desc(), SiteLogEntry.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return ObraDetailOut(
        **base.model_dump(),
        entries=[ObraEntryOut.model_validate(e) for e in entries],
    )


# ── Obras ──────────────────────────────────────────────────────────────────


@router.get("", response_model=list[ObraOut])
async def list_obras(
    estado: Literal["open", "closed", "all"] = "all",
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ObraOut]:
    """Obras del negocio: abiertas primero, las más recientes arriba."""
    stmt = select(SiteLog).where(SiteLog.tenant_id == user.tenant_id)
    if estado != "all":
        stmt = stmt.where(SiteLog.status == estado)
    if q and q.strip():
        stmt = stmt.where(SiteLog.title.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(
        (SiteLog.status == "open").desc(), SiteLog.created_at.desc()
    ).limit(limit)
    sites = list((await db.execute(stmt)).scalars().all())
    return await _to_out(db, user.tenant_id, sites)


@router.post("", response_model=ObraDetailOut, status_code=status.HTTP_201_CREATED)
async def create_obra(
    body: ObraCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ObraDetailOut:
    """Abre una obra para un cliente del negocio."""
    await _get_contact(db, user.tenant_id, body.contact_id)
    title = body.title.strip()
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El título está vacío")
    site = SiteLog(
        tenant_id=user.tenant_id,
        contact_id=body.contact_id,
        title=title,
        status="open",
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return await _detail(db, user.tenant_id, site)


@router.get("/{site_id}", response_model=ObraDetailOut)
async def get_obra(
    site_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ObraDetailOut:
    """Una obra con todos sus registros diarios."""
    site = await _get_site(db, user.tenant_id, site_id)
    return await _detail(db, user.tenant_id, site)


@router.patch("/{site_id}", response_model=ObraDetailOut)
async def update_obra(
    site_id: UUID,
    body: ObraUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ObraDetailOut:
    """Edita el título, el cliente o el estado (cerrar / reabrir)."""
    site = await _get_site(db, user.tenant_id, site_id)

    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "El título está vacío"
            )
        site.title = title
    if body.contact_id is not None:
        await _get_contact(db, user.tenant_id, body.contact_id)
        site.contact_id = body.contact_id
    if body.status is not None and body.status != site.status:
        site.status = body.status
        site.closed_at = datetime.now(UTC) if body.status == "closed" else None

    await db.commit()
    await db.refresh(site)
    return await _detail(db, user.tenant_id, site)


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_obra(
    site_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Borra la obra y sus registros (para cerrarla sin borrar, usa PATCH)."""
    site = await _get_site(db, user.tenant_id, site_id)
    await db.delete(site)
    await db.commit()


# ── Registros diarios ──────────────────────────────────────────────────────


@router.post(
    "/{site_id}/entries",
    response_model=ObraEntryOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_entry(
    site_id: UUID,
    body: EntryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ObraEntryOut:
    """Agrega un registro de avance a la obra (puede ser de una fecha pasada)."""
    site = await _get_site(db, user.tenant_id, site_id)
    note = body.note.strip()
    if not note:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El registro está vacío")
    entry = SiteLogEntry(
        site_id=site.id,
        note=note,
        entry_date=body.entry_date or datetime.now(UTC),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return ObraEntryOut.model_validate(entry)


@router.patch("/{site_id}/entries/{entry_id}", response_model=ObraEntryOut)
async def update_entry(
    site_id: UUID,
    entry_id: UUID,
    body: EntryUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ObraEntryOut:
    """Corrige el texto o la fecha de un registro."""
    site = await _get_site(db, user.tenant_id, site_id)
    entry = await _get_entry(db, site.id, entry_id)
    if body.note is not None:
        note = body.note.strip()
        if not note:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "El registro está vacío"
            )
        entry.note = note
    if body.entry_date is not None:
        entry.entry_date = body.entry_date
    await db.commit()
    await db.refresh(entry)
    return ObraEntryOut.model_validate(entry)


@router.delete(
    "/{site_id}/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_entry(
    site_id: UUID,
    entry_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    site = await _get_site(db, user.tenant_id, site_id)
    entry = await _get_entry(db, site.id, entry_id)
    await db.delete(entry)
    await db.commit()
