"""Registro de auditoría de la plataforma (adendo §4.3, §4.6).

Toda acción del superadmin que toca datos de un cliente queda aquí:
quién, acción, tenant, objeto, motivo y fecha. Append-only: la auditoría
no se edita ni se borra.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

logger = logging.getLogger(__name__)


async def log_action(
    db: AsyncSession,
    *,
    actor_user_id: UUID,
    action: str,
    tenant_id: UUID | None = None,
    object_ref: str | None = None,
    reason: str | None = None,
) -> AuditLog:
    """Escribe una entrada de auditoría. No confirma: la confirmación es
    del request que la provocó; si ese falla, la entrada se va con él."""
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        tenant_id=tenant_id,
        object_ref=object_ref,
        reason=reason,
    )
    db.add(entry)
    await db.flush()
    logger.info(
        "AUDITORÍA %s por %s (tenant %s): %s",
        action, actor_user_id, tenant_id, (reason or "")[:60],
    )
    return entry


async def list_entries(
    db: AsyncSession,
    *,
    tenant_id: UUID | None = None,
    limit: int = 50,
) -> list[AuditLog]:
    """Las entradas más recientes; por tenant si se pide."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if tenant_id is not None:
        stmt = stmt.where(AuditLog.tenant_id == tenant_id)
    return list((await db.execute(stmt)).scalars().all())
