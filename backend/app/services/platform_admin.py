"""Casos de uso de administración de clientes de Aura.

Este módulo contiene reglas de aplicación para el superadmin. Los routers solo
adaptan HTTP: las métricas y el cambio de estado pueden reutilizarse desde el
panel, comandos del chat o workers sin duplicar consultas ni autorización.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.modules_registry import AVAILABLE_MODULES
from app.models import Message, Quote, ServiceUsage, Tenant
from app.schemas.admin import (
    PlatformAdminStats,
    PlatformPlanStat,
    PlatformServiceStat,
)


async def compute_platform_stats(db: AsyncSession) -> PlatformAdminStats:
    """Calcula métricas globales excluyendo el tenant técnico de plataforma.

    Complejidad temporal: O(S + M + Q + U), donde S es el número de filas de
    servicios usados, M mensajes y Q cotizaciones; el trabajo se ejecuta en
    agregaciones indexables de PostgreSQL, no en memoria de Python.
    Complejidad espacial: O(K), con K servicios distintos registrados.
    """
    tenant_filter = Tenant.is_platform.is_(False)

    plan_rows = (
        await db.execute(
            select(Tenant.plan, func.count())
            .where(tenant_filter)
            .group_by(Tenant.plan)
        )
    ).all()
    plans = [PlatformPlanStat(plan=plan, count=int(count)) for plan, count in plan_rows]
    total_tenants = sum(item.count for item in plans)

    active_tenants = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Tenant)
                .where(tenant_filter, Tenant.is_active.is_(True))
            )
        ).scalar_one()
    )
    total_messages = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Message)
                .join(Tenant, Tenant.id == Message.tenant_id)
                .where(tenant_filter)
            )
        ).scalar_one()
    )
    total_quotes = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Quote)
                .join(Tenant, Tenant.id == Quote.tenant_id)
                .where(tenant_filter)
            )
        ).scalar_one()
    )

    usage_rows = (
        await db.execute(
            select(
                ServiceUsage.module_key,
                func.count().label("interactions"),
                func.count(func.distinct(ServiceUsage.tenant_id)).label("tenants"),
            )
            .join(Tenant, Tenant.id == ServiceUsage.tenant_id)
            .where(tenant_filter)
            .group_by(ServiceUsage.module_key)
            .order_by(func.count().desc())
        )
    ).all()
    service_names = {module["key"]: module["name"] for module in AVAILABLE_MODULES}
    services = [
        PlatformServiceStat(
            key=key,
            name=service_names.get(key, key),
            interactions=int(interactions),
            tenants=int(tenants),
        )
        for key, interactions, tenants in usage_rows
    ]

    return PlatformAdminStats(
        total_tenants=total_tenants,
        active_tenants=active_tenants,
        blocked_tenants=total_tenants - active_tenants,
        total_messages=total_messages,
        total_quotes=total_quotes,
        services=services,
        plans=plans,
    )


async def set_tenant_status(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    is_active: bool,
) -> Tenant:
    """Actualiza el estado funcional de un cliente, sin borrar sus datos."""
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise LookupError("Tenant no encontrado")
    if tenant.is_platform:
        raise ValueError("El tenant de plataforma no puede bloquearse")
    tenant.is_active = is_active
    return tenant
