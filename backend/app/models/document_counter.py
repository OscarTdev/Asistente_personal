"""Contador de documentos por negocio: consecutivos COT-0001, CC-0001.

Bloqueo de fila (SELECT FOR UPDATE) al incrementar: dos cotizaciones
simultáneas jamás comparten número.
"""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DocumentCounter(Base, TimestampMixin):
    __tablename__ = "document_counters"
    __table_args__ = (
        UniqueConstraint("tenant_id", "doc_type", name="uq_document_counters_tenant_type"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # "quote" (cotización) o "invoice" (cuenta de cobro)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    last_number: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
