"""Ítem de inventario: qué material, cuánto queda y alerta de mínimo."""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class InventoryItem(Base, TimestampMixin):
    __tablename__ = "inventory_items"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Nombre del material: «Cable THHN #12», «Breaker 30A Schneider»
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Unidad: metros, unidades, cajas, litros, kg...
    unit: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unidades")
    # Cantidad actual en stock
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    # Alerta cuando la cantidad baja de este mínimo
    min_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default="0"
    )
    # Borrado lógico
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
