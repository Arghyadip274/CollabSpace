from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import logging
from typing import Optional

from src.auth.jwt import verify_access_token
from src.database import db
from src.realtime.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token for authentication")
):
    # Authenticate via JWT from query param
    try:
        user_id = verify_access_token(token)
    except Exception as e:
        logger.warning(f"WebSocket auth failed: {e}")
        await websocket.close(code=1008, reason="Invalid authentication credentials")
        return

    # Verify user exists in DB
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        logger.warning(f"WebSocket auth failed: user {user_id} not found")
        await websocket.close(code=1008, reason="User not found")
        return

    await websocket.accept()
    logger.info(f"User {user.email} (id: {user.id}) connected to WebSocket")

    # Auto-join the user's personal room for notification delivery
    user_room = f"user_{user.id}"
    manager.active_connections[user_room].add(websocket)

    try:
        while True:
            # We expect JSON payloads in the format {"type": "...", "room_id": "...", "data": "..."}
            data = await websocket.receive_json()
            msg_type = data.get("type")
            room_id = data.get("room_id")
            
            if not msg_type or not room_id:
                await websocket.send_json({"type": "error", "message": "Missing 'type' or 'room_id'"})
                continue

            if msg_type == "join_room":
                await manager.join_room(websocket, room_id)
                await websocket.send_json({"type": "ack", "event": "join_room", "room_id": room_id})

            elif msg_type == "leave_room":
                manager.leave_room(websocket, room_id)
                await websocket.send_json({"type": "ack", "event": "leave_room", "room_id": room_id})

            elif msg_type == "message":
                payload = data.get("data")
                # Construct message object for broadcast
                broadcast_msg = {
                    "type": "message",
                    "room_id": room_id,
                    "sender_id": user.id,
                    "sender_name": user.name,
                    "data": payload
                }
                # Publish to Redis - it will be delivered to local clients via pub/sub task
                await manager.publish_to_room(room_id, broadcast_msg)
                
                # Optionally send ack back to the sender
                if data.get("msg_id"):
                    await websocket.send_json({
                        "type": "ack", 
                        "event": "message", 
                        "msg_id": data["msg_id"]
                    })

            elif msg_type == "doc_update":
                update_b64 = data.get("update")
                if update_b64:
                    broadcast_msg = {
                        "type": "doc_update",
                        "room_id": room_id,
                        "sender_id": user.id,
                        "update": update_b64
                    }
                    await manager.publish_to_room(room_id, broadcast_msg)

            elif msg_type == "heartbeat":
                # Process heartbeat for presence tracking
                # room_id here should be the workspace room e.g., "workspace_{id}"
                if room_id.startswith("workspace_"):
                    workspace_id = room_id.split("workspace_", 1)[1]
                    await manager.process_heartbeat(user.id, workspace_id)
                await websocket.send_json({"type": "ack", "event": "heartbeat"})

            elif msg_type == "presence_update":
                # Explicit presence update from client
                status = data.get("status", "online")
                if room_id.startswith("workspace_"):
                    workspace_id = room_id.split("workspace_", 1)[1]
                    await manager.process_heartbeat(user.id, workspace_id) # Refresh TTL
                await manager.publish_to_room(room_id, {
                    "type": "presence_update",
                    "user_id": user.id,
                    "status": status
                })

            elif msg_type == "typing_indicator":
                # Short-lived event for typing
                await manager.publish_to_room(room_id, {
                    "type": "typing_indicator",
                    "user_id": user.id,
                    "user_name": user.name
                })

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown event type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info(f"User {user.email} disconnected from WebSocket")
        manager.disconnect_all(websocket)
    except Exception as e:
        logger.error(f"WebSocket error for user {user.email}: {e}")
        manager.disconnect_all(websocket)
