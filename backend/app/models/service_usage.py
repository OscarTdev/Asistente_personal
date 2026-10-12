"""Registro de interacciones por servicio — alimenta las métricas del panel
(clientes activos, servicios más demandados)."""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ServiceUsage(Base, TimestampMixin):
    __tablename__ = "service_usage"
    __table_args__ = (
        Index(
            "ix_service_usage_tenant_key_created",
            "tenant_id",
            "module_key",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # Servicio que atendió la interacción (ej: "quoter")
    module_key: Mapped[str] = mapped_column(String(50), nullable=False)
    # Cliente implicado, cuando aplica (la interacción puede ser del panel)
    contact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    # Naturaleza de la interacción: extraction | quote_created | pdf | message
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
