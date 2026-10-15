"""Branding del negocio: pie de página y datos bancarios.

El logo vive en almacenamiento de archivos (sub-fase); aquí va lo que
se imprime en cada documento.
"""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TenantBranding(Base, TimestampMixin):
    __tablename__ = "tenant_branding"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # Pie de página personalizado (condiciones, agradecimiento)
    footer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Color principal para el encabezado del PDF (hex: #0f172a)
    primary_color: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Datos bancarios para la cuenta de cobro (cifrados a nivel app en prod)
    bank_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Logo del negocio en los PDFs (PNG normalizado por Pillow en la subida;
    # en la BD para sobrevivir despliegues sin almacenamiento de archivos)
    logo_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_mimetype: Mapped[str | None] = mapped_column(String(50), nullable=True)
