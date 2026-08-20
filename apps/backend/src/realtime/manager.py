import asyncio
import json
import logging
import base64
from collections import defaultdict
from fastapi import WebSocket
import redis.asyncio as aioredis

from src.redis_client import get_redis
from src.database import db

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Maps room_id -> set of active WebSockets
        self.active_connections: dict[str, set[WebSocket]] = defaultdict(set)
        
        # Maps room_id -> list of base64 Yjs updates (pending save)
        self.pending_updates: dict[str, list[str]] = defaultdict(list)
        # Maps room_id -> asyncio.Task (for debounced saving)
        self.save_tasks: dict[str, asyncio.Task] = {}
        
        # Background task listening to Redis
        self.pubsub_task: asyncio.Task | None = None
        self.pubsub: aioredis.client.PubSub | None = None
        
        # Background task for presence monitoring
        self.presence_monitor_task: asyncio.Task | None = None

    async def join_room(self, websocket: WebSocket, room_id: str):
        self.active_connections[room_id].add(websocket)
        logger.info(f"WebSocket {websocket.client} joined room {room_id}")
        
        updates = []
        # Only fetch document state for document rooms (not workspace/channel rooms)
        is_doc_room = not (room_id.startswith("workspace_") or room_id.startswith("channel_"))
        if is_doc_room:
            doc_record = await db.document.find_unique(where={"id": room_id})
            if doc_record and doc_record.content:
                try:
                    updates = json.loads(doc_record.content)
                except Exception as e:
                    logger.error(f"Failed to parse document content for {room_id}: {e}")
                    
            # Include any pending updates that haven't been saved yet
            if self.pending_updates[room_id]:
                updates.extend(self.pending_updates[room_id])

        # Send sync state to the connecting client
        await websocket.send_json({
            "type": "sync_step_1",
            "room_id": room_id,
            "updates": updates
        })

    def leave_room(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections and websocket in self.active_connections[room_id]:
            self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
            logger.info(f"WebSocket {websocket.client} left room {room_id}")

    def disconnect_all(self, websocket: WebSocket):
        """Remove a websocket from all rooms it was in."""
        empty_rooms = []
        for room_id, conns in self.active_connections.items():
            if websocket in conns:
                conns.remove(websocket)
                if not conns:
                    empty_rooms.append(room_id)
        for room_id in empty_rooms:
            del self.active_connections[room_id]

    async def _debounced_save(self, room_id: str):
        """Wait 2 seconds, then append pending updates to Postgres."""
        try:
            await asyncio.sleep(2.0)
            
            updates_to_save = self.pending_updates[room_id]
            if not updates_to_save:
                return
                
            # Read existing
            doc_record = await db.document.find_unique(where={"id": room_id})
            existing_updates = []
            if doc_record and doc_record.content:
                try:
                    existing_updates = json.loads(doc_record.content)
                except:
                    pass
                    
            # Combine and save
            combined = existing_updates + updates_to_save
            await db.document.update(
                where={"id": room_id},
                data={"content": json.dumps(combined)}
            )
            
            # Clear pending updates
            self.pending_updates[room_id] = []
            logger.info(f"Saved {len(updates_to_save)} updates for document {room_id} to DB")
        except asyncio.CancelledError:
            # Task was cancelled (because a new update came in)
            pass
        except Exception as e:
            logger.error(f"Failed to save document {room_id} to DB: {e}")

    def trigger_debounced_save(self, room_id: str):
        """Cancel existing save task and start a new one."""
        if room_id in self.save_tasks:
            self.save_tasks[room_id].cancel()
            
        self.save_tasks[room_id] = asyncio.create_task(
            self._debounced_save(room_id)
        )

    async def process_yjs_update(self, room_id: str, update_b64: str):
        """Buffer a Yjs update locally and trigger save."""
        self.pending_updates[room_id].append(update_b64)
        self.trigger_debounced_save(room_id)

    async def broadcast_to_local_room(self, room_id: str, message: dict):
        """Send message to all locally connected sockets in the room."""
        if room_id in self.active_connections:
            # We copy the set in case connections drop during iteration
            for connection in list(self.active_connections[room_id]):
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to {connection.client}: {e}")
                    self.leave_room(connection, room_id)

    async def publish_to_room(self, room_id: str, message: dict):
        """Publish a message to Redis so all servers can broadcast it."""
        redis = get_redis()
        # Publish to room channel
        await redis.publish(f"room:{room_id}", json.dumps(message))

    async def start_redis_listener(self):
        """Background task that listens to Redis Pub/Sub for room messages."""
        redis = get_redis()
        self.pubsub = redis.pubsub()
        # Use pattern subscribe for all rooms
        await self.pubsub.psubscribe("room:*")
        logger.info("Started Redis Pub/Sub listener for rooms")

        try:
            async for message in self.pubsub.listen():
                if message["type"] == "pmessage":
                    channel = message["channel"]
                    if channel.startswith("room:"):
                        room_id = channel.split("room:", 1)[1]
                        try:
                            data = json.loads(message["data"])
                            
                            # If it's a doc update, we buffer it for debounced saving
                            if data.get("type") == "doc_update" and "update" in data:
                                await self.process_yjs_update(room_id, data["update"])
                                
                            await self.broadcast_to_local_room(room_id, data)
                        except json.JSONDecodeError:
                            logger.error(f"Failed to decode message on {channel}: {message['data']}")
        except asyncio.CancelledError:
            logger.info("Redis Pub/Sub listener task cancelled")
        except Exception as e:
            logger.error(f"Redis Pub/Sub listener encountered an error: {e}")
        finally:
            if self.pubsub:
                await self.pubsub.close()

    async def process_heartbeat(self, user_id: str, workspace_id: str):
        """Update the user's presence TTL in Redis."""
        redis = get_redis()
        key = f"presence:{workspace_id}:{user_id}"
        await redis.set(key, "online", ex=20)

    async def start_presence_monitor(self):
        """Periodically check for expired presence TTLs and broadcast offline events."""
        redis = get_redis()
        last_known_state = defaultdict(set)
        
        try:
            while True:
                await asyncio.sleep(5.0)
                
                # Check presence only for workspaces this server has clients for
                for room_id in list(self.active_connections.keys()):
                    if not room_id.startswith("workspace_"):
                        continue
                        
                    workspace_id = room_id.split("workspace_", 1)[1]
                    pattern = f"presence:{workspace_id}:*"
                    keys = await redis.keys(pattern)
                    
                    current_online = set()
                    for key in keys:
                        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                        user_id = key_str.split(":")[-1]
                        current_online.add(user_id)
                        
                    previous_online = last_known_state[workspace_id]
                    
                    # Detect users who are no longer online
                    dropped_users = previous_online - current_online
                    for uid in dropped_users:
                        await self.publish_to_room(
                            room_id, 
                            {"type": "presence_update", "user_id": uid, "status": "offline"}
                        )
                        
                    # Also detect new users to broadcast them, though the heartbeat/presence_update
                    # from the router should already broadcast initial online state.
                    # This serves as a fallback.
                    new_users = current_online - previous_online
                    for uid in new_users:
                        await self.publish_to_room(
                            room_id, 
                            {"type": "presence_update", "user_id": uid, "status": "online"}
                        )
                        
                    last_known_state[workspace_id] = current_online
        except asyncio.CancelledError:
            logger.info("Presence monitor task cancelled")
        except Exception as e:
            logger.error(f"Presence monitor encountered an error: {e}")

manager = ConnectionManager()
