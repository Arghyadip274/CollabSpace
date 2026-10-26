"""
Parameterised raw-SQL paths (embedding writes + semantic search).

Requires the local PostgreSQL (pgvector) + Redis from docker-compose.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.ai.service import AIService
from src.database import db
from src.main import app
from src.redis_client import close_redis, init_redis

# Non-zero so cosine distance is defined (a zero vector yields NaN)
VECTOR = [1.0] + [0.0] * 767
INJECTION = "x' OR '1'='1"


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
def fake_embedding(monkeypatch):
    async def _embed(*args, **kwargs):
        return VECTOR

    monkeypatch.setattr(AIService, "generate_embedding", _embed)


async def _signup(client: AsyncClient) -> dict:
    resp = await client.post(
        "/auth/signup",
        json={
            "email": f"sql_{uuid.uuid4().hex[:8]}@example.com",
            "name": "SQL Tester",
            "password": "Password1!",
        },
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _has_embedding(table: str, row_id: str) -> bool:
    rows = await db.query_raw(
        f"SELECT embedding IS NOT NULL AS has FROM {table} WHERE id = $1", row_id
    )
    return bool(rows) and bool(rows[0]["has"])


async def _wait_for_embedding(table: str, row_id: str) -> bool:
    for _ in range(30):
        if await _has_embedding(table, row_id):
            return True
        await asyncio.sleep(0.1)
    return False


@pytest.mark.asyncio
async def test_document_embedding_written_via_params(client):
    headers = await _signup(client)
    ws_id = (await client.post("/workspaces", json={"name": "SQL WS"}, headers=headers)).json()["id"]
    doc_id = (await client.post(f"/documents/{ws_id}", json={"title": "Doc"}, headers=headers)).json()["id"]

    resp = await client.put(
        f"/documents/{ws_id}/{doc_id}", json={"content": "hello embeddings"}, headers=headers
    )
    assert resp.status_code == 200
    assert await _wait_for_embedding("documents", doc_id)


@pytest.mark.asyncio
async def test_message_embedding_written_via_params(client):
    headers = await _signup(client)
    ws_id = (await client.post("/workspaces", json={"name": "SQL WS"}, headers=headers)).json()["id"]
    ch_id = (
        await client.post(f"/workspaces/{ws_id}/channels", json={"name": "general"}, headers=headers)
    ).json()["id"]

    resp = await client.post(f"/channels/{ch_id}/messages", json={"content": "hi"}, headers=headers)
    assert resp.status_code == 200
    assert await _wait_for_embedding("messages", resp.json()["id"])


@pytest.mark.asyncio
async def test_search_returns_embedded_rows(client):
    headers = await _signup(client)
    ws_id = (await client.post("/workspaces", json={"name": "SQL WS"}, headers=headers)).json()["id"]
    doc_id = (await client.post(f"/documents/{ws_id}", json={"title": "Findable"}, headers=headers)).json()["id"]
    await client.put(f"/documents/{ws_id}/{doc_id}", json={"content": "body"}, headers=headers)
    assert await _wait_for_embedding("documents", doc_id)

    resp = await client.post(
        "/ai/search", json={"query": "anything", "workspace_id": ws_id, "limit": 3}, headers=headers
    )
    assert resp.status_code == 200
    assert [d["id"] for d in resp.json()["documents"]] == [doc_id]


@pytest.mark.asyncio
async def test_search_treats_workspace_id_as_data(client):
    headers = await _signup(client)
    resp = await client.post(
        "/ai/search", json={"query": "q", "workspace_id": INJECTION, "limit": 5}, headers=headers
    )
    assert resp.status_code == 403
    # the tables are still intact
    assert await db.query_raw("SELECT 1 AS ok FROM documents LIMIT 1") is not None


@pytest.mark.asyncio
async def test_hostile_id_matches_no_rows_in_update(client):
    """The exact statement shape used by the embedding writers, with a hostile id."""
    emb = f"[{','.join(map(str, VECTOR))}]"
    affected = await db.execute_raw(
        "UPDATE documents SET embedding = $1::vector WHERE id = $2", emb, INJECTION
    )
    assert affected == 0
