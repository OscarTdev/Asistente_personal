"""Recordatorio: algo que el bot debe decirle al dueño en una fecha."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Reminder(Base, TimestampMixin):
    __tablename__ = "reminders"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Qué debe recordar el bot: «Llamar a Juliana»
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Cuándo: la fecha/hora en que el bot debe escribirle al dueño
    remind_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # pending → sent (el bot ya avisó) | cancelled
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    # Fecha en que el bot envió el recordatorio principal
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Pre-notificaciones enviadas (2h antes y 30min antes)
    pre_notified_2h: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    pre_notified_30m: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # Evento equivalente en Google Calendar, si la cuenta está conectada.
    google_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_sync_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="local"
    )
