"""Mantenimiento preventivo: avisos periódicos a los clientes (spec §13).

El técnico registra «limpiar el aire cada 6 meses para Juliana» y el bot
le escribe a Juliana (y al dueño) cuando toca. Genera ingresos recurrentes
sin que el técnico tenga que acordarse de nada.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact, Maintenance, Tenant

logger = logging(logging.NOTSET) if False else logging.getLogger(__name__)

_FREQUENCY_DAYS = {
    "mensual": 30,
    "bimestral": 60,
    "trimestral": 90,
    "cuatrimestral": 120,
    "semestral": 180,
    "anual": 365,
    "cada 3 meses": 90,
    "cada 6 meses": 180,
    "cada 12 meses": 365,
    "cada mes": 30,
    "cada semana": 7,
    "semanal": 7,
}


def parse_frequency_days(text: str) -> int | None:
    """Detecta la frecuencia en días desde texto natural."""
    lowered = text.lower()
    for phrase, days in _FREQUENCY_DAYS.items():
        if phrase in lowered:
            return days
    # Buscar "cada N meses/semanas/días"
    import re
    pattern = r"cada\s+(\d+)\s*(día|dias|días|semana|semanas|mes|meses|año|años|a|an)"
    for match in re.finditer(pattern, lowered):
        num = int(match.group(1))
        unit = match.group(2)
        if "semana" in unit:
            return num * 7
        if "mes" in unit:
            return num * 30
        if "año" in unit or unit in ("a", "an"):
            return num * 365
        return num
    return None


async def schedule_maintenance(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    description: str,
    frequency_days: int,
    next_due: datetime | None = None,
) -> Maintenance:
    """Programa un mantenimiento recurrente para un cliente."""
    if next_due is None:
        next_due = datetime.now(UTC) + timedelta(days=frequency_days)
    m = Maintenance(
        tenant_id=tenant_id,
        contact_id=contact_id,
        description=description.strip()[:500],
        frequency_days=frequency_days,
        next_due=next_due,
        status="active",
    )
    db.add(m)
    await db.commit()
    logger.info(
        "Mantenimiento programado: %s cada %d días (próximo %s)",
        description[:50], frequency_days, next_due.date(),
    )
    return m


async def due_maintenances(db: AsyncSession) -> list[Maintenance]:
    """Mantenimientos activos cuya fecha llegó."""
    return list(
        (
            await db.execute(
                select(Maintenance)
                .where(
                    Maintenance.status == "active",
                    Maintenance.next_due <= datetime.now(UTC),
                )
                .order_by(Maintenance.next_due.asc())
                .limit(20)
            )
        ).scalars().all()
    )


async def mark_maintenance_sent(db: AsyncSession, m: Maintenance) -> None:
    """Marca el mantenimiento como enviado y programa el siguiente."""
    m.last_notified_at = datetime.now(UTC)
    m.next_due = datetime.now(UTC) + timedelta(days=m.frequency_days)
    await db.commit()


async def send_maintenance_reminders(
    db: AsyncSession,
    *,
    channel,
) -> int:
    """Envía los mantenimientos vencidos por WhatsApp (al dueño y al cliente)."""
    sent = 0
    for m in await due_maintenances(db):
        try:
            tenant = (
                await db.execute(
                    select(Tenant).where(Tenant.id == m.tenant_id)
                )
            ).scalar_one()
            contact = (
                await db.execute(
                    select(Contact).where(Contact.id == m.contact_id)
                )
            ).scalar_one_or_none()
            if contact is None:
                continue

            # Avisar al CLIENTE
            await channel.send_text(
                contact.wa_id,
                f"¡Hola {contact.name or ''}! {tenant.name} te recuerda que "
                f"tocan las fechas de: {m.description}. "
                "¿Quieres agendar la visita? ¡Responde y coordinamos!",
            )

            # Avisar al DUEÑO si tiene WhatsApp registrado
            if tenant.wa_id:
                owner_contact = (
                    await db.execute(
                        select(Contact).where(
                            Contact.tenant_id == tenant.id,
                            Contact.wa_id == tenant.wa_id,
                        )
                    )
                ).scalar_one_or_none()
                if owner_contact:
                    await channel.send_text(
                        tenant.wa_id,
                        f"🔧 Mantenimiento de {contact.name or contact.wa_id}: "
                        f"«{m.description}». Ya le avisé al cliente.",
                    )

            await mark_maintenance_sent(db, m)
            sent += 1
        except Exception:
            logger.exception("No se pudo enviar el mantenimiento %s", m.id)
    return sent
