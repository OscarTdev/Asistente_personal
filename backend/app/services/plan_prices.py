"""Precios de los planes: default del código + override desde el panel.

El panel de administración escribe en plan_prices; el checkout y la
validación de pagos leen siempre el precio vigente (override o default).
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.modules_registry import PLAN_LABELS, PLAN_PRICE_COP
from app.models import PlanPrice

logger = logging.getLogger(__name__)

MAX_PRICE_COP = 10_000_000


async def effective_price(db: AsyncSession, plan: str) -> int | None:
    """Precio vigente del plan: override del panel o default del código."""
    row = (
        await db.execute(select(PlanPrice).where(PlanPrice.plan == plan))
    ).scalar_one_or_none()
    if row is not None:
        return row.price_cop
    return PLAN_PRICE_COP.get(plan)


async def list_plans(db: AsyncSession) -> list[dict[str, Any]]:
    """Todos los planes con su precio vigente y si viene del panel."""
    overrides = {
        row.plan: row.price_cop
        for row in (await db.execute(select(PlanPrice))).scalars()
    }
    return [
        {
            "plan": plan,
            "label": label,
            "price_cop": overrides.get(plan, PLAN_PRICE_COP[plan]),
            "is_overridden": plan in overrides,
        }
        for plan, label in PLAN_LABELS.items()
    ]


async def set_price(db: AsyncSession, *, plan: str, price_cop: int) -> dict[str, Any]:
    """Crea o actualiza el override del precio de un plan (upsert)."""
    row = (
        await db.execute(select(PlanPrice).where(PlanPrice.plan == plan))
    ).scalar_one_or_none()
    if row is None:
        row = PlanPrice(plan=plan, price_cop=price_cop)
        db.add(row)
    else:
        row.price_cop = price_cop
    await db.commit()
    logger.info("Precio del plan '%s' actualizado a %s COP", plan, price_cop)
    return {
        "plan": plan,
        "label": PLAN_LABELS[plan],
        "price_cop": row.price_cop,
        "is_overridden": True,
    }
