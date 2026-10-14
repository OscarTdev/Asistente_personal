"""Sesión de onboarding: la máquina de estados del registro por chat.

Un paso a la vez, datos parciales en JSONB, reanudable y con expiración.
El estado vive aquí — no en un string truncado del contacto.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class OnboardingSession(Base, TimestampMixin):
    __tablename__ = "onboarding_sessions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # El contacto del prospecto en el tenant de plataforma
    contact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Paso actual de la máquina: consent, bot_name, account_type, nit,
    # owner_name, city, email, response_pref
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    # Respuestas acumuladas: {"bot_name": "Aura", "account_type": "business", ...}
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # Expiración: sesiones abandonadas se limpian (reanudables mientras vivan)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
