"""Métricas del asistente para el panel: clientes, cotizaciones y
servicios más demandados (interacciones por servicio)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.modules_registry import AVAILABLE_MODULES, module_dev_status
from app.models import Contact, Conversation, Message, Quote, ServiceUsage, TenantModule
from app.schemas.dashboard import (
    ContactsStats,
    DashboardStats,
    QuotesStats,
    ServiceStat,
)


async def compute_stats(db: AsyncSession, *, tenant_id: UUID, bot_name: str) -> DashboardStats:
    """Agrega todas las métricas del panel en una consulta lógica por grupo."""
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)

    # ── Clientes ────────────────────────────────────────────────────────────
    contacts_total = (
        await db.execute(
            select(func.count())
            .select_from(Contact)
            .where(Contact.tenant_id == tenant_id, Contact.is_active.is_(True))
        )
    ).scalar_one()

    active_7d = (
        await db.execute(
            select(func.count(func.distinct(Conversation.contact_id))).where(
                Conversation.tenant_id == tenant_id,
                Conversation.last_message_at >= week_ago,
            )
        )
    ).scalar_one()

    # ── Cotizaciones ─────────────────────────────────────────────────────────
    quotes_total = (
        await db.execute(
            select(func.count()).select_from(Quote).where(Quote.tenant_id == tenant_id)
        )
    ).scalar_one()

    quotes_7d = (
        await db.execute(
            select(func.count()).select_from(Quote).where(
                Quote.tenant_id == tenant_id,
                Quote.created_at >= week_ago,
            )
        )
    ).scalar_one()

    by_status_rows = (
        await db.execute(
            select(Quote.status, func.count())
            .where(Quote.tenant_id == tenant_id)
            .group_by(Quote.status)
        )
    ).all()
    by_status = {status_name: int(count) for status_name, count in by_status_rows}

    # ── Mensajes de la semana ────────────────────────────────────────────────
    messages_7d = (
        await db.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.tenant_id == tenant_id, Message.created_at >= week_ago)
        )
    ).scalar_one()

    # ── Servicios: estado del tenant + interacciones ─────────────────────────
    usage_rows = (
        await db.execute(
            select(
                ServiceUsage.module_key,
                func.count(),
                func.count().filter(ServiceUsage.created_at >= week_ago),
            )
            .where(ServiceUsage.tenant_id == tenant_id)
            .group_by(ServiceUsage.module_key)
        )
    ).all()
    usage_total = {key: int(total) for key, total, _ in usage_rows}
    usage_7d = {key: int(last_week) for key, _, last_week in usage_rows}

    module_state = {
        row.module_key: row.is_enabled
        for row in (
            await db.execute(
                select(TenantModule).where(TenantModule.tenant_id == tenant_id)
            )
        ).scalars()
    }

    services = [
        ServiceStat(
            key=module["key"],
            name=module["name"],
            dev_status=module_dev_status(module["key"]),
            is_enabled=module_state.get(module["key"], False),
            interactions=usage_total.get(module["key"], 0),
            interactions_7d=usage_7d.get(module["key"], 0),
        )
        for module in AVAILABLE_MODULES
    ]
    services.sort(key=lambda service: service.interactions, reverse=True)

    return DashboardStats(
        bot_name=bot_name,
        contacts=ContactsStats(total=contacts_total, active_last_7d=active_7d),
        quotes=QuotesStats(total=quotes_total, last_7d=quotes_7d, by_status=by_status),
        services=services,
        messages_last_7d=messages_7d,
    )
