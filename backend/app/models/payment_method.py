"""Métodos de pago de un tenant — solo datos tokenizados.

PCI: el número de tarjeta JAMÁS pasa por este servidor; la pasarela entrega
un token y nosotros guardamos brand + últimos 4 dígitos para identificar.
"""

from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PaymentMethod(Base, TimestampMixin):
    __tablename__ = "payment_methods"
    __table_args__ = (
        CheckConstraint("last4 ~ '^[0-9]{4}$'", name="last4_digits"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="manual"
    )
    # Token de la pasarela (o generado en modo manual); nunca datos de tarjeta
    provider_token: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str] = mapped_column(String(30), nullable=False)
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    exp_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exp_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
