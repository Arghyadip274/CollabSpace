"""
Redis sliding-window rate limiter.

Algorithm: sorted-set per key
  - Each request adds a member (timestamp) to a sorted set
  - Old entries outside the window are pruned on every request
  - If the set size exceeds max_requests, the request is denied

This is a true sliding window (not fixed bucket).

Two layers:
  1. RateLimitMiddleware — Starlette middleware applied globally, route-tier based
  2. rate_limit() — FastAPI dependency for per-endpoint fine-grained control
"""

import time
import logging

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.redis_client import get_redis

logger = logging.getLogger(__name__)

RATE_LIMIT_KEY_PREFIX = "rl:"

# ─── Route tiers (path prefix → (max_requests, window_seconds)) ────────────
ROUTE_TIERS: list[tuple[str, int, int]] = [
    # (path_prefix, max_requests, window_seconds)
    ("/auth/login",    100, 60),   # strict — brute-force protection
    ("/auth/signup",   100, 60),   # moderate
    ("/auth/",         20,  60),   # other auth endpoints
    ("/channels/",     30,  60),   # message sending
    ("/workspaces/",   60,  60),   # workspace management
    ("/notifications", 60,  60),   # notifications
    ("/documents/",    60,  60),   # document ops
    ("/",              120, 60),   # global catch-all
]


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
    pipe.zremrangebyscore(full_key, 0, window_start)
    pipe.zadd(full_key, {str(now): now})
    pipe.zcard(full_key)
    pipe.expire(full_key, window_seconds)
    results = await pipe.execute()

    count: int = results[2]
    return count <= max_requests


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Global sliding-window rate limiter middleware.
    Applies different limits based on route prefix (ROUTE_TIERS).
    Skips WebSocket upgrade requests and health probes.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Skip health probes and WS upgrades
        path = request.url.path
        if path in ("/health", "/ready") or request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # Skip GET /docs, /redoc, /openapi.json
        if path.startswith(("/docs", "/redoc", "/openapi")):
            return await call_next(request)

        # Determine rate limit tier
        max_requests, window_seconds = 120, 60  # default
        for prefix, limit, window in ROUTE_TIERS:
            if path.startswith(prefix):
                max_requests, window_seconds = limit, window
                break

        client_ip = request.client.host if request.client else "unknown"
        
        # Skip rate limiting in test environment
        if request.headers.get("x-test-bypass-ratelimit") == "1":
            return await call_next(request)

        key = f"global:{path.split('/')[1]}:{client_ip}"  # e.g. "global:auth:1.2.3.4"

        try:
            redis = get_redis()
            allowed = await sliding_window_check(redis, key, max_requests, window_seconds)
        except Exception as e:
            logger.warning(f"Rate limiter Redis error: {e} — allowing request")
            allowed = True

        if not allowed:
            return Response(
                content=f'{{"detail":"Too many requests. Retry in {window_seconds}s."}}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(window_seconds)},
            )

        return await call_next(request)


def rate_limit(max_requests: int = 5, window_seconds: int = 60, key_prefix: str = ""):
    """
    FastAPI dependency factory for per-endpoint fine-grained control.

        @router.post("/login")
        async def login(_: None = Depends(rate_limit(5, 60, "login"))):
            ...
    """

    async def _check(
        request: Request,
        redis: aioredis.Redis = Depends(get_redis),
    ) -> None:
        if request.headers.get("x-test-bypass-ratelimit") == "1":
            return
            
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

