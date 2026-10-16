"""Entrada de bitácora: un registro diario dentro de una obra."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SiteLogEntry(Base, TimestampMixin):
    __tablename__ = "site_log_entries"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    site_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("site_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # El registro del día: «Se instaló el tablero, falta conectar fase 3»
    note: Mapped[str] = mapped_column(Text, nullable=False)
    # Fecha del registro (por defecto hoy; puede ser retroactiva)
    entry_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
