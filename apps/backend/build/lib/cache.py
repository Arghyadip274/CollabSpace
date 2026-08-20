"""
Redis caching helpers — Cache-Aside pattern with explicit invalidation.

Strategy: Read-through cache-aside with write-invalidate.
- On READ: check Redis first. On miss → query Postgres → write to Redis with TTL.
- On WRITE: after any mutation, DEL the affected cache key.
  The next read repopulates automatically.

Why not write-through?
  Write-through requires updating the cache atomically with every DB write,
  which is invasive and can cause stale data on partial failures.
  Write-invalidate is simpler, safer, and sufficient for our read-heavy workloads.
"""

import json
import logging
from typing import Any

from src.redis_client import get_redis

logger = logging.getLogger(__name__)

CACHE_PREFIX = "cache:"


def _key(name: str) -> str:
    return f"{CACHE_PREFIX}{name}"


async def get_cached(name: str) -> Any | None:
    """Return the cached value or None on miss."""
    redis = get_redis()
    raw = await redis.get(_key(name))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"Cache decode error for key {name}")
        return None


async def set_cached(name: str, value: Any, ttl: int = 300) -> None:
    """Store value in Redis as JSON with a TTL (seconds)."""
    redis = get_redis()
    try:
        await redis.set(_key(name), json.dumps(value, default=str), ex=ttl)
    except Exception as e:
        logger.warning(f"Cache write error for key {name}: {e}")


async def invalidate(name: str) -> None:
    """Delete a cache entry (call after writes)."""
    redis = get_redis()
    try:
        await redis.delete(_key(name))
        logger.debug(f"Cache invalidated: {name}")
    except Exception as e:
        logger.warning(f"Cache invalidate error for key {name}: {e}")


async def invalidate_many(*names: str) -> None:
    """Delete multiple cache entries at once."""
    redis = get_redis()
    try:
        keys = [_key(n) for n in names]
        await redis.delete(*keys)
    except Exception as e:
        logger.warning(f"Cache bulk invalidate error: {e}")
