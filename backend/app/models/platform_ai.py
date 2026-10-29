"""Configuración dinámica de IA a nivel de plataforma (super admin).

Clave-valor simple: el guardián LLM y/o el super admin pueden cambiar proveedores/modelos
sin tocar .env ni reiniciar. Sin tenant_id: es configuración global.
"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PlatformAIConfig(Base, TimestampMixin):
    """Configuración dinámica de IA (proveedores, modelos, claves).

    Keys soportados:
    - LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_MODEL_INTENT, LLM_MODEL_VISION
    - STT_API_KEY, STT_BASE_URL, STT_MODEL
    - TTS_API_KEY, TTS_BASE_URL, TTS_MODEL, TTS_VOICE
    """
    __tablename__ = "platform_ai_config"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    # Metadatos para UI y validación
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_secret: Mapped[bool] = mapped_column(default=False)
    value_type: Mapped[str] = mapped_column(String(20), default="string")