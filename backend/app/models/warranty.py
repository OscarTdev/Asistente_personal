"""Garantía de un trabajo: qué se instaló, cuándo y hasta cuándo cubre."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Warranty(Base, TimestampMixin):
    __tablename__ = "warranties"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    contact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Qué se instaló: «Breaker 30A Schneider», «Aire acondicionado LG 12000 BTU»
    item: Mapped[str] = mapped_column(Text, nullable=False)
    # Fecha de instalación
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Fecha en que la garantía vence
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # "active" | "expired" | "voided"
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active"
    )
