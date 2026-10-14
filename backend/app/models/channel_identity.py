"""Identidades por canal: el mismo humano en WhatsApp, Telegram o la app.

El núcleo del asistente (conversaciones, notas, cotizaciones,
recordatorios) vive en la base de datos ligado al contacto del tenant; el
canal es solo una puerta. Esta tabla traduce «quién escribe en este canal»
a su contacto — cambiar de canal no le cuesta nada al usuario.
"""

from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ChannelIdentity(Base, TimestampMixin):
    __tablename__ = "channel_identities"
    __table_args__ = (
        # Un identificador externo de un canal apunta a UN contacto
        UniqueConstraint(
            "channel", "external_id", name="uq_channel_identities_channel_external"
        ),
        CheckConstraint("kind IN ('owner', 'contact')", name="kind"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    contact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    # "owner": la identidad del dueño del tenant (le habla a su asistente)
    # "contact": la identidad de un cliente del dueño
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # Canal abierto: hoy "whatsapp"; mañana "telegram" o "web" sin migración
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
