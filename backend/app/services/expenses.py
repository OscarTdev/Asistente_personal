"""Finanzas personales: ingresos y gastos con balance de cartera.

El dueño registra:
- Ingresos: «cobré 500 mil a Juliana», «ingreso 200 mil por mantenimiento»
- Gastos: «gasté 45 mil en cable», «compré gasolina por 30 mil»

El bot calcula:
- Balance actual (cartera): ingresos - gastos
- Resúmenes por día, semana, mes y año
- Snapshots históricos para gráficos

Compatibilidad: ``record_expense``/``monthly_summary`` mantienen la
firma antigua (orchestrator, google_actions y tests dependen de ella).
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Expense, WalletSnapshot

# Re-export legacy: orchestrator importa _format_cop desde aquí.
from app.services.formatting import format_cop as _format_cop  # noqa: F401
from app.services.time_window import colombia_now, month_bounds, week_bounds

logger = logging.getLogger(__name__)

# ── Categorización por palabras clave ───────────────────────────────────────

# Categorías de GASTOS (type='expense')
_EXPENSE_CATEGORIES = {
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

# Alias legacy: el resto del proyecto conoce este nombre.
_CATEGORY_KEYWORDS = _EXPENSE_CATEGORIES

# Categorías de INGRESOS (type='income')
_INCOME_CATEGORIES = {
    "clientes": (
        "cliente", "cobré", "cobre", "cobro", "pagó", "pago", "abono",
        "cuota", "factura", "cotización", "trabajo", "instalación",
        "mantenimiento", "visita", "reparación", "arreglo",
    ),
    "otros_ingresos": (
        "ingreso", "entrada", "dinero", "plata", "recibí", "recibi",
        "venta", "vendí", "vendi", "ganancia", "utilidad",
    ),
}

# Palabras clave para detectar el TIPO de movimiento (ingreso vs gasto)
_INCOME_WORDS = (
    "cobré", "cobre", "cobro", "me pagó", "me pago", "ingreso",
    "entrada", "recibí", "recibi", "abonó", "abono", "factura",
    "cobranza", "venta", "vendí", "vendi", "gané", "gane",
)
_EXPENSE_WORDS = (
    "gasté", "gaste", "gasto", "compré", "compre", "compra", "pagué",
    "pague", "salida", "coste", "costó", "costo", "mercado",
    "supermercado", "farmacia", "restaurante",
)


def detect_type(text: str) -> str:
    """¿El texto describe un ingreso o un gasto? (mayor puntaje gana)."""
    lowered = text.lower()
    income_score = sum(1 for w in _INCOME_WORDS if w in lowered)
    expense_score = sum(1 for w in _EXPENSE_WORDS if w in lowered)
    return "income" if income_score > expense_score else "expense"


def detect_category(description: str, mov_type: str = "expense") -> str:
    """Detecta la categoría según el tipo de movimiento."""
    lowered = description.lower()
    if mov_type == "income":
        for category, keywords in _INCOME_CATEGORIES.items():
            if any(word in lowered for word in keywords):
                return category
        return "otros_ingresos"
    for category, keywords in _EXPENSE_CATEGORIES.items():
        if any(word in lowered for word in keywords):
            return category
    return "otros"


# ── Registro de movimientos ─────────────────────────────────────────────────


async def record_movement(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    description: str,
    amount: Decimal,
    mov_type: str = "expense",
    category: str | None = None,
    reference_id: UUID | None = None,
    reference_type: str | None = None,
    notes: str | None = None,
) -> Expense:
    """Registra un movimiento financiero (ingreso o gasto)."""
    if mov_type not in ("income", "expense"):
        mov_type = detect_type(description)
    valid = (
        _INCOME_CATEGORIES if mov_type == "income" else _EXPENSE_CATEGORIES
    )
    if not category or category not in valid:
        category = detect_category(description, mov_type)

    expense = Expense(
        tenant_id=tenant_id,
        type=mov_type,
        description=description.strip()[:500],
        category=category,
        amount=amount,
        expense_date=datetime.now(UTC),
        reference_id=reference_id,
        reference_type=reference_type,
        notes=(notes or "").strip()[:500] or None,
    )
    db.add(expense)
    await db.commit()
    logger.info(
        "%s registrado: %s COP en %s (%s)",
        "Ingreso" if mov_type == "income" else "Gasto",
        amount, category, description[:50],
    )
    return expense


async def record_expense(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    description: str,
    amount: Decimal,
    category: str | None = None,
) -> Expense:
    """Compat: registra un GASTO (firma antigua)."""
    return await record_movement(
        db,
        tenant_id=tenant_id,
        description=description,
        amount=amount,
        mov_type="expense",
        category=category,
    )


async def record_income(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    description: str,
    amount: Decimal,
    category: str | None = None,
) -> Expense:
    """Registra un INGRESO."""
    return await record_movement(
        db,
        tenant_id=tenant_id,
        description=description,
        amount=amount,
        mov_type="income",
        category=category,
    )


# ── Cartera (balance) ───────────────────────────────────────────────────────


async def get_wallet_balance(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    as_of: datetime | None = None,
) -> dict:
    """Balance de cartera: ingresos - gastos hasta una fecha."""
    if as_of is None:
        as_of = datetime.now(UTC)

    total_income = (
        await db.execute(
            select(func.coalesce(func.sum(Expense.amount), Decimal(0)))
            .where(
                Expense.tenant_id == tenant_id,
                Expense.type == "income",
                Expense.expense_date <= as_of,
            )
        )
    ).scalar_one()

    total_expenses = (
        await db.execute(
            select(func.coalesce(func.sum(Expense.amount), Decimal(0)))
            .where(
                Expense.tenant_id == tenant_id,
                Expense.type == "expense",
                Expense.expense_date <= as_of,
            )
        )
    ).scalar_one()

    return {
        "balance": total_income - total_expenses,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "currency": "COP",
        "as_of": as_of.isoformat(),
    }


# ── Resúmenes por período ──────────────────────────────────────────────────


async def get_period_summary(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    period: str,  # "day" | "week" | "month" | "year"
    date: datetime | None = None,
) -> dict:
    """Resumen de ingresos/gastos de un período (hora Colombia)."""
    if date is None:
        date = colombia_now()

    if period == "day":
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        period_label = start.strftime("%d/%m/%Y")
    elif period == "week":
        start, end = week_bounds(date)
        end_col = end - timedelta(hours=5)
        period_label = (
            f"Semana del {start.strftime('%d/%m')} al "
            f"{end_col.strftime('%d/%m/%Y')}"
        )
    elif period == "month":
        start, end = month_bounds(date)
        period_label = start.strftime("%B %Y")
    elif period == "year":
        start = date.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end = start.replace(year=start.year + 1)
        period_label = str(start.year)
    else:
        raise ValueError(f"Período inválido: {period}")

    # start/end vienen en UTC (time_window); day/year ya están en Colombia
    if period in ("day", "year"):
        start_utc = start + timedelta(hours=5)
        end_utc = end + timedelta(hours=5)
    else:
        start_utc, end_utc = start, end

    income_rows = (
        await db.execute(
            select(Expense.category, func.sum(Expense.amount), func.count())
            .where(
                Expense.tenant_id == tenant_id,
                Expense.type == "income",
                Expense.expense_date >= start_utc,
                Expense.expense_date < end_utc,
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
        )
    ).all()

    expense_rows = (
        await db.execute(
            select(Expense.category, func.sum(Expense.amount), func.count())
            .where(
                Expense.tenant_id == tenant_id,
                Expense.type == "expense",
                Expense.expense_date >= start_utc,
                Expense.expense_date < end_utc,
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
        )
    ).all()

    total_income = sum(row[1] or Decimal(0) for row in income_rows)
    total_expenses = sum(row[1] or Decimal(0) for row in expense_rows)

    return {
        "period": period,
        "period_label": period_label,
        "start_date": start_utc.isoformat(),
        "end_date": end_utc.isoformat(),
        # Claves estilo antiguo (solo gastos) para compatibilidad
        "total": total_expenses,
        "categories": {
            row[0]: {"total": row[1] or Decimal(0), "count": row[2]}
            for row in expense_rows
        },
        "month": period_label,
        # Claves nuevas (ingresos + gastos + neto)
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net": total_income - total_expenses,
        "income_categories": {
            row[0]: {"total": row[1] or Decimal(0), "count": row[2]}
            for row in income_rows
        },
        "expense_categories": {
            row[0]: {"total": row[1] or Decimal(0), "count": row[2]}
            for row in expense_rows
        },
        "currency": "COP",
    }


async def daily_summary(
    db: AsyncSession, *, tenant_id: UUID, date: datetime | None = None
) -> dict:
    """Resumen del día."""
    return await get_period_summary(
        db, tenant_id=tenant_id, period="day", date=date
    )


async def weekly_summary(
    db: AsyncSession, *, tenant_id: UUID, date: datetime | None = None
) -> dict:
    """Resumen de la semana (lunes a domingo, hora Colombia)."""
    return await get_period_summary(
        db, tenant_id=tenant_id, period="week", date=date
    )


async def monthly_summary(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    month: datetime | None = None,
) -> dict:
    """Resumen del mes (compat: ``total``/``categories`` = solo gastos)."""
    return await get_period_summary(
        db, tenant_id=tenant_id, period="month", date=month
    )


async def yearly_summary(
    db: AsyncSession, *, tenant_id: UUID, year: datetime | None = None
) -> dict:
    """Resumen del año."""
    return await get_period_summary(
        db, tenant_id=tenant_id, period="year", date=year
    )


async def recent_expenses(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    limit: int = 10,
    mov_type: str | None = None,
) -> list[Expense]:
    """Movimientos más recientes, opcionalmente filtrados por tipo."""
    stmt = select(Expense).where(Expense.tenant_id == tenant_id)
    if mov_type:
        stmt = stmt.where(Expense.type == mov_type)
    stmt = stmt.order_by(Expense.expense_date.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


# ── Wallet Snapshots (gráficos históricos) ──────────────────────────────────


async def upsert_wallet_snapshot(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    date: datetime | None = None,
) -> WalletSnapshot:
    """Crea o actualiza el snapshot del balance del día."""
    if date is None:
        date = colombia_now()

    day_start_col = date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_col = date.replace(hour=23, minute=59, second=59, microsecond=0)
    day_start_utc = day_start_col + timedelta(hours=5)
    day_end_utc = day_end_col + timedelta(hours=5)

    balance_data = await get_wallet_balance(
        db, tenant_id=tenant_id, as_of=day_end_utc
    )

    daily_income = (
        await db.execute(
            select(func.coalesce(func.sum(Expense.amount), Decimal(0)))
            .where(
                Expense.tenant_id == tenant_id,
                Expense.type == "income",
                Expense.expense_date >= day_start_utc,
                Expense.expense_date <= day_end_utc,
            )
        )
    ).scalar_one()

    daily_expenses = (
        await db.execute(
            select(func.coalesce(func.sum(Expense.amount), Decimal(0)))
            .where(
                Expense.tenant_id == tenant_id,
                Expense.type == "expense",
                Expense.expense_date >= day_start_utc,
                Expense.expense_date <= day_end_utc,
            )
        )
    ).scalar_one()

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(WalletSnapshot).values(
        tenant_id=tenant_id,
        snapshot_date=day_start_utc,
        balance=balance_data["balance"],
        total_income=balance_data["total_income"],
        total_expenses=balance_data["total_expenses"],
        daily_income=daily_income,
        daily_expenses=daily_expenses,
    ).on_conflict_do_update(
        index_elements=["tenant_id", "snapshot_date"],
        set_=dict(
            balance=balance_data["balance"],
            total_income=balance_data["total_income"],
            total_expenses=balance_data["total_expenses"],
            daily_income=daily_income,
            daily_expenses=daily_expenses,
        ),
    )
    await db.execute(stmt)
    await db.commit()

    return (
        await db.execute(
            select(WalletSnapshot).where(
                WalletSnapshot.tenant_id == tenant_id,
                WalletSnapshot.snapshot_date == day_start_utc,
            )
        )
    ).scalar_one()


async def get_wallet_history(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    days: int = 30,
) -> list[WalletSnapshot]:
    """Historial de snapshots (últimos N días)."""
    cutoff_col = colombia_now() - timedelta(days=days)
    cutoff_utc = cutoff_col.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(hours=5)

    return list(
        (
            await db.execute(
                select(WalletSnapshot)
                .where(
                    WalletSnapshot.tenant_id == tenant_id,
                    WalletSnapshot.snapshot_date >= cutoff_utc,
                )
                .order_by(WalletSnapshot.snapshot_date.asc())
            )
        ).scalars().all()
    )
