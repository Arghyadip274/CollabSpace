"""
Async Redis client — singleton with lifespan management.
"""

import redis.asyncio as aioredis
from src.config import settings

_redis: aioredis.Redis | None = None


async def init_redis() -> None:
    """Initialise the Redis connection pool. Called on app startup."""
    global _redis
    _redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    # Verify connectivity
    await _redis.ping()


async def close_redis() -> None:
    """Close the Redis connection. Called on app shutdown."""
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


def get_redis() -> aioredis.Redis:
    """FastAPI dependency — returns the Redis client."""
    if _redis is None:
        raise RuntimeError("Redis not initialised. Call init_redis() first.")
    return _redis
