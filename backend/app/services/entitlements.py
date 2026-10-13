"""Entitlements: aplicar el plan de un tenant a sus servicios.

`apply_plan` es LA pieza que sincroniza el plan con los módulos: activa los
incluidos, apaga los que quedan fuera, deja historial en `subscriptions` y
un evento para el feed del panel. Nadie enciende un servicio que su plan no
autoriza: la validación vive en el router de admin (contrato de entitlements).
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.modules_registry import (
    AVAILABLE_MODULES,
    PLAN_ENTITLEMENTS,
    plan_entitlements,
)
from app.models import Event, Subscription, Tenant, TenantModule

logger = logging.getLogger(__name__)

# Estado de la fila de suscripción según el plan aplicado
PLAN_SUBSCRIPTION_STATUS: dict[str, str] = {
    "trial": "trial",
    "freemium": "freemium",
    "premium": "active",
}

SUBSCRIPTION_PERIOD_DAYS = 30


async def apply_plan(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    plan: str,
    provider: str = "manual",
    provider_ref: str | None = None,
) -> Tenant:
    """Aplica el plan: sincroniza módulos, registra historial y devuelve el tenant."""
    if plan not in PLAN_ENTITLEMENTS:
        raise ValueError(f"Plan desconocido: {plan}")

    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one()
    previous_plan = tenant.plan
    entitled = plan_entitlements(plan)

    # 1) Módulos: encender los del plan, apagar el resto (upsert; sin tocar filas ya correctas)
    existing = {
        tm.module_key: tm
        for tm in (
            await db.execute(
                select(TenantModule).where(TenantModule.tenant_id == tenant_id)
            )
        ).scalars()
    }
    for definition in AVAILABLE_MODULES:
        key = definition["key"]
        should_enable = key in entitled
        row = existing.get(key)
        if row is None:
            db.add(
                TenantModule(
                    tenant_id=tenant_id,
                    module_key=key,
                    name=definition["name"],
                    description=definition["description"],
                    category=definition["category"],
                    is_enabled=should_enable,
                )
            )
        elif row.is_enabled != should_enable:
            row.is_enabled = should_enable

    # 2) Historial de suscripción: una fila por cambio de plan
    now = datetime.now(UTC)
    is_premium = plan == "premium"
    db.add(
        Subscription(
            tenant_id=tenant_id,
            plan_key=plan,
            status=PLAN_SUBSCRIPTION_STATUS[plan],
            provider=provider,
            provider_ref=provider_ref,
            current_period_start=now if is_premium else None,
            current_period_end=(
                now + timedelta(days=SUBSCRIPTION_PERIOD_DAYS) if is_premium else None
            ),
        )
    )

    # 3) Evento para el feed del panel
    db.add(
        Event(
            tenant_id=tenant_id,
            type="tenant.plan_changed",
            payload={"plan": plan, "previous": previous_plan},
        )
    )

    tenant.plan = plan
    await db.commit()
    await db.refresh(tenant)
    logger.info(
        "Plan del tenant %s: %s → %s (%d servicios autorizados)",
        tenant_id,
        previous_plan,
        plan,
        len(entitled),
    )
    return tenant
