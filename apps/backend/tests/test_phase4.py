import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.database import connect_db, disconnect_db
from src.redis_client import init_redis, close_redis
import uuid

def unique_email(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"

@pytest_asyncio.fixture(autouse=True)
async def setup_db_and_redis():
    await connect_db()
    await init_redis()
    yield
    await close_redis()
    await disconnect_db()

@pytest.fixture
def auth_headers():
    return lambda token: {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_chat_rest_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Setup a user and a workspace
        email = unique_email("chatuser")
        res_signup = await ac.post("/auth/signup", json={
            "email": email,
            "password": "Password123!",
            "name": "Chat User"
        })
        token = res_signup.json()["access_token"]
            
        headers = {"Authorization": f"Bearer {token}"}
        
        res_ws = await ac.post("/workspaces", json={"name": "Chat Workspace"}, headers=headers)
        workspace_id = res_ws.json()["id"]
        
        # 2. Create a channel
        res_ch = await ac.post(f"/workspaces/{workspace_id}/channels", json={
            "name": "general",
            "type": "PUBLIC"
        }, headers=headers)
        assert res_ch.status_code == 200
        channel_id = res_ch.json()["id"]
        
        # 3. Get channels
        res_chs = await ac.get(f"/workspaces/{workspace_id}/channels", headers=headers)
        assert res_chs.status_code == 200
        assert len(res_chs.json()) >= 1
        
        # 4. Send messages
        for i in range(15):
            await ac.post(f"/channels/{channel_id}/messages", json={
                "content": f"Message {i}"
            }, headers=headers)
            
        # 5. Get messages with pagination (limit 10)
        res_msgs = await ac.get(f"/channels/{channel_id}/messages?limit=10", headers=headers)
        assert res_msgs.status_code == 200
        data = res_msgs.json()
        assert len(data["messages"]) == 10
        assert data["next_cursor"] is not None
        
        # Get next page
        res_msgs2 = await ac.get(f"/channels/{channel_id}/messages?limit=10&cursor={data['next_cursor']}", headers=headers)
        assert res_msgs2.status_code == 200
        data2 = res_msgs2.json()
        assert len(data2["messages"]) == 5
        assert data2["next_cursor"] is None


