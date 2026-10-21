"""Conexión OAuth de Google por tenant: cada dueño conecta SU cuenta.

Cada negocio conecta su propia cuenta de Google desde el panel (Mi
negocio → Google). Los tokens viven en ESTA fila y jamás cruzan
tenants: todas las consultas filtran por tenant_id (spec §15).

El `state` del flujo OAuth es un JWT corto firmado con el secreto de
la plataforma: ata el consentimiento al tenant que lo inició y bloquea
 tanto CSRF como conexiones cruzadas entre negocios.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class GoogleConnection(Base, TimestampMixin):
    __tablename__ = "google_connections"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # una conexión Google por tenant
    )
    # Email de la cuenta Google conectada
    google_email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Tokens OAuth (nivel de aplicación; el acceso a la fila es por tenant)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    # Google puede omitirlo si ya había consentimiento previo
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cuándo expira el access token (~1 hora)
    token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Alcances concedidos en el consentimiento
    scopes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # False = el refresh falló y el dueño debe reconectar desde el panel
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
