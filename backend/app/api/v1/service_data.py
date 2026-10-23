"""API para los datos de los servicios operativos del técnico.

Un solo router con los listados por servicio — el panel los consume a
través de una página parametrizada. Todos los queries son por tenant
(del token, nunca del request). Escrituras mínimas para que el dueño
pueda ajustar desde el panel lo que ya hace por chat.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import (
    Contact,
    Expense,
    InventoryItem,
    Maintenance,
    User,
    Warranty,
)
from app.models.site_log import SiteLog

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Esquemas ──────────────────────────────────────────────────────────────


class InventoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    unit: str
    quantity: float
    min_quantity: float
    is_active: bool
    updated_at: datetime


class InventoryAdjust(BaseModel):
    """Ajustar el stock desde el panel (llegada/descuento de material)."""

    delta: float  # positivo = entra, negativo = sale
    reason: str | None = None


class MaintenanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contact_id: UUID
    contact_name: str | None = None
    description: str
    frequency_days: int
    next_due: datetime
    status: str


class WarrantyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contact_id: UUID
    contact_name: str | None = None
    item: str
    installed_at: datetime
    expires_at: datetime
    status: str


class WarrantyStatusUpdate(BaseModel):
    status: str  # active | expired | voided


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    description: str
    category: str
    amount: float
    expense_date: datetime


class ExpenseCreate(BaseModel):
    description: str
    category: str
    amount: float


class SiteLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contact_id: UUID
    contact_name: str | None = None
    title: str
    status: str
    closed_at: datetime | None = None


class SiteLogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    site_id: UUID
    note: str
    entry_date: datetime


# ── Helpers ────────────────────────────────────────────────────────────────


async def _contact_name(db: AsyncSession, contact_id: UUID) -> str | None:
    contact = (
        await db.execute(select(Contact).where(Contact.id == contact_id))
    ).scalar_one_or_none()
    return contact.name if contact else None


# ── Inventario ────────────────────────────────────────────────────────────


@router.get("/inventory", response_model=list[InventoryItemOut])
async def list_inventory(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InventoryItemOut]:
    """Materiales del negocio: qué hay, cuánto queda y qué está bajo mínimo."""
    items = (
        (
            await db.execute(
                select(InventoryItem)
                .where(
                    InventoryItem.tenant_id == _user.tenant_id,
                    InventoryItem.is_active.is_(True),
                )
                .order_by(InventoryItem.name.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        InventoryItemOut(
            id=i.id,
            name=i.name,
            unit=i.unit,
            quantity=float(i.quantity),
            min_quantity=float(i.min_quantity),
            is_active=i.is_active,
            updated_at=i.updated_at,
        )
        for i in items
    ]


@router.put("/inventory/{item_id}/adjust", response_model=InventoryItemOut)
async def adjust_inventory(
    item_id: UUID,
    body: InventoryAdjust,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InventoryItemOut:
    """Ajusta el stock: delta positivo entra, negativo sale. Nunca bajo 0."""
    item = (
        await db.execute(
            select(InventoryItem).where(
                InventoryItem.tenant_id == current_user.tenant_id,
                InventoryItem.id == item_id,
                InventoryItem.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ítem no encontrado"
        )

    new_qty = float(item.quantity) + body.delta
    if new_qty < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No hay suficiente stock: tienes {item.quantity} {item.unit}",
        )
    item.quantity = Decimal(str(new_qty))
    await db.commit()
    await db.refresh(item)
    return InventoryItemOut(
        id=item.id,
        name=item.name,
        unit=item.unit,
        quantity=float(item.quantity),
        min_quantity=float(item.min_quantity),
        is_active=item.is_active,
        updated_at=item.updated_at,
    )


# ── Mantenimiento preventivo ──────────────────────────────────────────────


@router.get("/maintenance", response_model=list[MaintenanceOut])
async def list_maintenance(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MaintenanceOut]:
    """Mantenimientos del negocio, ordenados por próxima fecha."""
    items = (
        (
            await db.execute(
                select(Maintenance)
                .where(
                    Maintenance.tenant_id == _user.tenant_id,
                    Maintenance.status == "active",
                )
                .order_by(Maintenance.next_due.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        MaintenanceOut(
            id=m.id,
            contact_id=m.contact_id,
            contact_name=await _contact_name(db, m.contact_id),
            description=m.description,
            frequency_days=m.frequency_days,
            next_due=m.next_due,
            status=m.status,
        )
        for m in items
    ]


# ── Garantías ──────────────────────────────────────────────────────────────


@router.get("/warranties", response_model=list[WarrantyOut])
async def list_warranties(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WarrantyOut]:
    """Garantías activas, la más próxima a vencer primero."""
    items = (
        (
            await db.execute(
                select(Warranty)
                .where(
                    Warranty.tenant_id == _user.tenant_id,
                    Warranty.status == "active",
                )
                .order_by(Warranty.expires_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        WarrantyOut(
            id=w.id,
            contact_id=w.contact_id,
            contact_name=await _contact_name(db, w.contact_id),
            item=w.item,
            installed_at=w.installed_at,
            expires_at=w.expires_at,
            status=w.status,
        )
        for w in items
    ]


@router.put("/warranties/{warranty_id}/status", response_model=WarrantyOut)
async def update_warranty_status(
    warranty_id: UUID,
    body: WarrantyStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarrantyOut:
    """Marca una garantía como vencida o anulada."""
    if body.status not in ("active", "expired", "voided"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Estado inválido: active, expired o voided",
        )
    w = (
        await db.execute(
            select(Warranty).where(
                Warranty.tenant_id == current_user.tenant_id,
                Warranty.id == warranty_id,
            )
        )
    ).scalar_one_or_none()
    if w is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Garantía no encontrada"
        )
    w.status = body.status
    await db.commit()
    await db.refresh(w)
    return WarrantyOut(
        id=w.id,
        contact_id=w.contact_id,
        contact_name=await _contact_name(db, w.contact_id),
        item=w.item,
        installed_at=w.installed_at,
        expires_at=w.expires_at,
        status=w.status,
    )


# ── Gastos personales ──────────────────────────────────────────────────────


@router.get("/expenses", response_model=list[ExpenseOut])
async def list_expenses(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ExpenseOut]:
    """Gastos del dueño, los más recientes primero."""
    items = (
        (
            await db.execute(
                select(Expense)
                .where(Expense.tenant_id == _user.tenant_id)
                .order_by(Expense.expense_date.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        ExpenseOut(
            id=e.id,
            description=e.description,
            category=e.category,
            amount=float(e.amount),
            expense_date=e.expense_date,
        )
        for e in items
    ]


@router.post("/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create_expense(
    body: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseOut:
    """Registra un gasto desde el panel (igual que por chat)."""
    e = Expense(
        tenant_id=current_user.tenant_id,
        description=body.description.strip(),
        category=body.category.strip(),
        amount=Decimal(str(body.amount)),
        expense_date=datetime.now(UTC),
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return ExpenseOut(
        id=e.id,
        description=e.description,
        category=e.category,
        amount=float(e.amount),
        expense_date=e.expense_date,
    )


# ── Bitácora de obra ──────────────────────────────────────────────────────


@router.get("/site-log", response_model=list[SiteLogOut])
async def list_site_logs(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=30, ge=1, le=100),
) -> list[SiteLogOut]:
    """Días de obra registrados, los más recientes primero."""
    items = (
        (
            await db.execute(
                select(SiteLog)
                .where(SiteLog.tenant_id == _user.tenant_id)
                .order_by(SiteLog.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        SiteLogOut(
            id=s.id,
            contact_id=s.contact_id,
            contact_name=await _contact_name(db, s.contact_id),
            title=s.title,
            status=s.status,
            closed_at=s.closed_at,
        )
        for s in items
    ]
