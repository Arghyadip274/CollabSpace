import uuid
import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient, ASGITransport

from src.main import app
from src.database import db
from src.redis_client import init_redis, close_redis

# Utility
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

@pytest.fixture(autouse=True)
def mock_ai_service(monkeypatch):
    """Mock the AI service to avoid real LLM calls during tests."""
    from src.ai.service import AIService
    
    async def mock_summarize_doc(*args, **kwargs):
        return "This is a mocked document summary."
        
    async def mock_summarize_chat(*args, **kwargs):
        return {
            "key_points": ["Mock point 1"],
            "decisions": ["Mock decision 1"],
            "action_items": ["Mock action 1"]
        }
        
    async def mock_generate_embedding(*args, **kwargs):
        # Return a 768-d vector of zeros for testing
        return [0.0] * 768
        
    async def mock_stream_assist(*args, **kwargs):
        yield "This "
        yield "is "
        yield "a mocked response."
        
    async def mock_extract_tasks(*args, **kwargs):
        return [
            {
                "description": "Fix the AI tests",
                "assignee_name": "Alice",
                "due_date": "2026-12-31"
            }
        ]

    monkeypatch.setattr(AIService, "summarize_document", mock_summarize_doc)
    monkeypatch.setattr(AIService, "summarize_chat", mock_summarize_chat)
    monkeypatch.setattr(AIService, "generate_embedding", mock_generate_embedding)
    monkeypatch.setattr(AIService, "stream_writing_assistant", mock_stream_assist)
    monkeypatch.setattr(AIService, "extract_tasks", mock_extract_tasks)

@pytest.mark.asyncio
async def test_summarize_document(client: AsyncClient):
    # Setup user and doc
    email = unique_email("ai_doc")
    token = await _signup_and_token(client, email, "AI Doc User")
    
    ws_resp = await client.post("/workspaces", json={"name": "AI WS"}, headers={"Authorization": f"Bearer {token}"})
    ws_id = ws_resp.json()["id"]
    
    doc_resp = await client.post(f"/documents/{ws_id}", json={"title": "AI Doc"}, headers={"Authorization": f"Bearer {token}"})
    doc_id = doc_resp.json()["id"]
    
    # Test summarization
    resp = await client.post(f"/ai/document/{doc_id}/summarize", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["summary"] == "This is a mocked document summary."

@pytest.mark.asyncio
async def test_extract_tasks(client: AsyncClient):
    # Setup user and workspace
    email = unique_email("alice")
    token = await _signup_and_token(client, email, "Alice")
    
    ws_resp = await client.post("/workspaces", json={"name": "Task WS"}, headers={"Authorization": f"Bearer {token}"})
    ws_id = ws_resp.json()["id"]
    
    # Extract tasks
    resp = await client.post("/ai/extract-tasks", json={
        "content": "Alice, please fix the AI tests by 2026-12-31",
        "workspace_id": ws_id
    }, headers={"Authorization": f"Bearer {token}"})
    
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["description"] == "Fix the AI tests"
    
    # Check DB directly
    db_tasks = await db.task.find_many(where={"workspaceId": ws_id})
    assert len(db_tasks) == 1
    assert db_tasks[0].description == "Fix the AI tests"
