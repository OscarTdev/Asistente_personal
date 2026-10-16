"""Gasto personal del dueño: qué gastó, en qué categoría y cuándo."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Expense(Base, TimestampMixin):
    __tablename__ = "expenses"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Descripción: «cable THHN #12», «gasolina para la moto», «almuerzo»
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Categoría auto-detectada: materiales, transporte, comida, etc.
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    # Monto en COP
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    # Fecha del gasto (por defecto hoy)
    expense_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
