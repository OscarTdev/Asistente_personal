"""Router del dashboard del panel."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Tenant, User
from app.schemas.dashboard import DashboardStats
from app.schemas.realtime import RealtimeActivity
from app.services.dashboard import compute_stats
from app.services.realtime import compute_realtime_activity

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardStats:
    """Métricas del asistente: clientes, cotizaciones y servicios."""
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one()
    return await compute_stats(
        db, tenant_id=current_user.tenant_id, bot_name=tenant.bot_name
    )


@router.get("/realtime", response_model=RealtimeActivity)
async def dashboard_realtime(
    window_minutes: int = Query(default=15, ge=5, le=120),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RealtimeActivity:
    """Actividad real reciente del bot, aislada al tenant autenticado."""
    return await compute_realtime_activity(
        db, tenant_id=current_user.tenant_id, window_minutes=window_minutes
    )
