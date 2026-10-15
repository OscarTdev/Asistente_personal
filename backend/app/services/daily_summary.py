"""Resumen diario proactivo (adendo: el módulo que crea hábito).

Cada mañana el bot le escribe al dueño con lo esencial del día:
- Recordatorios de hoy (agenda)
- Cotizaciones enviadas sin respuesta (seguimiento pendiente)
- Pagos vencidos (cobro de cartera)

Genera el texto SIN LLM: son queries simples sobre datos que ya existen.
El mensaje llega por WhatsApp — el dueño abre el chat y ya sabe su día.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contact, Conversation, Message, Quote, Reminder, Tenant, TenantModule

logger = logging.getLogger(__name__)


async def _send_to_owner(
    db: AsyncSession,
    *,
    tenant: Tenant,
    channel,
    text: str,
) -> None:
    """Envía el resumen al WhatsApp del dueño y lo persiste."""
    if not tenant.wa_id:
        logger.warning("Resumen diario: %s sin WhatsApp — se omite", tenant.slug)
        return

    conversation = (
        await db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant.id,
                Conversation.contact_id.is_not(None),
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
            .limit(1)
        )
    ).scalar_one_or_none()
    if conversation is None:
        return

    await channel.send_text(tenant.wa_id, text)
    db.add(
        Message(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            direction="out",
            type="text",
            content=text,
            whatsapp_message_id=f"daily-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{tenant.slug}",
            status="sent",
        )
    )
    await db.commit()


async def generate_daily_summary(db: AsyncSession, *, tenant: Tenant) -> str:
    """Arma el texto del resumen con los datos reales del día.

    Sin LLM: queries directas que el dueño puede verificar.
    """

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    lines: list[str] = []

    # 1) Recordatorios de hoy
    reminders = (
        (
            await db.execute(
                select(Reminder)
                .where(
                    Reminder.tenant_id == tenant.id,
                    Reminder.status == "pending",
                    Reminder.remind_at >= today_start,
                    Reminder.remind_at < today_end,
                )
                .order_by(Reminder.remind_at.asc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    if reminders:
        lines.append("📅 **Hoy tienes:**")
        for r in reminders:
            hora = r.remind_at.strftime("%I:%M %p").lstrip("0")
            lines.append(f"   • {hora} — {r.content}")

    # 2) Cotizaciones sin respuesta (seguimiento)
    pending_quotes = (
        (
            await db.execute(
                select(Quote)
                .where(
                    Quote.tenant_id == tenant.id,
                    Quote.status == "sent",
                    Quote.created_at >= now - timedelta(days=15),
                )
                .order_by(Quote.created_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    if pending_quotes:
        lines.append("")
        lines.append(f"📄 **{len(pending_quotes)} cotizaciones esperan respuesta:**")
        for q in pending_quotes:
            contacto = ""
            if q.contact_id:
                c = (
                    await db.execute(
                        select(Contact).where(Contact.id == q.contact_id)
                    )
                ).scalar_one_or_none()
                contacto = f" — {c.name}" if c and c.name else ""
            lines.append(f"   • ${int(q.total):,} {contacto}")

    # 3) Recordatorios vencidos (no atendidos ayer)
    overdue = (
        (
            await db.execute(
                select(Reminder)
                .where(
                    Reminder.tenant_id == tenant.id,
                    Reminder.status == "pending",
                    Reminder.remind_at < today_start,
                )
                .order_by(Reminder.remind_at.asc())
                .limit(3)
            )
        )
        .scalars()
        .all()
    )
    if overdue:
        lines.append("")
        lines.append(f"⚠️ **{len(overdue)} pendientes de días anteriores**")

    if not lines:
        lines.append(
            "☀️ Buenos días, {bot}. Hoy no tienes nada pendiente — "
            "aprovecha para prospectar."
        )

    return "\n".join(lines)


async def send_daily_summaries(db: AsyncSession, *, channel) -> int:
    """Envía el resumen a todos los negocios con el módulo activo.

    Se llama desde el ciclo de main.py una vez al día (mañana, 7-8am UTC-5).
    """
    # Solo los que tienen daily_summary encendido
    enabled = (
        (
            await db.execute(
                select(TenantModule.tenant_id).where(
                    TenantModule.module_key == "daily_summary",
                    TenantModule.is_enabled.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    if not enabled:
        return 0

    sent = 0
    for tenant_id in enabled:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        if tenant is None or not tenant.is_active or not tenant.wa_id:
            continue

        text = await generate_daily_summary(db, tenant=tenant)
        try:
            await _send_to_owner(db, tenant=tenant, channel=channel, text=text)
            sent += 1
            logger.info("Resumen diario enviado a %s", tenant.slug)
        except Exception:
            logger.exception("No se pudo enviar el resumen diario a %s", tenant.slug)

    return sent
