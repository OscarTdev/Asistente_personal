"""Registro de interacciones por servicio — alimenta las métricas del panel
(servicios más demandados)."""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ServiceUsage

logger = logging.getLogger(__name__)


async def log_service_usage(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    module_key: str,
    kind: str,
    contact_id: UUID | None = None,
) -> None:
    """Anota una interacción atendida por un servicio.

    Se llama DESPUÉS de que la operación principal tuvo éxito (y confirmó
    su propia transacción). Best-effort: si falla no revienta la acción
    principal, solo se pierde la métrica.
    """
    try:
        db.add(
            ServiceUsage(
                tenant_id=tenant_id,
                module_key=module_key,
                kind=kind,
                contact_id=contact_id,
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        # Sin datos personales en el log (Ley 1581)
        logger.exception("No se pudo registrar el uso del servicio %s", module_key)
