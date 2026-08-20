from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, List, Optional
from pydantic import BaseModel
from datetime import datetime
from prisma.enums import ChannelType

from src.middleware.auth_middleware import get_current_user
from src.auth.models import UserResponse
from src.database import db
from src.realtime.manager import manager
from src.notifications.service import emit_notification, extract_mentions, resolve_mentions
import json

router = APIRouter(tags=["Chat"])

# --- Schemas ---

class ChannelCreate(BaseModel):
    name: str
    type: ChannelType = ChannelType.PUBLIC

class MessageCreate(BaseModel):
    content: str

# --- Endpoints ---

@router.post("/workspaces/{workspace_id}/channels")
async def create_channel(
    workspace_id: str,
    channel: ChannelCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    # Verify user is in workspace
    member = await db.workspacemember.find_unique(
        where={"workspaceId_userId": {"workspaceId": workspace_id, "userId": current_user.id}}
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    
    # Check if channel name exists
    existing = await db.channel.find_unique(
        where={"workspaceId_name": {"workspaceId": workspace_id, "name": channel.name}}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Channel name already exists in this workspace")
    
    new_channel = await db.channel.create(
        data={
            "name": channel.name,
            "type": channel.type,
            "workspaceId": workspace_id
        }
    )
    return new_channel

@router.get("/workspaces/{workspace_id}/channels")
async def get_channels(
    workspace_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    # Verify user is in workspace
    member = await db.workspacemember.find_unique(
        where={"workspaceId_userId": {"workspaceId": workspace_id, "userId": current_user.id}}
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    
    channels = await db.channel.find_many(
        where={"workspaceId": workspace_id},
        order={"createdAt": "asc"}
    )
    return channels

@router.post("/channels/{channel_id}/messages")
async def send_message(
    channel_id: str,
    message: MessageCreate,
    current_user: UserResponse = Depends(get_current_user)
):
    # Verify channel exists and user has access
    channel = await db.channel.find_unique(
        where={"id": channel_id},
        include={"workspace": True}
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    # member = await db.workspacemember.find_unique(
    #     where={"workspaceId_userId": {"workspaceId": channel.workspaceId, "userId": current_user.id}}
    # )
    # if not member:
    #     raise HTTPException(status_code=403, detail="Not a member of this workspace")
        
    new_msg = await db.message.create(
        data={
            "content": message.content,
            "channelId": channel_id,
            "authorId": current_user.id
        },
        include={"author": True}
    )

    # Generate embedding in background
    async def _update_embedding(msg_id, text):
        try:
            from src.ai.service import AIService
            embedding = await AIService.generate_embedding(text)
            emb_str = f"[{','.join(map(str, embedding))}]"
            await db.execute_raw(f"UPDATE messages SET embedding = '{emb_str}'::vector WHERE id = '{msg_id}'")
        except Exception as e:
            import structlog
            structlog.get_logger().error("failed_to_generate_message_embedding", error=str(e))
            
    import asyncio
    asyncio.create_task(_update_embedding(new_msg.id, new_msg.content))
    
    # Broadcast message via Redis Pub/Sub to the channel's room
    broadcast_payload = {
        "type": "new_message",
        "room_id": f"channel_{channel_id}",
        "message": {
            "id": new_msg.id,
            "content": new_msg.content,
            "authorId": new_msg.authorId,
            "authorName": new_msg.author.name if new_msg.author else "Unknown",
            "createdAt": new_msg.createdAt.isoformat()
        }
    }
    await manager.publish_to_room(f"channel_{channel_id}", broadcast_payload)
    
    # Detect @mentions and emit notifications asynchronously
    mentions = extract_mentions(message.content)
    if mentions:
        mentioned_user_ids = await resolve_mentions(mentions, channel.workspaceId)
        for uid in mentioned_user_ids:
            await emit_notification(
                type="MENTION",
                recipient_id=uid,
                actor_id=current_user.id,
                payload={
                    "messageId": new_msg.id,
                    "channelId": channel_id,
                    "workspaceId": channel.workspaceId,
                    "preview": message.content[:100],
                },
            )
    
    return new_msg

@router.get("/channels/{channel_id}/messages")
async def get_messages(
    channel_id: str,
    cursor: Optional[str] = None,
    limit: int = Query(50, le=100),
    current_user: UserResponse = Depends(get_current_user)
):
    channel = await db.channel.find_unique(
        where={"id": channel_id}
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    # member = await db.workspacemember.find_unique(
    #     where={"workspaceId_userId": {"workspaceId": channel.workspaceId, "userId": current_user.id}}
    # )
    # if not member:
    #     raise HTTPException(status_code=403, detail="Not a member of this workspace")
        
    query_args: dict[str, Any] = {
        "where": {"channelId": channel_id},
        "order": {"createdAt": "desc"},
        "take": limit + 1,
        "include": {"author": True}
    }
    
    if cursor:
        query_args["cursor"] = {"id": cursor}
        query_args["skip"] = 1
        
    messages = await db.message.find_many(**query_args)
    
    has_more = len(messages) > limit
    if has_more:
        messages.pop()
        next_cursor = messages[-1].id
    else:
        next_cursor = None
        
    return {
        "messages": messages,
        "next_cursor": next_cursor
    }
