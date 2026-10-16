"""Inventario de materiales: registrar, consultar, descontar y alertar (spec §13).

El técnico dice «tengo 20 metros de cable» y el bot lo registra.
«usé 15 metros» descuenta. «qué inventario tengo» lista todo.
Cuando queda menos que el mínimo, el bot sugiere comprar más.
"""

import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InventoryItem

logger = logging.getLogger(__name__)

# Unidades comunes para técnicos en Colombia
_UNIT_KEYWORDS = {
    "metros": ("metro", "metros", "m de", "ml de"),
    "unidades": ("unidad", "unidades", "und", "u de"),
    "cajas": ("caja", "cajas"),
    "litros": ("litro", "litros", "l de"),
    "kg": ("kilo", "kilos", "kg de", "kilogramo"),
    "rollos": ("rollo", "rollos"),
    "galones": ("galon", "galón", "galones"),
}


def detect_unit(description: str) -> str:
    """Detecta la unidad del texto natural."""
    lowered = description.lower()
    for unit, keywords in _UNIT_KEYWORDS.items():
        if any(word in lowered for word in keywords):
            return unit
    return "unidades"


def _norm(name: str) -> str:
    """Normaliza el nombre del material para búsqueda (ILIKE escapado)."""
    from app.services.ai_extraction import _escape_like
    return _escape_like(name.strip().lower()[:80])


async def _find_or_create(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    name: str,
    unit: str,
) -> InventoryItem:
    """Busca el ítem por nombre (ILIKE) o lo crea si no existe."""
    pattern = f"%{_norm(name)}%"
    item = (
        await db.execute(
            select(InventoryItem)
            .where(
                InventoryItem.tenant_id == tenant_id,
                InventoryItem.is_active.is_(True),
                InventoryItem.name.ilike(pattern),
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    if item is None:
        item = InventoryItem(
            tenant_id=tenant_id,
            name=name.strip()[:200],
            unit=unit,
            quantity=Decimal("0"),
            min_quantity=Decimal("0"),
        )
        db.add(item)
        await db.flush()
    return item


async def add_stock(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    name: str,
    quantity: Decimal,
    unit: str | None = None,
) -> InventoryItem:
    """Agrega material al inventario (o crea el ítem si no existe)."""
    if unit is None:
        unit = detect_unit(name)
    item = await _find_or_create(db, tenant_id=tenant_id, name=name, unit=unit)
    item.quantity = (item.quantity or Decimal("0")) + quantity
    if item.unit == "unidades" and unit != "unidades":
        item.unit = unit
    await db.commit()
    logger.debug("Inventario: %s +%s %s", name[:30], quantity, unit)
    return item


async def deduct_stock(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    name: str,
    quantity: Decimal,
) -> InventoryItem | None:
    """Descuenta material del inventario. None si no hay suficiente."""
    pattern = f"%{_norm(name)}%"
    item = (
        await db.execute(
            select(InventoryItem)
            .where(
                InventoryItem.tenant_id == tenant_id,
                InventoryItem.is_active.is_(True),
                InventoryItem.name.ilike(pattern),
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    if item is None:
        return None
    if item.quantity < quantity:
        return None

    item.quantity = item.quantity - quantity
    await db.commit()
    return item


async def list_inventory(
    db: AsyncSession,
    *,
    tenant_id: UUID,
) -> list[InventoryItem]:
    """Todo el inventario activo del negocio."""
    return list(
        (
            await db.execute(
                select(InventoryItem)
                .where(
                    InventoryItem.tenant_id == tenant_id,
                    InventoryItem.is_active.is_(True),
                )
                .order_by(InventoryItem.name.asc())
            )
        ).scalars().all()
    )


async def low_stock_items(
    db: AsyncSession,
    *,
    tenant_id: UUID,
) -> list[InventoryItem]:
    """Materiales cuya cantidad es menor o igual al mínimo."""
    return list(
        (
            await db.execute(
                select(InventoryItem)
                .where(
                    InventoryItem.tenant_id == tenant_id,
                    InventoryItem.is_active.is_(True),
                    InventoryItem.quantity <= InventoryItem.min_quantity,
                    InventoryItem.min_quantity > 0,
                )
                .order_by(InventoryItem.quantity.asc())
            )
        ).scalars().all()
    )


def _fmt_qty(quantity: Decimal, unit: str) -> str:
    """Formatea la cantidad: 20 metros, 5 unidades, 2.5 kg."""
    qty = float(quantity)
    if qty == int(qty):
        return f"{int(qty)} {unit}"
    return f"{qty} {unit}"
