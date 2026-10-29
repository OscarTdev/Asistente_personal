"""Configuración de ARQ (cola durable con Redis)."""
from arq.connections import RedisSettings

redis_settings = RedisSettings(
    host="localhost",
    port=6379,
    database=0,
)
