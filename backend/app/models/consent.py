"""Consentimientos: quién aceptó qué política, cuándo y por qué canal.

Ley 1581 de 2012 (Habeas Data): el tratamiento de datos personales
requiere consentimiento previo, expreso e informado. Esta tabla es la
evidencia.
"""

from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Consent(Base, TimestampMixin):
    __tablename__ = "consents"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Quién aceptó (el contacto del dueño)
    contact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Tipo de consentimiento: "privacy_policy", "terms_of_service", etc.
    consent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Versión de la política aceptada (auditable)
    policy_version: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="1.0"
    )
    # Canal por el que aceptó: "whatsapp", "telegram", "web"
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
