"""Servicio CRUD para cotizaciones y sus ítems.

Reglas:
- line_total = quantity * unit_price (calculado en backend).
- quote.total = suma de todos los line_total (recalculado en cada operación de ítem).
- Aislamiento por tenant_id.
"""

import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Quote, QuoteItem
from app.schemas.quotes import (
    QuoteCreate,
    QuoteDetail,
    QuoteItemCreate,
    QuoteItemOut,
    QuoteItemUpdate,
    QuotePage,
    QuoteUpdate,
)

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _recalculate_total(db: AsyncSession, quote: Quote) -> None:
    """Recalcula quote.total sumando los line_total de sus ítems activos."""
    result = await db.execute(
        select(func.sum(QuoteItem.line_total))
        .where(QuoteItem.quote_id == quote.id)
    )
    total = result.scalar_one_or_none() or Decimal("0")
    quote.total = total


async def _load_items(db: AsyncSession, quote_id: UUID) -> list[QuoteItem]:
    result = await db.execute(
        select(QuoteItem)
        .where(QuoteItem.quote_id == quote_id)
        .order_by(QuoteItem.position, QuoteItem.created_at)
    )
    return list(result.scalars().all())


# ── Quotes CRUD ───────────────────────────────────────────────────────────────

async def list_quotes(
    db: AsyncSession,
    tenant_id: UUID,
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
) -> QuotePage:
    base = select(Quote).where(Quote.tenant_id == tenant_id)
    if status:
        base = base.where(Quote.status == status)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    items_stmt = base.order_by(Quote.created_at.desc()).offset(skip).limit(limit)
    items = (await db.execute(items_stmt)).scalars().all()

    return QuotePage(items=list(items), total=total, skip=skip, limit=limit)


async def get_quote(db: AsyncSession, tenant_id: UUID, quote_id: UUID) -> QuoteDetail | None:
    """Obtiene una cotización con sus ítems."""
    result = await db.execute(
        select(Quote)
        .where(Quote.id == quote_id)
        .where(Quote.tenant_id == tenant_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        return None

    items = await _load_items(db, quote.id)
    detail = QuoteDetail.model_validate(quote)
    detail.items = [QuoteItemOut.model_validate(i) for i in items]  # type: ignore[assignment]
    return detail


async def create_quote(
    db: AsyncSession, tenant_id: UUID, data: QuoteCreate
) -> QuoteDetail:
    """Crea una cotización con sus ítems iniciales."""
    quote = Quote(
        tenant_id=tenant_id,
        contact_id=data.contact_id,
        conversation_id=data.conversation_id,
        notes=data.notes,
        valid_until=data.valid_until,
        status="draft",
        total=Decimal("0"),
    )
    db.add(quote)
    await db.flush()

    for pos, item_data in enumerate(data.items):
        line_total = item_data.quantity * item_data.unit_price
        db.add(QuoteItem(
            tenant_id=tenant_id,
            quote_id=quote.id,
            catalog_item_id=item_data.catalog_item_id,
            description=item_data.description,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            line_total=line_total,
            position=item_data.position if item_data.position else pos,
        ))

    await db.flush()
    await _recalculate_total(db, quote)
    await db.commit()
    await db.refresh(quote)

    items = await _load_items(db, quote.id)
    from app.schemas.quotes import QuoteItemOut
    detail = QuoteDetail.model_validate(quote)
    detail.items = [QuoteItemOut.model_validate(i) for i in items]  # type: ignore[assignment]
    return detail


async def update_quote(
    db: AsyncSession, quote: Quote, data: QuoteUpdate
) -> Quote:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(quote, field, value)
    await db.commit()
    await db.refresh(quote)
    return quote


# ── Quote items CRUD ──────────────────────────────────────────────────────────

async def add_quote_item(
    db: AsyncSession, tenant_id: UUID, quote: Quote, data: QuoteItemCreate
) -> QuoteItem:
    line_total = data.quantity * data.unit_price
    item = QuoteItem(
        tenant_id=tenant_id,
        quote_id=quote.id,
        catalog_item_id=data.catalog_item_id,
        description=data.description,
        quantity=data.quantity,
        unit_price=data.unit_price,
        line_total=line_total,
        position=data.position,
    )
    db.add(item)
    await db.flush()
    await _recalculate_total(db, quote)
    await db.commit()
    await db.refresh(item)
    return item


async def update_quote_item(
    db: AsyncSession, quote: Quote, item: QuoteItem, data: QuoteItemUpdate
) -> QuoteItem:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.line_total = item.quantity * item.unit_price
    await db.flush()
    await _recalculate_total(db, quote)
    await db.commit()
    await db.refresh(item)
    return item


async def delete_quote_item(
    db: AsyncSession, quote: Quote, item: QuoteItem
) -> None:
    await db.delete(item)
    await db.flush()
    await _recalculate_total(db, quote)
    await db.commit()


async def get_quote_raw(db: AsyncSession, tenant_id: UUID, quote_id: UUID) -> Quote | None:
    """Devuelve la Quote ORM sin cargar ítems (para operaciones de actualización)."""
    result = await db.execute(
        select(Quote)
        .where(Quote.id == quote_id)
        .where(Quote.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def get_quote_item(
    db: AsyncSession, tenant_id: UUID, quote_id: UUID, item_id: UUID
) -> QuoteItem | None:
    result = await db.execute(
        select(QuoteItem)
        .where(QuoteItem.id == item_id)
        .where(QuoteItem.quote_id == quote_id)
        .where(QuoteItem.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()
