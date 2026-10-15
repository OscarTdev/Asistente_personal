"""Excepción por cliente (adendo §5): el superadmin puede dar o quitar un
servicio a UN negocio concreto, con motivo y vencimiento. Si existe y no
venció, manda sobre el plan."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TenantServiceOverride(Base, TimestampMixin):
    __tablename__ = "tenant_service_overrides"
    __table_args__ = (
        UniqueConstraint("tenant_id", "service_key", name="uq_tenant_service_overrides"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    service_key: Mapped[str] = mapped_column(String(50), nullable=False)
    # True = el superadmin REGALA el servicio; False = se lo quita
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Motivo obligatorio (adendo §4): nada de excepciones anónimas
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # None = sin vencimiento; vencida deja de aplicar
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
