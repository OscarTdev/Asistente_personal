"""Finanzas personales: gastos por voz con categorización y resumen mensual.

El técnico dice «gasté 45 mil en cable» y el bot lo registra con la
categoría correcta. Al final del mes: «cuánto he gastado» → resumen
agrupado por categoría con el total.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Expense

logger = logging.getLogger(__name__)

# ── Categorización por palabras clave ───────────────────────────────────────

_CATEGORY_KEYWORDS = {
    "materiales": (
        "cable", "breaker", "tomacorriente", "tubo", "conduit", "material",
        "tornillo", "cinta", "aislante", "socket", "interruptor", "foco",
        "bombilla", "medidor", "panel", "tablero", "ducto", "valvula",
        "válvula", "grifo", "tuberia", "tubería", "canaleta", "pegante",
    ),
    "transporte": (
        "gasolina", "transporte", "uber", "bus", "taxi", "moto", "carro",
        "parqueadero", "peaje", "didi", "beat", "combustible", "acpm",
    ),
    "comida": (
        "comida", "almuerzo", "desayuno", "cena", "café", "cafe", "tinto",
        "agua", "gaseosa", "restaurante", "empanada", "arepa", "jugo",
    ),
    "herramientas": (
        "herramienta", "taladro", "destornillador", "alicate", "pinza",
        "martillo", "sierra", "metro", "escalera", "borracho", "multímetro",
        "multimetro", "destapa", "ponchadora",
    ),
    "arriendo": (
        "arriendo", "alquiler", "renta", "bodega", "oficina", "local",
    ),
    "servicios": (
        "luz", "agua", "internet", "celular", "telefono", "teléfono",
        "data", "plan", "recibo", "gas", "predial",
    ),
    "otros": (),
}


def detect_category(description: str) -> str:
    """Detecta la categoría del gasto por las palabras de la descripción."""
    lowered = description.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(word in lowered for word in keywords):
            return category
    return "otros"


# ── CRUD ───────────────────────────────────────────────────────────────────


async def record_expense(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    description: str,
    amount: Decimal,
    category: str | None = None,
) -> Expense:
    """Registra un gasto con la categoría auto-detectada."""
    if category is None or category not in _CATEGORY_KEYWORDS:
        category = detect_category(description)
    expense = Expense(
        tenant_id=tenant_id,
        description=description.strip()[:500],
        category=category,
        amount=amount,
        expense_date=datetime.now(UTC),
    )
    db.add(expense)
    await db.commit()
    logger.debug(
        "Gasto registrado: %s COP en %s (%s)", amount, category, description[:50]
    )
    return expense


async def monthly_summary(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    month: datetime | None = None,
) -> dict:
    """Resumen del mes: total y desglose por categoría.

    "Este mes" se define en hora Colombia (UTC-5): sin esto, un gasto
    del 31 a las 8pm Bogotá caería en el mes siguiente (01:00 UTC).
    """
    if month is None:
        month = datetime.now(UTC) - timedelta(hours=5)  # hora Colombia
    start_col = month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start_col.month == 12:
        end_col = start_col.replace(year=start_col.year + 1, month=1)
    else:
        end_col = start_col.replace(month=start_col.month + 1)
    start = start_col + timedelta(hours=5)  # local → UTC
    end = end_col + timedelta(hours=5)

    rows = (
        await db.execute(
            select(Expense.category, func.sum(Expense.amount), func.count())
            .where(
                Expense.tenant_id == tenant_id,
                Expense.expense_date >= start,
                Expense.expense_date < end,
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
        )
    ).all()

    total = sum(row[1] or Decimal(0) for row in rows)
    return {
        "total": total,
        "categories": {
            row[0]: {
                "total": row[1] or Decimal(0),
                "count": row[2],
            }
            for row in rows
        },
        "month": start.strftime("%B %Y"),
    }


async def recent_expenses(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    limit: int = 10,
) -> list[Expense]:
    """Los gastos más recientes."""
    return list(
        (
            await db.execute(
                select(Expense)
                .where(Expense.tenant_id == tenant_id)
                .order_by(Expense.expense_date.desc())
                .limit(limit)
            )
        ).scalars().all()
    )


def _format_cop(amount: Decimal | float | int) -> str:
    try:
        return f"${float(amount):,.0f}".replace(",", ".")
    except Exception:
        return f"${amount}"
