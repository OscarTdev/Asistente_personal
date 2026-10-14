"""Evento de webhook de pagos: guardar primero, procesar después (spec §11).

Idempotencia real: el evento llega, se guarda con su referencia, y el
procesamiento es un paso separado que puede reintentar. Si la referencia
ya existe, no se procesa de nuevo.
"""

from uuid import UUID, uuid4

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PaymentWebhookEvent(Base, TimestampMixin):
    __tablename__ = "payment_webhook_events"
    __table_args__ = (
        # Idempotencia: un mismo evento del proveedor no se procesa dos veces
        UniqueConstraint("provider", "provider_ref", name="uq_payment_events_ref"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # "mercadopago"
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    # Referencia del evento (payment_id)
    provider_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    # "pending" | "processed" | "failed"
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    # Payload crudo del evento (para auditoría y reprocesamiento)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Intentos de procesamiento
    attempts: Mapped[int] = mapped_column(
        nullable=False, server_default="0"
    )
    # Error del último intento (si falló)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
