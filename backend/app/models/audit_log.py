"""Auditoría de la plataforma (adendo §4): quién hizo qué, sobre qué
tenant, cuándo y POR QUÉ. El superadmin es encargado del tratamiento de
datos personales (Ley 1581): leer contenido de un cliente exige motivo."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Sin TimestampMixin: la auditoría es inmutable (append-only, sin updated_at)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_log_actor_created", "actor_user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # Quién actuó (superadmin)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    # Sobre qué tenant (None = acción de plataforma, p. ej. cambiar precios)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    # Qué hizo: read_conversations | change_plan | set_status | override | ...
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    # Sobre qué objeto (UUID o tipo:quote:123 — descriptivo)
    object_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # POR QUÉ (obligatorio en lecturas de contenido; adendo §4.3)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(UTC),
    )
