"""Servicio de configuración dinámica de IA (nivel plataforma).

Lee/escribe platform_ai_config con fallback a .env. Caché en memoria con TTL
para no golpear la BD en cada request. Usado por servicios LLM/STT/TTS y por el guardián.
"""
import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings as get_env_settings
from app.models import PlatformAIConfig

logger = logging.getLogger(__name__)

# TTL de caché en segundos (5 min)
_CACHE_TTL = 300
_config_cache: dict[str, tuple[str, float]] = {}  # key -> (value, timestamp)


def _cache_get(key: str) -> str | None:
    entry = _config_cache.get(key)
    if entry and time.time() - entry[1] < _CACHE_TTL:
        return entry[0]
    return None


def _cache_set(key: str, value: str) -> None:
    _config_cache[key] = (value, time.time())


def _cache_invalidate(key: str | None = None) -> None:
    if key:
        _config_cache.pop(key, None)
    else:
        _config_cache.clear()


async def get_ai_config(db: AsyncSession, key: str) -> str | None:
    """Obtiene un valor de configuración (BD → .env → None)."""
    # 1. Caché
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # 2. BD
    result = await db.execute(select(PlatformAIConfig).where(PlatformAIConfig.key == key))
    row = result.scalar_one_or_none()
    if row is not None:
        _cache_set(key, row.value)
        return row.value

    # 3. Fallback a .env (Settings)
    env_settings = get_env_settings()
    env_key = key.lower()
    if hasattr(env_settings, env_key):
        val = getattr(env_settings, env_key)
        if val:
            _cache_set(key, val)
            return val

    return None


async def get_all_ai_config(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Devuelve toda la config con metadatos para el panel/guardián."""
    result = await db.execute(select(PlatformAIConfig))
    rows = result.scalars().all()
    out = {}
    for row in rows:
        out[row.key] = {
            "value": row.value,
            "label": row.label,
            "description": row.description,
            "is_secret": row.is_secret,
            "value_type": row.value_type,
        }
    return out


async def set_ai_config(db: AsyncSession, key: str, value: str) -> PlatformAIConfig:
    """Actualiza (upsert) una clave de configuración."""
    result = await db.execute(select(PlatformAIConfig).where(PlatformAIConfig.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        row = PlatformAIConfig(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    await db.commit()
    await db.refresh(row)
    _cache_invalidate(key)
    logger.info("Config IA actualizada: %s", key)
    return row


async def refresh_ai_config_cache() -> None:
    """Invalida toda la caché (útil tras cambios masivos del guardián)."""
    _cache_invalidate()