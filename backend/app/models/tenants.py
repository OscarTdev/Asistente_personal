import uuid

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    bot_name: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="Aura"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    # Plan de suscripción: trial → freemium (método de pago) → premium (pagado)
    plan: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="trial"
    )
    # WhatsApp del dueño (técnico): con UN número de bot compartido, el webhook
    # identifica quién escribe por este campo y enruta a SU tenant.
    wa_id: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    # Tipo de cuenta: "personal" (persona natural, sin NIT) o "business"
    # (negocio o empresa: se pide NIT con dígito de verificación)
    account_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="personal"
    )
    # NIT con dígito de verificación — solo para cuentas business
    nit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Atención al cliente por chat: apagado por defecto (el bot calla con los
    # clientes del dueño salvo que el negocio lo active)
    customer_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # Tenant de la plataforma: la puerta donde caen los desconocidos
    # (onboarding y soporte). Los datos de la plataforma nunca se mezclan
    # con los de un negocio.
    is_platform: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )