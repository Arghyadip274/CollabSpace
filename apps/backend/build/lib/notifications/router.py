"""
Notification HTTP routes.

GET  /notifications             — list notifications (newest first, cursor-paginated)
GET  /notifications/unread-count — returns {"count": N}
POST /notifications/{id}/read  — mark a notification as read
POST /notifications/read-all   — mark all as read
"""

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from datetime import datetime, timezone

from src.auth.models import UserResponse
from src.middleware.auth_middleware import get_current_user
from src.database import db

router = APIRouter(tags=["Notifications"])


@router.get("/unread-count")
async def get_unread_count(
    current_user: UserResponse = Depends(get_current_user),
):
    """Returns the number of unread notifications for the current user."""
    count = await db.notification.count(
        where={"recipientId": current_user.id, "readAt": None}
    )
    return {"count": count}


@router.get("")
async def list_notifications(
    cursor: Optional[str] = None,
    limit: int = Query(20, le=50),
    current_user: UserResponse = Depends(get_current_user),
):
    """
    Fetch notifications for the current user, newest first (cursor-based pagination).
    """
    query_args: dict[str, Any] = {
        "where": {"recipientId": current_user.id},
        "order": {"createdAt": "desc"},
        "take": limit + 1,
    }
    if cursor:
        query_args["cursor"] = {"id": cursor}
        query_args["skip"] = 1

    notifications = await db.notification.find_many(**query_args)

    has_more = len(notifications) > limit
    if has_more:
        notifications.pop()
        next_cursor = notifications[-1].id
    else:
        next_cursor = None

    return {
        "notifications": notifications,
        "next_cursor": next_cursor,
    }


@router.post("/{notification_id}/read", status_code=status.HTTP_200_OK)
async def mark_read(
    notification_id: str,
    current_user: UserResponse = Depends(get_current_user),
):
    """Mark a single notification as read."""
    notif = await db.notification.find_unique(where={"id": notification_id})
    if not notif or notif.recipientId != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")

    updated = await db.notification.update(
        where={"id": notification_id},
        data={"readAt": datetime.now(timezone.utc)},
    )
    return updated


@router.post("/read-all", status_code=status.HTTP_200_OK)
async def mark_all_read(
    current_user: UserResponse = Depends(get_current_user),
):
    """Mark all notifications for the current user as read."""
    await db.notification.update_many(
        where={"recipientId": current_user.id, "readAt": None},
        data={"readAt": datetime.now(timezone.utc)},
    )
    return {"message": "All notifications marked as read"}
