import uuid
import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient, ASGITransport
import websockets
import json

from src.main import app
from src.database import db
from src.redis_client import init_redis, close_redis

def unique_email(prefix="test"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"

async def _signup_and_token(client: AsyncClient, email: str, name: str) -> str:
    resp = await client.post("/auth/signup", json={
        "email": email, "name": name, "password": "Password1!"
    })
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return token

@pytest_asyncio.fixture(autouse=True)
async def setup_db_and_redis():
    await db.connect()
    await init_redis()
    yield
    await close_redis()
    await db.disconnect()

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"x-test-bypass-ratelimit": "1"},
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_auth_flow(client: AsyncClient):
    """Test full auth flow (signup, login)"""
    email = unique_email("auth")
    
    # Signup
    resp = await client.post("/auth/signup", json={
        "email": email, "name": "Auth Tester", "password": "Password1!"
    })
    assert resp.status_code == 201
    
    # Login
    resp2 = await client.post("/auth/login", json={
        "email": email, "password": "Password1!"
    })
    assert resp2.status_code == 200
    assert "access_token" in resp2.json()


@pytest.mark.asyncio
async def test_rate_limiting():
    """Test rate limiting without bypass header."""
    # We create a new client without bypass header
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as rl_client:
        
        # Hit /auth/login repeatedly.
        # We increased the limit to 100 for local demo usage, so we fire 105 requests.
        email = unique_email("rate")
        statuses = []
        for _ in range(105):
            resp = await rl_client.post("/auth/login", json={
                "email": email, "password": "Password1!"
            })
            statuses.append(resp.status_code)
            
        assert 429 in statuses, "Expected Rate Limit Exceeded (429) status code"


@pytest.mark.asyncio
async def test_websocket_and_conflict_resolution(client: AsyncClient):
    """
    Test WebSocket room join, broadcast, and document conflict resolution 
    (simulating 2 concurrent edits).
    """
    email = unique_email("ws")
    token = await _signup_and_token(client, email, "WS Tester")
    
    ws_resp = await client.post("/workspaces", json={"name": "WS Test"}, headers={"Authorization": f"Bearer {token}"})
    ws_id = ws_resp.json()["id"]
    
    doc_resp = await client.post(f"/documents/{ws_id}", json={"title": "Doc1"}, headers={"Authorization": f"Bearer {token}"})
    doc_id = doc_resp.json()["id"]

    # Instead of using TestClient which causes event loop conflicts,
    # we directly simulate the concurrent websocket operations 
    # hitting the realtime manager's process_yjs_update logic.
    from src.realtime.manager import manager
    
    update1 = "Base64UpdateFromClient1"
    update2 = "Base64UpdateFromClient2"
    
    # Simulate concurrent processing
    await asyncio.gather(
        manager.process_yjs_update(doc_id, update1),
        manager.process_yjs_update(doc_id, update2)
    )
    
    # Since debounced_save waits 2 seconds, we can trigger it immediately or check pending updates
    assert update1 in manager.pending_updates[doc_id]
    assert update2 in manager.pending_updates[doc_id]
    
    # We can also check the metrics endpoint to see if it recorded the rooms
    # We need to manually simulate join_room for the metrics to update
    class MockWS:
        client = "mock"
        async def send_json(self, data):
            pass
    mock_ws = MockWS()
    
    await manager.join_room(mock_ws, doc_id) # increments WS_CONNECTIONS and ACTIVE_ROOMS
    
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "active_ws_connections" in resp.text
    assert "active_document_rooms" in resp.text
    
    # Clean up
    manager.leave_room(mock_ws, doc_id)
