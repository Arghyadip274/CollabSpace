"""
Redis sliding-window rate limiter.

Algorithm: sorted-set per key
  - Each request adds a member (timestamp) to a sorted set
  - Old entries outside the window are pruned on every request
  - If the set size exceeds max_requests, the request is denied

This is a true sliding window (not fixed bucket).
"""

import time

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status

from src.redis_client import get_redis

RATE_LIMIT_KEY_PREFIX = "rl:"


async def sliding_window_check(
    redis: aioredis.Redis,
    key: str,
    max_requests: int,
    window_seconds: int,
) -> bool:
    """
    Returns True if the request is allowed, False if rate-limited.
    Uses a Redis sorted set as a sliding window log.
    """
    now = time.time()
    window_start = now - window_seconds
    full_key = f"{RATE_LIMIT_KEY_PREFIX}{key}"

    pipe = redis.pipeline()
    # Remove requests outside the window
    pipe.zremrangebyscore(full_key, 0, window_start)
    # Add this request
    pipe.zadd(full_key, {str(now): now})
    # Count requests in window
    pipe.zcard(full_key)
    # Auto-expire the key so Redis cleans up idle keys
    pipe.expire(full_key, window_seconds)
    results = await pipe.execute()

    count: int = results[2]
    return count <= max_requests


def rate_limit(max_requests: int = 5, window_seconds: int = 60, key_prefix: str = ""):
    """
    FastAPI dependency factory. Example:

        @router.post("/login")
        async def login(_: None = Depends(rate_limit(5, 60, "login"))):
            ...
    """

    async def _check(
        request: Request,
        redis: aioredis.Redis = Depends(get_redis),
    ) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{key_prefix}:{client_ip}"
        allowed = await sliding_window_check(redis, key, max_requests, window_seconds)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Try again in {window_seconds} seconds.",
                headers={"Retry-After": str(window_seconds)},
            )

    return _check
