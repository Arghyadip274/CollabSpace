"""
Notification service — event-driven via Redis List queue.

Architecture:
  Producer (chat/workspace handlers)
    → LPUSH notifications:queue <JSON event>
  Consumer (NotificationWorker background task)
    → BRPOP notifications:queue
    → write Notification row to Postgres
    → push real-time WS message to online user

Why Redis List over in-process EventEmitter?
- Survives server restarts (Redis persists the queue)
- Decouples producers from consumers
- Horizontally scalable — any instance can consume
- Easy to explain in interviews as a stepping stone to Kafka/SQS
"""

import asyncio
import json
import logging
import re
from typing import Any

from prisma import Json
from src.database import db
from src.redis_client import get_redis

logger = logging.getLogger(__name__)

NOTIFICATION_QUEUE = "notifications:queue"


async def emit_notification(
    *,
    type: str,
    recipient_id: str,
    actor_id: str | None = None,
    payload: dict[str, Any],
) -> None:
    """
    Push a notification event onto the Redis queue.
    Non-blocking — the worker consumes it asynchronously.
    """
    if recipient_id == actor_id:
        return  # Don't notify yourself

    redis = get_redis()
    event = json.dumps({
        "type": type,
        "recipient_id": recipient_id,
        "actor_id": actor_id,
        "payload": payload,
    })
    await redis.lpush(NOTIFICATION_QUEUE, event)
    print(f"DEBUG: emit_notification queued event: {event}")
    logger.debug(f"Notification queued: {type} → {recipient_id}")


MENTION_PATTERN = re.compile(r"@(\w+)")


def extract_mentions(content: str) -> list[str]:
    """Return list of @username strings from message content."""
    return MENTION_PATTERN.findall(content)


async def resolve_mentions(usernames: list[str], workspace_id: str) -> list[str]:
    """
    Resolve @username strings to user IDs within a workspace.
    Returns a list of user IDs.
    """
    if not usernames:
        return []

    # Find users by name who are members of this workspace
    members = await db.workspacemember.find_many(
        where={"workspaceId": workspace_id},
        include={"user": True},
    )

    username_lower = {u.lower() for u in usernames}
    user_ids = []
    for m in members:
        if m.user and m.user.name.lower() in username_lower:
            user_ids.append(m.userId)
    return user_ids


class NotificationWorker:
    """Background task that consumes the Redis notification queue."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self):
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("NotificationWorker started")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _run(self):
        try:
            while self._running:
                await self._process_one()
        except asyncio.CancelledError:
            logger.info("NotificationWorker stopped")
        except Exception as e:
            logger.error(f"NotificationWorker fatal error: {e}")

    async def _process_one(self):
        """BRPOP with 2s timeout so we can check _running flag."""
        redis = get_redis()
        try:
            result = await redis.brpop(NOTIFICATION_QUEUE, timeout=2)
            if result is None:
                return  # timeout, loop continues

            _, raw = result
            event = json.loads(raw)

            await self._handle(event)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"NotificationWorker error processing event: {e}")

    async def _handle(self, event: dict):
        """Write notification to Postgres and push real-time WS if user is online."""
        print(f"DEBUG: NotificationWorker._handle received event: {event}")
        notification_type = event["type"]
        recipient_id = event["recipient_id"]
        actor_id = event.get("actor_id")
        payload = event.get("payload", {})

        # Write to Postgres using scalar fields
        data: dict = {
            "type": notification_type,
            "recipientId": recipient_id,
            "payload": json.dumps(payload),
        }
        if actor_id:
            data["actorId"] = actor_id

        try:
            notif = await db.notification.create(data=data)
            print(f"DEBUG: Notification created successfully: {notif.id}")
            logger.info(f"Notification created: {notif.id} ({notification_type} → {recipient_id})")
        except Exception as e:
            print(f"DEBUG: Failed to create notification: {e}")
            logger.error(f"Failed to create notification: {e}")
            return

        # Push real-time WS to online user via ConnectionManager
        # Import here to avoid circular imports
        from src.realtime.manager import manager

        ws_payload = {
            "type": "notification",
            "notification": {
                "id": notif.id,
                "notificationType": notification_type,
                "actorId": actor_id,
                "payload": payload,
                "createdAt": notif.createdAt.isoformat(),
            },
        }

        # User's personal room is "user_{id}" — if they're connected there
        user_room = f"user_{recipient_id}"
        if user_room in manager.active_connections:
            await manager.broadcast_to_local_room(user_room, ws_payload)
            logger.debug(f"Real-time notification pushed to {recipient_id}")


# Singleton worker instance
worker = NotificationWorker()
