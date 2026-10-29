"""Finanzas personales: ingresos y gastos del dueño con balance de cartera."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Expense(Base, TimestampMixin):
    """
    Movimiento financiero (ingreso o gasto) del dueño.
    
    type: 'income' (ingreso) o 'expense' (gasto)
    El balance de cartera se calcula: sum(incomes) - sum(expenses)
    """
    __tablename__ = "expenses"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Tipo: 'income' = ingreso (dinero que entra), 'expense' = gasto (dinero que sale)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="expense")
    # Descripción: «pago cliente Juliana», «cable THHN #12», «gasolina»
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Categoría: ingresos → 'clientes', 'otros_ingresos';
    # gastos → 'materiales', 'transporte', 'comida', etc.
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    # Monto en COP (siempre positivo)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    # Fecha del movimiento
    expense_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # Referencia opcional: id de cotización, factura, cliente, etc.
    reference_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    # Tipo de referencia: 'quote', 'invoice', 'client', etc.
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Notas adicionales
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class WalletSnapshot(Base, TimestampMixin):
    """
    Snapshot diario del balance de cartera para gráficos históricos.
    Se actualiza automáticamente al final de cada día (via job) o manualmente.
    """
    __tablename__ = "wallet_snapshots"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Fecha del snapshot (día calendario Colombia)
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # Balance total al cierre del día: ingresos - gastos acumulados
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # Ingresos totales acumulados hasta ese día
    total_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # Gastos totales acumulados hasta ese día
    total_expenses: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # Ingresos del día
    daily_income: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Gastos del día
    daily_expenses: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Constraint único por tenant y fecha
    __table_args__ = (
        Index("ix_wallet_snapshots_tenant_date", "tenant_id", "snapshot_date", unique=True),
    )
