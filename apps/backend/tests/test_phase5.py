"""
Phase 5 integration tests — Notifications, Rate Limiting, Caching.
"""

import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.database import connect_db, disconnect_db
from src.redis_client import init_redis, close_redis


@pytest_asyncio.fixture(autouse=True)
async def setup_db_and_redis():
    await connect_db()
    await init_redis()
    yield
    await close_redis()
    await disconnect_db()

async def process_notification_queue():
    """Helper to process a single item from the queue synchronously in tests."""
    from src.notifications.service import worker, NOTIFICATION_QUEUE
    from src.redis_client import get_redis
    import json
    
    redis = get_redis()
    raw = await redis.rpop(NOTIFICATION_QUEUE)
    if raw:
        event = json.loads(raw)
        await worker._handle(event)
    else:
        print("DEBUG: Queue was empty when process_notification_queue was called")


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"x-test-bypass-ratelimit": "1"},  # bypass global rate limiter in tests
    ) as ac:
        yield ac


def unique_email(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


async def _signup_and_token(client: AsyncClient, email: str, name: str) -> str:
    resp = await client.post("/auth/signup", json={
        "email": email, "name": name, "password": "Password1!"
    })
    assert resp.status_code == 201
    return resp.json()["access_token"]


# ─── Notification REST API ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unread_count_initially_zero(client: AsyncClient):
    """New user should have 0 unread notifications."""
    token = await _signup_and_token(client, unique_email("notif"), "Notif User")
    resp = await client.get("/notifications/unread-count",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_workspace_invite_creates_notification(client: AsyncClient):
    """Inviting a user to a workspace should create a WORKSPACE_INVITE notification."""
    # Owner creates workspace
    owner_email = unique_email("owner")
    owner_token = await _signup_and_token(client, owner_email, "Owner")

    # Member to be invited
    member_email = unique_email("member")
    member_token = await _signup_and_token(client, member_email, "Member")

    # Create workspace
    ws_resp = await client.post("/workspaces", json={"name": "Notif WS"},
                                 headers={"Authorization": f"Bearer {owner_token}"})
    ws_id = ws_resp.json()["id"]

    # Invite member
    invite_resp = await client.post(
        f"/workspaces/{ws_id}/invite",
        json={"email": member_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert invite_resp.status_code == 201

    # Process the queue manually
    await process_notification_queue()

    # Check member's unread count
    count_resp = await client.get("/notifications/unread-count",
                                   headers={"Authorization": f"Bearer {member_token}"})
    assert count_resp.status_code == 200
    assert count_resp.json()["count"] >= 1

    # List notifications and verify
    list_resp = await client.get("/notifications",
                                  headers={"Authorization": f"Bearer {member_token}"})
    assert list_resp.status_code == 200
    notifications = list_resp.json()["notifications"]
    assert len(notifications) >= 1
    types = [n["type"] for n in notifications]
    assert "WORKSPACE_INVITE" in types


@pytest.mark.asyncio
async def test_mention_creates_notification(client: AsyncClient):
    """Sending a @mention in chat should create a MENTION notification."""
    # Setup two users in a workspace with a channel
    alice_email = unique_email("alice")
    alice_token = await _signup_and_token(client, alice_email, "Alice")

    bob_email = unique_email("bob")
    bob_token = await _signup_and_token(client, bob_email, "Bob")

    # Create workspace and invite Bob
    ws_resp = await client.post("/workspaces", json={"name": "Mention WS"},
                                 headers={"Authorization": f"Bearer {alice_token}"})
    ws_id = ws_resp.json()["id"]
    await client.post(f"/workspaces/{ws_id}/invite",
                      json={"email": bob_email, "role": "MEMBER"},
                      headers={"Authorization": f"Bearer {alice_token}"})

    # Create channel
    ch_resp = await client.post(
        f"/workspaces/{ws_id}/channels",
        json={"name": f"general-{uuid.uuid4().hex[:6]}", "type": "PUBLIC"},
        headers={"Authorization": f"Bearer {alice_token}"}
    )
    ch_id = ch_resp.json()["id"]

    # Alice sends a message mentioning Bob
    await client.post(
        f"/channels/{ch_id}/messages",
        json={"content": "Hey @Bob, check this out!"},
        headers={"Authorization": f"Bearer {alice_token}"}
    )

    # Process the queue manually (once for invite, once for mention)
    await process_notification_queue()
    await process_notification_queue()

    # Bob should have a MENTION notification
    count_resp = await client.get("/notifications/unread-count",
                                   headers={"Authorization": f"Bearer {bob_token}"})
    assert count_resp.json()["count"] >= 1

    list_resp = await client.get("/notifications",
                                  headers={"Authorization": f"Bearer {bob_token}"})
    types = [n["type"] for n in list_resp.json()["notifications"]]
    assert "MENTION" in types


@pytest.mark.asyncio
async def test_mark_notification_read(client: AsyncClient):
    """Marking a notification read should decrement unread count."""
    owner_email = unique_email("mowner")
    owner_token = await _signup_and_token(client, owner_email, "MOwner")

    member_email = unique_email("mmember")
    member_token = await _signup_and_token(client, member_email, "MMember")

    ws_resp = await client.post("/workspaces", json={"name": "Read WS"},
                                 headers={"Authorization": f"Bearer {owner_token}"})
    ws_id = ws_resp.json()["id"]

    await client.post(f"/workspaces/{ws_id}/invite",
                      json={"email": member_email, "role": "MEMBER"},
                      headers={"Authorization": f"Bearer {owner_token}"})

    # Process the queue manually
    await process_notification_queue()

    # Get notifications
    list_resp = await client.get("/notifications",
                                  headers={"Authorization": f"Bearer {member_token}"})
    notifications = list_resp.json()["notifications"]
    assert len(notifications) >= 1
    notif_id = notifications[0]["id"]

    # Mark as read
    read_resp = await client.post(f"/notifications/{notif_id}/read",
                                   headers={"Authorization": f"Bearer {member_token}"})
    assert read_resp.status_code == 200
    assert read_resp.json()["readAt"] is not None

    # Count should decrease
    count_resp = await client.get("/notifications/unread-count",
                                   headers={"Authorization": f"Bearer {member_token}"})
    assert count_resp.json()["count"] == 0


# ─── Caching ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_workspace_member_list_cached(client: AsyncClient):
    """Workspace member list should come from cache on second call (no observable difference but verifies no error)."""
    email = unique_email("cache_ws")
    token = await _signup_and_token(client, email, "Cache WS")

    ws_resp = await client.post("/workspaces", json={"name": "Cache WS"},
                                 headers={"Authorization": f"Bearer {token}"})
    ws_id = ws_resp.json()["id"]

    # First call — populates cache
    resp1 = await client.get(f"/workspaces/{ws_id}",
                              headers={"Authorization": f"Bearer {token}"})
    assert resp1.status_code == 200

    # Second call — should return from cache (same data)
    resp2 = await client.get(f"/workspaces/{ws_id}",
                              headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200
    assert resp1.json()["id"] == resp2.json()["id"]
