"""Entitlements: aplicar el plan de un tenant a sus servicios.

`apply_plan` es LA pieza que sincroniza el plan con los módulos: activa los
incluidos, apaga los que quedan fuera, deja historial en `subscriptions` y
un evento para el feed del panel. Nadie enciende un servicio que su plan no
autoriza: la validación vive en `module_allowed` — con los overrides del
Admin (matriz gratis/VIP) y los defaults del código como respaldo.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.modules_registry import (
    AVAILABLE_MODULES,
    PLAN_ENTITLEMENTS,
    plan_entitlements,
)
from app.models import (
    Event,
    PaymentMethod,
    PlanEntitlement,
    Subscription,
    Tenant,
    TenantModule,
)

logger = logging.getLogger(__name__)

# Estado de la fila de suscripción según el plan aplicado
PLAN_SUBSCRIPTION_STATUS: dict[str, str] = {
    "trial": "trial",
    "freemium": "freemium",
    "premium": "active",
}

SUBSCRIPTION_PERIOD_DAYS = 30


# ── Matriz gratis/VIP (overrides del Admin) ────────────────────────────────


async def module_allowed(
    db: AsyncSession, *, plan: str, module_key: str
) -> bool:
    """¿El plan autoriza el servicio? Override del Admin o default del código."""
    row = (
        await db.execute(
            select(PlanEntitlement).where(
                PlanEntitlement.plan == plan,
                PlanEntitlement.module_key == module_key,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row.allowed
    return module_key in plan_entitlements(plan)


async def plan_modules(db: AsyncSession, *, plan: str) -> dict[str, bool]:
    """Estado de cada servicio para el plan: override o default."""
    overrides = {
        row.module_key: row.allowed
        for row in (
            await db.execute(
                select(PlanEntitlement).where(PlanEntitlement.plan == plan)
            )
        ).scalars()
    }
    defaults = plan_entitlements(plan)
    return {
        definition["key"]: overrides.get(
            definition["key"], definition["key"] in defaults
        )
        for definition in AVAILABLE_MODULES
    }


async def set_entitlement(
    db: AsyncSession, *, plan: str, module_key: str, allowed: bool
) -> PlanEntitlement:
    """Crea o actualiza un override de la matriz (upsert)."""
    row = (
        await db.execute(
            select(PlanEntitlement).where(
                PlanEntitlement.plan == plan,
                PlanEntitlement.module_key == module_key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = PlanEntitlement(plan=plan, module_key=module_key, allowed=allowed)
        db.add(row)
    else:
        row.allowed = allowed
    await db.commit()
    logger.info(
        "Matriz de planes: %s/%s → %s (super admin)", plan, module_key, allowed
    )
    return row


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
    entitled = await plan_modules(db, plan=plan)

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
        should_enable = entitled.get(key, False)
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

    # 2) Historial de suscripción: una fila por cambio de plan.
    #    Renovación premium: el periodo se extiende DESDE el fin del periodo
    #    vigente (no desde hoy) — pagar dos veces no regala días.
    now = datetime.now(UTC)
    is_premium = plan == "premium"
    period_start = now if is_premium else None
    period_end = None
    if is_premium:
        base = now
        latest = (
            await db.execute(
                select(Subscription)
                .where(Subscription.tenant_id == tenant_id)
                .order_by(Subscription.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if (
            latest is not None
            and latest.status == "active"
            and latest.current_period_end is not None
            and latest.current_period_end > now
        ):
            base = latest.current_period_end
        period_end = base + timedelta(days=SUBSCRIPTION_PERIOD_DAYS)

    db.add(
        Subscription(
            tenant_id=tenant_id,
            plan_key=plan,
            status=PLAN_SUBSCRIPTION_STATUS[plan],
            provider=provider,
            provider_ref=provider_ref,
            current_period_start=period_start,
            current_period_end=period_end,
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


async def expire_subscriptions(db: AsyncSession) -> int:
    """Vence suscripciones premium cuyo periodo terminó.

    La fila de suscripción pasa a 'past_due' y el tenant baja de plan:
    freemium si tiene método de pago en archivo, trial si no. El evento
    'tenant.plan_changed' queda en el feed del panel.
    """
    now = datetime.now(UTC)
    tenants = (
        await db.execute(select(Tenant).where(Tenant.plan == "premium"))
    ).scalars().all()

    expired = 0
    for tenant in tenants:
        latest = (
            await db.execute(
                select(Subscription)
                .where(Subscription.tenant_id == tenant.id)
                .order_by(Subscription.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if (
            latest is None
            or latest.status != "active"
            or latest.current_period_end is None
            or latest.current_period_end >= now
        ):
            continue

        latest.status = "past_due"
        await db.commit()

        methods = (
            await db.execute(
                select(func.count())
                .select_from(PaymentMethod)
                .where(PaymentMethod.tenant_id == tenant.id)
            )
        ).scalar_one()
        target_plan = "freemium" if methods > 0 else "trial"

        await apply_plan(
            db, tenant_id=tenant.id, plan=target_plan, provider="system"
        )
        expired += 1
        logger.info(
            "Suscripción del tenant %s vencida → %s", tenant.slug, target_plan
        )

    return expired
