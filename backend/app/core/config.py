from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"  # raíz del repo


class Settings(BaseSettings):
    # 127.0.0.1 (no "localhost"): el relay de WSL (wslrelay.exe) intercepta [::1]:5433
    database_url: str = "postgresql+psycopg_async://asistente:asistente@127.0.0.1:5433/asistente"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str                      # SIN default → fail-fast
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # LLM: OpenRouter o NVIDIA NIM (interfaz compatible con OpenAI SDK)
    llm_api_key: str = ""            # vacío → IA deshabilitada (no falla el arranque)
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "meta-llama/llama-3.1-70b-instruct"

    # Evolution API (canal WhatsApp) — vacío → el bot no atiende (guard real)
    evolution_api_url: str = "http://127.0.0.1:8080"
    evolution_api_key: str = ""
    evolution_instance: str = "aura"
    # Tenant de la plataforma (Enmienda A): la puerta donde caen los números
    # desconocidos — onboarding y soporte. Sin X-Tenant-Slug: el remitente
    # se resuelve por su número, no por parámetros que controla el emisor.
    platform_tenant_slug: str = "plataforma"
    # URL base del panel para el enlace de un solo uso del onboarding
    panel_base_url: str = "http://localhost:5173"

    # Webhook de WhatsApp: secreto compartido con Evolution (fail-closed,
    # sin él el endpoint responde 401). Se configura como cabecera del
    # webhook en la instancia de Evolution.
    webhook_secret: str = ""

    # Seguimiento de cotizaciones: días de cada ronda (3 y 7 por defecto)
    # y horario permitido en Colombia (UTC-5 fijo: el país no tiene DST)
    followup_days: str = "3,7"
    followup_hours: str = "8,19"

    # Agrupación de mensajes (spec §7): varios seguidos = una respuesta
    debounce_seconds: int = 5
    debounce_max_wait: int = 20

    # Matching del catálogo (pg_trgm): umbral de similitud y brecha de
    # ambigüedad — si dos ítems empatan, no se matchea (mejor confirmar)
    catalog_similarity_threshold: float = 0.30
    catalog_ambiguity_gap: float = 0.05

    # MercadoPago (fase 2): vacíos → el pago sigue siendo manual desde el panel.
    # El webhook de pagos responde 200 pero no procesa hasta que existan.
    mercadopago_access_token: str = ""
    mercadopago_webhook_secret: str = ""
    # URL pública del webhook para incluir en las preferencias (fase 2: túnel/dominio)
    mercadopago_notification_url: str = ""

    # Audio: STT (transcripción) y TTS (síntesis) — cualquier endpoint
    # compatible con OpenAI. STT_API_KEY vacío → el bot pide por escrito.
    stt_api_key: str = ""
    stt_base_url: str = "https://api.groq.com/openai/v1"
    stt_model: str = "whisper-large-v3"
    tts_api_key: str = ""
    tts_base_url: str = "https://api.openai.com/v1"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_strong(cls, value: str) -> str:
        """Fail-fast: un JWT débil o el texto de ejemplo no arrancan."""
        if len(value) < 32 or "cambia-esto" in value.lower():
            raise ValueError(
                "JWT_SECRET inseguro: usa 32+ caracteres aleatorios "
                "(no el texto de .env.example)"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()