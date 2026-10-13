"""Registro de seguimientos de cotizaciones (follow-ups por WhatsApp)."""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FollowUp(Base, TimestampMixin):
    __tablename__ = "follow_ups"
    __table_args__ = (
        # Anti-spam: un seguimiento por ronda y cotización
        UniqueConstraint("quote_id", "round", name="uq_follow_ups_quote_round"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    quote_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    # 1 = primer recordatorio (día 3) | 2 = cierre (día 7)
    round: Mapped[int] = mapped_column(nullable=False)
    message_sent: Mapped[str] = mapped_column(nullable=False)
