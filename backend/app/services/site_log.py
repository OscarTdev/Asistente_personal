"""Bitácora de obra: registro diario de avance con reporte al cliente (spec §13).

El técnico abre una obra, registra avances por chat (texto o voz) y al
cerrar genera un reporte. Conecta con inventario (qué materiales usó) y
rentabilidad (costo real vs lo cotizado).
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SiteLog, SiteLogEntry

logger = logging.getLogger(__name__)


async def open_site(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    title: str,
) -> SiteLog:
    """Abre una obra nueva para un cliente."""
    site = SiteLog(
        tenant_id=tenant_id,
        contact_id=contact_id,
        title=title.strip()[:200],
        status="open",
    )
    db.add(site)
    await db.commit()
    logger.info("Obra abierta: %s", site.title[:50])
    return site


async def add_entry(
    db: AsyncSession,
    *,
    site_id: UUID,
    note: str,
) -> SiteLogEntry:
    """Agrega un registro diario a la obra."""
    entry = SiteLogEntry(
        site_id=site_id,
        note=note.strip()[:2000],
    )
    db.add(entry)
    await db.commit()
    return entry


async def close_site(
    db: AsyncSession,
    site_id: UUID,
) -> SiteLog:
    """Cierra la obra."""
    site = (
        await db.execute(select(SiteLog).where(SiteLog.id == site_id))
    ).scalar_one()
    site.status = "closed"
    site.closed_at = datetime.now(UTC)
    await db.commit()
    return site


async def active_sites(
    db: AsyncSession,
    *,
    tenant_id: UUID,
) -> list[SiteLog]:
    """Obras abiertas del negocio."""
    return list(
        (
            await db.execute(
                select(SiteLog)
                .where(SiteLog.tenant_id == tenant_id, SiteLog.status == "open")
                .order_by(SiteLog.created_at.desc())
            )
        ).scalars().all()
    )


async def entries_of_site(
    db: AsyncSession,
    *,
    site_id: UUID,
) -> list[SiteLogEntry]:
    """Todos los registros de una obra, en orden cronológico."""
    return list(
        (
            await db.execute(
                select(SiteLogEntry)
                .where(SiteLogEntry.site_id == site_id)
                .order_by(SiteLogEntry.created_at.asc())
            )
        ).scalars().all()
    )


async def find_site_for_contact(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID,
) -> SiteLog | None:
    """La obra abierta más reciente de un contacto."""
    return (
        await db.execute(
            select(SiteLog)
            .where(
                SiteLog.tenant_id == tenant_id,
                SiteLog.contact_id == contact_id,
                SiteLog.status == "open",
            )
            .order_by(SiteLog.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
