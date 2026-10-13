from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "wa_id", name="uq_contacts_tenant_wa_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    wa_id: Mapped[str] = mapped_column(String(50), nullable=False)  # teléfono, solo dígitos
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # False = retirado (soft delete): el contacto deja de aparecer por defecto
    # en el panel, pero su historial se conserva (Ley 1581: no borrar datos).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Onboarding conversacional (rol de entrada del bot): estado del registro
    # de un prospecto — "ask_bot_name", "ask_owner_name:<nombre elegido>", None.
    onboarding_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
