"""
Phase 1 integration tests — Auth & Workspaces.

Run from apps/backend/:
    pytest tests/ -v

Uses httpx AsyncClient to hit the real FastAPI app.
Requires PostgreSQL + Redis to be running.
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
    """Ensure DB and Redis are connected for each test's event loop."""
    await connect_db()
    await init_redis()
    yield
    await close_redis()
    await disconnect_db()


@pytest_asyncio.fixture
async def client():
    """AsyncClient wired to the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


def unique_email(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


# ─── Auth Tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_signup(client: AsyncClient):
    email = unique_email("signup")
    resp = await client.post("/auth/signup", json={
        "email": email,
        "name": "Test User",
        "password": "Password1!",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == email
    # Refresh token must be in httpOnly cookie
    assert "refresh_token" in resp.cookies


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient):
    email = unique_email("dup")
    # First registration
    resp1 = await client.post("/auth/signup", json={
        "email": email,
        "name": "Dup",
        "password": "Password1!",
    })
    assert resp1.status_code == 201
    # Second should fail with 409 Conflict
    resp2 = await client.post("/auth/signup", json={
        "email": email,
        "name": "Dup2",
        "password": "Password1!",
    })
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    email = unique_email("login")
    # Register first
    await client.post("/auth/signup", json={
        "email": email,
        "name": "Login User",
        "password": "Password1!",
    })
    resp = await client.post("/auth/login", json={
        "email": email,
        "password": "Password1!",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    email = unique_email("wrongpass")
    await client.post("/auth/signup", json={
        "email": email,
        "name": "WP User",
        "password": "Password1!",
    })
    resp = await client.post("/auth/login", json={
        "email": email,
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401  # no token -> 401 Unauthorized


@pytest.mark.asyncio
async def test_me_with_token(client: AsyncClient):
    email = unique_email("me")
    resp = await client.post("/auth/signup", json={
        "email": email,
        "name": "Me User",
        "password": "Password1!",
    })
    token = resp.json()["access_token"]
    resp2 = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["email"] == email


@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient):
    email = unique_email("refresh")
    signup_resp = await client.post("/auth/signup", json={
        "email": email,
        "name": "Refresh User",
        "password": "Password1!",
    })
    assert signup_resp.status_code == 201
    refresh_token = signup_resp.cookies.get("refresh_token")
    assert refresh_token

    # Use refresh token
    client.cookies.set("refresh_token", refresh_token)
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "access_token" in data
    # New refresh cookie should be set
    assert "refresh_token" in refresh_resp.cookies


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    email = unique_email("logout")
    signup_resp = await client.post("/auth/signup", json={
        "email": email,
        "name": "Logout User",
        "password": "Password1!",
    })
    refresh_token = signup_resp.cookies.get("refresh_token")
    assert refresh_token is not None

    client.cookies.set("refresh_token", refresh_token)
    logout_resp = await client.post("/auth/logout")
    assert logout_resp.status_code == 204

    # Refresh token must now be invalid
    client.cookies.set("refresh_token", refresh_token)
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 401


# ─── Workspace Tests ──────────────────────────────────────────────────────────

async def _register_and_token(client: AsyncClient, email: str, name: str) -> str:
    """Helper — sign up and return access token."""
    resp = await client.post("/auth/signup", json={
        "email": email, "name": name, "password": "Password1!",
    })
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_create_workspace(client: AsyncClient):
    email = unique_email("ws_owner")
    token = await _register_and_token(client, email, "WS Owner")
    ws_name = f"Test Workspace {uuid.uuid4().hex[:6]}"
    resp = await client.post(
        "/workspaces",
        json={"name": ws_name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == ws_name
    assert "test-workspace" in data["slug"]
    # Creator is automatically added as OWNER
    assert len(data["members"]) == 0  # members not embedded on create


@pytest.mark.asyncio
async def test_list_workspaces(client: AsyncClient):
    email = unique_email("list_ws")
    token = await _register_and_token(client, email, "List WS")
    await client.post(
        "/workspaces", json={"name": "WS Alpha"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        "/workspaces",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_invite_member(client: AsyncClient):
    owner_email = unique_email("invite_owner")
    owner_token = await _register_and_token(client, owner_email, "Invite Owner")
    
    # Create a second user to invite
    member_email = unique_email("invite_member")
    await client.post("/auth/signup", json={
        "email": member_email,
        "name": "Invite Member",
        "password": "Password1!",
    })

    # Create workspace
    ws_resp = await client.post(
        "/workspaces",
        json={"name": "Invite WS"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    ws_id = ws_resp.json()["id"]

    # Invite the second user
    invite_resp = await client.post(
        f"/workspaces/{ws_id}/invite",
        json={"email": member_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert invite_resp.status_code == 201
    data = invite_resp.json()
    assert data["email"] == member_email
    assert data["role"] == "MEMBER"
