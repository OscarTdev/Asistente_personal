"""Motor de disponibilidad de servicios (adendo §5).

Orden para decidir si el cliente X puede usar el servicio S:
1. Interruptor global (service_status): down/maintenance → no.
2. Excepción por cliente (tenant_service_overrides): si existe y no venció, manda.
3. Plan del cliente (matriz PlanEntitlement con defaults del código).
Devuelve (disponible, motivo) — el motivo alimenta el mensaje claro del bot.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ServiceStatus, Tenant, TenantServiceOverride
from app.services.entitlements import module_allowed

logger = logging.getLogger(__name__)

# Estados que bloquean el uso; «degraded» deja pasar (funciona, pero peor)
BLOCKING_STATUSES = ("down", "maintenance")


async def get_status(db: AsyncSession, service_key: str) -> dict[str, Any]:
    """Estado global del servicio; sin fila → operativo."""
    row = (
        await db.execute(
            select(ServiceStatus).where(ServiceStatus.service_key == service_key)
        )
    ).scalar_one_or_none()
    if row is None:
        return {
            "service_key": service_key,
            "status": "operational",
            "message": None,
            "source": "auto",
        }
    return {
        "service_key": row.service_key,
        "status": row.status,
        "message": row.message,
        "source": row.source,
    }


async def set_status(
    db: AsyncSession,
    *,
    service_key: str,
    status: str,
    message: str | None = None,
    source: str = "manual",
    updated_by: UUID | None = None,
) -> ServiceStatus:
    """Crea o actualiza el estado global (upsert)."""
    row = (
        await db.execute(
            select(ServiceStatus).where(ServiceStatus.service_key == service_key)
        )
    ).scalar_one_or_none()
    if row is None:
        row = ServiceStatus(
            service_key=service_key, status=status, message=message,
            source=source, updated_by=updated_by,
        )
        db.add(row)
    else:
        row.status = status
        row.message = message
        row.source = source
        row.updated_by = updated_by
    await db.commit()
    logger.info("Estado del servicio %s → %s (%s)", service_key, status, source)
    return row


async def list_statuses(db: AsyncSession) -> list[dict[str, Any]]:
    """Todos los estados con fila; los servicios sin fila son operativos."""
    rows = (await db.execute(select(ServiceStatus))).scalars().all()
    return [
        {
            "service_key": r.service_key,
            "status": r.status,
            "message": r.message,
            "source": r.source,
        }
        for r in rows
    ]


async def effective_override(
    db: AsyncSession, *, tenant_id: UUID, service_key: str
) -> TenantServiceOverride | None:
    """La excepción vigente del cliente; vencida no cuenta."""
    row = (
        await db.execute(
            select(TenantServiceOverride).where(
                TenantServiceOverride.tenant_id == tenant_id,
                TenantServiceOverride.service_key == service_key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.expires_at is not None and row.expires_at <= datetime.now(UTC):
        return None
    return row


async def set_override(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    service_key: str,
    allowed: bool,
    reason: str,
    expires_at: datetime | None = None,
    created_by: UUID | None = None,
) -> TenantServiceOverride:
    """Crea o actualiza la excepción del cliente (upsert). Motivo obligatorio."""
    if not reason.strip():
        raise ValueError("El motivo es obligatorio (adendo §4)")
    row = (
        await db.execute(
            select(TenantServiceOverride).where(
                TenantServiceOverride.tenant_id == tenant_id,
                TenantServiceOverride.service_key == service_key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = TenantServiceOverride(
            tenant_id=tenant_id,
            service_key=service_key,
            allowed=allowed,
            reason=reason.strip(),
            expires_at=expires_at,
            created_by=created_by,
        )
        db.add(row)
    else:
        row.allowed = allowed
        row.reason = reason.strip()
        row.expires_at = expires_at
        row.created_by = created_by
    await db.commit()
    logger.info(
        "Excepción de %s/%s → %s (tenant %s)", service_key, allowed, reason[:60], tenant_id
    )
    return row


async def clear_override(
    db: AsyncSession, *, tenant_id: UUID, service_key: str
) -> bool:
    row = (
        await db.execute(
            select(TenantServiceOverride).where(
                TenantServiceOverride.tenant_id == tenant_id,
                TenantServiceOverride.service_key == service_key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def service_available(
    db: AsyncSession, *, tenant_id: UUID, plan: str, service_key: str
) -> tuple[bool, str | None]:
    """El veredicto completo del adendo §5: (disponible, motivo si no)."""
    # 1) Interruptor global
    state = await get_status(db, service_key)
    if state["status"] in BLOCKING_STATUSES:
        return False, state["message"] or f"Este servicio está en {state['status']}"

    # 2) Excepción por cliente: manda sobre el plan
    override = await effective_override(
        db, tenant_id=tenant_id, service_key=service_key
    )
    if override is not None:
        if override.allowed:
            return True, None
        return False, "El administrador desactivó este servicio para tu cuenta"

    # 3) Plan
    if not await module_allowed(db, plan=plan, module_key=service_key):
        return False, "Tu plan no incluye este servicio"

    return True, None


async def tenant_plan(db: AsyncSession, tenant_id: UUID) -> str:
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    return tenant.plan if tenant else "trial"
