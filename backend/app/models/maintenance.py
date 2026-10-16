"""Mantenimiento preventivo: avisos periódicos a clientes."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Maintenance(Base, TimestampMixin):
    __tablename__ = "maintenances"

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
    # Qué mantener: «limpieza de aire acondicionado», «revisión de tablero»
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Frecuencia en días: 180 = semestral, 90 = trimestral
    frequency_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # Próxima fecha en que el bot debe avisar
    next_due: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # "active" | "paused" | "cancelled"
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active"
    )
    # Última vez que el bot envió el aviso
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
