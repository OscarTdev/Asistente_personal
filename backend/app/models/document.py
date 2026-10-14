"""Documento emitido: cotización o cuenta de cobro.

Inmutable: el snapshot guarda los datos exactos con los que se generó.
Si el negocio cambia su nombre, NIT o logo, los PDFs ya emitidos
conservan sus datos originales (spec §10.3).
"""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

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
    # Consecutivo legible: COT-0001, CC-0001
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    # Estado del documento: draft, sent, paid, void
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft"
    )
    # Snapshot inmutable: datos exactos con los que se generó el PDF
    # (nombre del negocio, NIT, ítems, precios, total en letras)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Versión: si se edita y regenera, es una versión nueva
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    # Referencia a la cotización original (para cuenta de cobro)
    quote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )
