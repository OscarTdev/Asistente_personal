"""Estado global de un servicio (adendo §5): operativo, degradado, caído o
en mantenimiento. El superadmin lo pone a mano; el estado automático se
deriva de los fallos recientes.
"""

from uuid import UUID

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

SERVICE_STATUSES = ("operational", "degraded", "down", "maintenance")


class ServiceStatus(Base, TimestampMixin):
    __tablename__ = "service_status"

    service_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="operational"
    )
    # Mensaje visible para el dueño («Estamos actualizando el cotizador»)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # auto (derivado de fallos) | manual (superadmin)
    source: Mapped[str] = mapped_column(String(10), nullable=False, server_default="auto")
    updated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
