"""Acción pendiente de confirmación del dueño (spec §8.1, §9.1).

El asistente JAMÁS envía nada a un tercero sin confirmación explícita:
la cotización se muestra al dueño ("¿Te la envío?") y solo al confirmar
se envía al cliente. La acción queda en auditoría.
"""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PendingAction(Base, TimestampMixin):
    __tablename__ = "pending_actions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "send_quote" (enviar cotización al cliente)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Payload: quote_id, contact_id, etc.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # "pending" | "confirmed" | "cancelled"
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
