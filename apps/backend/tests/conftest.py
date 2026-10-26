"""Shared test fixtures."""

import uuid

import pytest_asyncio
from redis import asyncio as aioredis

from src.config import settings


@pytest_asyncio.fixture
async def isolated_notification_queue(monkeypatch):
    """
    Give the test its own uniquely named notification queue key.

    Producers (emit_notification) and consumers both resolve
    NOTIFICATION_QUEUE from the service module at call time, so patching it
    redirects both. Events left in the shared dev Redis by earlier runs or
    other tests can then never be popped in place of this test's own events,
    and this test leaves nothing behind on the real queue.

    Only this test's key is deleted (never FLUSHDB/FLUSHALL), using a
    short-lived client so cleanup does not depend on the app connection.
    """
    import src.notifications.service as notification_service

    key = f"test:{notification_service.NOTIFICATION_QUEUE}:{uuid.uuid4().hex}"
    monkeypatch.setattr(notification_service, "NOTIFICATION_QUEUE", key)
    yield key
    client = aioredis.from_url(settings.redis_url)
    try:
        await client.delete(key)
    finally:
        await client.aclose()
