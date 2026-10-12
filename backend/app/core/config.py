from functools import lru_cache
from pathlib import Path

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

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()