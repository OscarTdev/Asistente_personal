"""Motor de seguimiento de cotizaciones.

Detecta cotizaciones ENVIADAS sin respuesta del cliente y escribe por
WhatsApp: ronda 1 a los 3 días, ronda 2 (cierre) a los 7. Anti-spam:
una ronda por cotización (UNIQUE quote_id+round) y nunca se escribe a
quien ya respondió. El scheduler del panel y el programado comparten
esta misma pieza (futura migración a ARQ para escala).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import Channel
from app.core.config import get_settings
from app.models import Contact, FollowUp, Message, Quote, TenantModule
from app.services.usage import log_service_usage

if TYPE_CHECKING:
    from app.schemas.followup import FollowUpRunResult

logger = logging.getLogger(__name__)

_TEMPLATE_ROUND_1 = (
    "¡Hola{name_part}! Hace unos días te envié la cotización #{short_id}. "
    "¿Necesitas algún ajuste o tienes alguna duda? Quedo pendiente para ayudarte."
)
_TEMPLATE_ROUND_2 = (
    "¡Hola{name_part}! Tu cotización #{short_id} sigue vigente por unos días más. "
    "¿Te la reenvío o la dejamos para otro momento? Escríbeme y la activamos."
)
# Días mínimos entre la ronda 1 y la ronda 2 (no doble mensaje el mismo día)
_MIN_GAP_DAYS = 2


def _parse_round_days(raw: str) -> tuple[int, int]:
    parts = [int(piece.strip()) for piece in raw.split(",") if piece.strip()]
    if len(parts) < 2 or parts[0] >= parts[1]:
        return 3, 7
    return parts[0], parts[1]


async def tenants_with_service(db: AsyncSession) -> list[UUID]:
    """Tenants con el servicio de seguimiento encendido."""
    result = await db.execute(
        select(TenantModule.tenant_id).where(
            TenantModule.module_key == "follow_up",
            TenantModule.is_enabled.is_(True),
        )
    )
    return [row for row in result.scalars().all()]


async def run_followups(
    db: AsyncSession,
    *,
    tenant_ids: list[UUID] | None = None,
    channel: Channel | None = None,
) -> "FollowUpRunResult":
    """Ejecuta una ronda de seguimientos y devuelve el resumen."""
    from app.channels import get_channel
    from app.schemas.followup import FollowUpRunResult

    settings = get_settings()
    result = FollowUpRunResult(round1_sent=0, round2_sent=0, errors=0)

    if not settings.evolution_api_key:
        logger.info("Seguimiento omitido: canal de WhatsApp no configurado")
        return result

    if tenant_ids is None:
        tenant_ids = await tenants_with_service(db)
    if not tenant_ids:
        return result

    if channel is None:
        channel = get_channel("evolution")

    now = datetime.now(UTC)
    day_first, day_second = _parse_round_days(settings.followup_days)
    cutoff_first = now - timedelta(days=day_first)
    cutoff_second = now - timedelta(days=day_second)

    # Cotizaciones enviadas, con contacto, sin respuesta posterior del cliente
    reply_exists = exists(
        select(Message.id).where(
            Message.conversation_id == Quote.conversation_id,
            Message.direction == "in",
            Message.created_at > Quote.created_at,
        )
    )

    stmt = (
        select(Quote, Contact)
        .join(Contact, Quote.contact_id == Contact.id)
        .where(
            Quote.tenant_id.in_(tenant_ids),
            Quote.status == "sent",
            Quote.created_at <= cutoff_first,
            ~reply_exists,
        )
        .order_by(Quote.created_at.asc())
    )
    candidates = (await db.execute(stmt)).all()

    for quote, contact in candidates:
        existing = (
            await db.execute(
                select(FollowUp).where(FollowUp.quote_id == quote.id)
            )
        ).scalars().all()
        sent_rounds = {follow_up.round: follow_up for follow_up in existing}

        round_to_send = None
        message = None
        if 1 not in sent_rounds:
            round_to_send = 1
            message = _TEMPLATE_ROUND_1
        elif (
            2 not in sent_rounds
            and quote.created_at <= cutoff_second
            and (now - sent_rounds[1].created_at).days >= _MIN_GAP_DAYS
        ):
            round_to_send = 2
            message = _TEMPLATE_ROUND_2

        if round_to_send is None:
            continue

        name_part = f" {contact.name}" if contact.name else ""
        message = message.format(name_part=name_part, short_id=str(quote.id)[:8])

        try:
            await channel.send_text(contact.wa_id, message)
            db.add(
                FollowUp(
                    tenant_id=quote.tenant_id,
                    quote_id=quote.id,
                    contact_id=contact.id,
                    round=round_to_send,
                    message_sent=message,
                )
            )
            await db.commit()
            await log_service_usage(
                db,
                tenant_id=quote.tenant_id,
                module_key="follow_up",
                kind="followup",
                contact_id=contact.id,
            )
            if round_to_send == 1:
                result.round1_sent += 1
            else:
                result.round2_sent += 1
        except Exception:
            await db.rollback()
            result.errors += 1
            # Sin wa_id en logs (Ley 1581)
            logger.exception("Falló el seguimiento de la cotización %s", quote.id)

    return result
