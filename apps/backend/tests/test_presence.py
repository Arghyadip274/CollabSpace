"""
Presence tracking end-to-end test for Phase 4.

Tests:
1. User A connects, sends heartbeat -> sets presence key in Redis
2. User B connects to same workspace room
3. User A sends presence_update -> User B receives it via Redis Pub/Sub
4. User A disconnects (no more heartbeats)
5. After 25-30 seconds, User B receives offline event from presence monitor

Run: python -u tests/test_presence.py
"""
import asyncio
import httpx
import websockets
import json
import sys

async def drain_until(ws, target_type: str, timeout: float = 5.0):
    """Drain messages until one of the target type, or raise TimeoutError."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        remaining = deadline - asyncio.get_event_loop().time()
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 1.0))
            data = json.loads(msg)
            print(f"  << {data.get('type')}", flush=True)
            if data.get("type") == target_type:
                return data
        except asyncio.TimeoutError:
            pass
    raise TimeoutError(f"Did not receive '{target_type}' within {timeout}s")


async def run_test():
    print("=== Phase 4 Presence Test ===", flush=True)
    base = "http://127.0.0.1:8000"
    ws_base = "ws://127.0.0.1:8000"

    async with httpx.AsyncClient(base_url=base) as client:
        # ── Create users ──────────────────────────────────────────────────
        print("\n[1] Creating users...", flush=True)
        r = await client.post("/auth/signup", json={"email": "presence_a@test.com", "password": "Password123!", "name": "Alice"})
        if r.status_code != 201:
            r = await client.post("/auth/login", json={"email": "presence_a@test.com", "password": "Password123!"})
        token_a = r.json()["access_token"]
        print("  Alice logged in", flush=True)

        r = await client.post("/auth/signup", json={"email": "presence_b@test.com", "password": "Password123!", "name": "Bob"})
        if r.status_code != 201:
            r = await client.post("/auth/login", json={"email": "presence_b@test.com", "password": "Password123!"})
        token_b = r.json()["access_token"]
        print("  Bob logged in", flush=True)

        # ── Create workspace ──────────────────────────────────────────────
        print("\n[2] Setting up workspace...", flush=True)
        r = await client.post("/workspaces", json={"name": "Presence Test WS"}, headers={"Authorization": f"Bearer {token_a}"})
        ws_id = r.json()["id"]
        print(f"  Workspace: {ws_id}", flush=True)

        await client.post(
            f"/workspaces/{ws_id}/invite",
            json={"email": "presence_b@test.com", "role": "MEMBER"},
            headers={"Authorization": f"Bearer {token_a}"}
        )
        print("  Bob invited", flush=True)

        room = f"workspace_{ws_id}"

        # ── Phase A: Connect both, verify presence_update propagates ──────
        print("\n[3] Connecting Alice and Bob to room...", flush=True)
        async with (
            websockets.connect(f"{ws_base}/realtime/ws?token={token_a}") as ws_a,
            websockets.connect(f"{ws_base}/realtime/ws?token={token_b}") as ws_b,
        ):
            # Both join the workspace room
            await ws_a.send(json.dumps({"type": "join_room", "room_id": room}))
            await ws_b.send(json.dumps({"type": "join_room", "room_id": room}))

            # Drain join ACKs
            await drain_until(ws_a, "ack")
            await drain_until(ws_b, "ack")
            print("  Both joined room", flush=True)

            # Alice sends heartbeat (sets presence key in Redis with 20s TTL)
            await ws_a.send(json.dumps({"type": "heartbeat", "room_id": room}))
            await drain_until(ws_a, "ack")
            print("  Alice heartbeat sent", flush=True)

            # Alice broadcasts presence_update -> should arrive at Bob via Redis Pub/Sub
            await ws_a.send(json.dumps({"type": "presence_update", "room_id": room, "status": "online"}))
            print("  Alice sent presence_update 'online'", flush=True)

            # Bob should receive it
            try:
                data = await drain_until(ws_b, "presence_update", timeout=5.0)
                print(f"  ✓ Bob received presence_update: {data}", flush=True)
            except TimeoutError:
                print("  ✗ FAIL: Bob did NOT receive presence_update", flush=True)
                sys.exit(1)

            # Create a channel and test messaging
            print("\n[4] Testing messaging...", flush=True)
            r = await client.post(
                f"/workspaces/{ws_id}/channels",
                json={"name": "test-channel", "type": "PUBLIC"},
                headers={"Authorization": f"Bearer {token_a}"}
            )
            ch_id = r.json()["id"]
            print(f"  Channel: {ch_id}", flush=True)

            # Bob joins channel room
            ch_room = f"channel_{ch_id}"
            await ws_b.send(json.dumps({"type": "join_room", "room_id": ch_room}))
            await drain_until(ws_b, "ack")

            # Alice sends message via REST (REST endpoint broadcasts to Redis)
            await client.post(
                f"/channels/{ch_id}/messages",
                json={"content": "Hello Bob from Alice!"},
                headers={"Authorization": f"Bearer {token_a}"}
            )
            print("  Alice sent message via REST", flush=True)

            # Bob should receive it
            try:
                data = await drain_until(ws_b, "new_message", timeout=5.0)
                print(f"  ✓ Bob received message: {data['message']['content']}", flush=True)
            except TimeoutError:
                print("  ✗ FAIL: Bob did NOT receive message", flush=True)
                sys.exit(1)

            # Alice sends typing indicator
            await ws_a.send(json.dumps({"type": "typing_indicator", "room_id": ch_room}))
            try:
                data = await drain_until(ws_b, "typing_indicator", timeout=5.0)
                print(f"  ✓ Bob received typing indicator from: {data['user_name']}", flush=True)
            except TimeoutError:
                print("  ✗ FAIL: Bob did NOT receive typing_indicator", flush=True)
                sys.exit(1)

        # Alice's WS is now closed (context manager exited)
        print("\n[5] Alice disconnected. Waiting for offline broadcast (~25s)...", flush=True)
        print("    (Presence TTL=20s, monitor polls every 5s)", flush=True)

        async with websockets.connect(f"{ws_base}/realtime/ws?token={token_b}") as ws_b2:
            await ws_b2.send(json.dumps({"type": "join_room", "room_id": room}))
            await drain_until(ws_b2, "ack")
            
            try:
                async with asyncio.timeout(35):
                    while True:
                        msg = await ws_b2.recv()
                        data = json.loads(msg)
                        print(f"  << {data.get('type')}: {data}", flush=True)
                        if data.get("type") == "presence_update" and data.get("status") == "offline":
                            print(f"\n  ✓ SUCCESS! Bob received offline event for user: {data['user_id']}", flush=True)
                            break
            except (asyncio.TimeoutError, TimeoutError):
                print("  ✗ FAIL: Did not receive offline event within 35s", flush=True)
                sys.exit(1)

    print("\n=== All Phase 4 tests PASSED ===", flush=True)


if __name__ == "__main__":
    asyncio.run(run_test())
