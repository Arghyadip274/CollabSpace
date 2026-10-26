"""
The test-only rate-limit bypass must never weaken real rate limiting.

Requires the local Redis from docker-compose.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from src.config import settings
from src.main import app
from src.middleware.rate_limit import RATE_LIMIT_KEY_PREFIX, _bypass_requested
from src.redis_client import close_redis, get_redis, init_redis

# Documentation-range address (RFC 5737): keys the limiter state to this test alone
TEST_CLIENT_IP = "203.0.113.77"
AUTH_TIER_LIMIT = 20  # ("/auth/", 20, 60) in ROUTE_TIERS


def make_request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        }
    )


@pytest.mark.parametrize(
    "app_env, headers, expected",
    [
        ("development", {"x-test-bypass-ratelimit": "1"}, True),
        ("development", {}, False),
        ("development", {"x-test-bypass-ratelimit": "0"}, False),
        ("development", {"x-test-bypass-ratelimit": "true"}, False),
        ("production", {"x-test-bypass-ratelimit": "1"}, False),
        ("production", {}, False),
    ],
)
def test_bypass_only_outside_production(monkeypatch, app_env, headers, expected):
    monkeypatch.setattr(settings, "app_env", app_env)
    assert _bypass_requested(make_request(headers)) is expected


@pytest_asyncio.fixture
async def limiter_redis():
    await init_redis()
    yield get_redis()
    redis = get_redis()
    # delete only the limiter keys created for this test's own client address
    async for key in redis.scan_iter(match=f"{RATE_LIMIT_KEY_PREFIX}*{TEST_CLIENT_IP}*"):
        await redis.delete(key)
    await close_redis()


@pytest.mark.asyncio
async def test_limiter_still_blocks_without_bypass_header(limiter_redis):
    transport = ASGITransport(app=app, client=(TEST_CLIENT_IP, 12345))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        statuses = [(await ac.get("/auth/me")).status_code for _ in range(AUTH_TIER_LIMIT + 5)]
    assert 429 in statuses
    assert statuses.index(429) <= AUTH_TIER_LIMIT


@pytest.mark.asyncio
async def test_header_skips_limiter_outside_production(limiter_redis):
    transport = ASGITransport(app=app, client=(TEST_CLIENT_IP, 12345))
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"x-test-bypass-ratelimit": "1"},
    ) as ac:
        statuses = [(await ac.get("/auth/me")).status_code for _ in range(AUTH_TIER_LIMIT + 5)]
    assert 429 not in statuses


@pytest.mark.asyncio
async def test_header_ignored_in_production(limiter_redis, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    transport = ASGITransport(app=app, client=(TEST_CLIENT_IP, 12345))
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"x-test-bypass-ratelimit": "1"},
    ) as ac:
        statuses = [(await ac.get("/auth/me")).status_code for _ in range(AUTH_TIER_LIMIT + 5)]
    assert 429 in statuses
