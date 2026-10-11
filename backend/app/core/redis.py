from collections.abc import AsyncIterator

from redis.asyncio import Redis, from_url

from app.core.config import get_settings


async def get_redis() -> AsyncIterator[Redis]:
    """Cliente redis.asyncio por request, cerrado al terminar."""
    redis: Redis = from_url(get_settings().redis_url, decode_responses=True)
    try:
        yield redis
    finally:
        await redis.aclose()
