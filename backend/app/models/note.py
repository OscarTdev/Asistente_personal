"""Nota del dueño: apuntes rápidos por chat con borrado lógico."""

from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Note(Base, TimestampMixin):
    __tablename__ = "notes"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # El texto de la nota tal como la dictó el dueño
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Borrado lógico recuperable (spec §13): visible en el panel
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    # Breve etiqueta opcional para búsqueda ("compras", "cliente X")
    tag: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Mini CRM: nota ligada a un cliente concreto (None = nota general por chat)
    contact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
