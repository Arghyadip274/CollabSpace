import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.ai.service import AIService
from src.database import db
from src.middleware.auth_middleware import get_current_user
from src.auth.models import UserResponse

router = APIRouter()

# ─── Summarization ─────────────────────────────────────────────────────────────

import asyncio

class DocSummarizeRequest(BaseModel):
    content: str | None = None

@router.post("/document/{doc_id}/summarize")
async def summarize_document(
    doc_id: str,
    req: DocSummarizeRequest = None,
    current_user: UserResponse = Depends(get_current_user),
):
    # Verify access
    doc = await db.document.find_unique(
        where={"id": doc_id},
        include={"workspace": {"include": {"members": True}}}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    is_member = any(m.userId == current_user.id for m in doc.workspace.members)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a workspace member")
        
    content_to_summarize = doc.content
    revision = doc.revision

    if req and req.content is not None:
        content_to_summarize = req.content
        revision = doc.revision + 1
        await db.document.update(
            where={"id": doc_id},
            data={"content": req.content, "revision": revision}
        )
        
        async def _update_embedding(d_id, text):
            try:
                embedding = await AIService.generate_embedding(text)
                emb_str = f"[{','.join(map(str, embedding))}]"
                await db.execute_raw(f"UPDATE documents SET embedding = '{emb_str}'::vector WHERE id = '{d_id}'")
            except Exception:
                pass
                
        asyncio.create_task(_update_embedding(doc_id, req.content))
        
    summary = await AIService.summarize_document(doc_id, revision, content_to_summarize)
    return {"summary": summary}


class ChatSummarizeRequest(BaseModel):
    since_hours: int = 24

@router.post("/channel/{channel_id}/summarize")
async def summarize_channel(
    channel_id: str,
    req: ChatSummarizeRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    # Verify access
    channel = await db.channel.find_unique(
        where={"id": channel_id},
        include={"workspace": {"include": {"members": True}}}
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    is_member = any(m.userId == current_user.id for m in channel.workspace.members)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a workspace member")
        
    # Get messages
    now = datetime.now(timezone.utc)
    from_date = datetime.fromtimestamp(now.timestamp() - (req.since_hours * 3600), timezone.utc)
    
    messages = await db.message.find_many(
        where={"channelId": channel_id, "createdAt": {"gte": from_date}},
        include={"author": True},
        order={"createdAt": "asc"}
    )
    
    msg_data = [
        {"author_name": m.author.name if m.author else "Unknown", "content": m.content}
        for m in messages
    ]
    
    summary = await AIService.summarize_chat(msg_data)
    return summary


# ─── Writing Assistant ────────────────────────────────────────────────────────

class AssistRequest(BaseModel):
    text: str
    instruction: str

@router.post("/assist")
async def ai_assist(
    req: AssistRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Stream AI suggestions based on instruction."""
    async def event_generator():
        try:
            async for chunk in AIService.stream_writing_assistant(req.text, req.instruction):
                # Send SSE formatted chunk
                yield chunk
        except Exception as e:
            yield f"[ERROR] {str(e)}"
            
    return StreamingResponse(event_generator(), media_type="text/plain")


# ─── Task Extraction ──────────────────────────────────────────────────────────

class ExtractTasksRequest(BaseModel):
    content: str
    workspace_id: str
    source_url: str | None = None

@router.post("/extract-tasks")
async def extract_tasks(
    req: ExtractTasksRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    # Check workspace access
    member = await db.workspacemember.find_unique(
        where={"workspaceId_userId": {"workspaceId": req.workspace_id, "userId": current_user.id}}
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a workspace member")
        
    # Extract tasks
    extracted = await AIService.extract_tasks(req.content)
    
    created_tasks = []
    if extracted:
        # Get members to match names to user IDs
        members = await db.workspacemember.find_many(
            where={"workspaceId": req.workspace_id},
            include={"user": True}
        )
        name_to_id = {m.user.name.lower(): m.userId for m in members if m.user}
        
        for task_data in extracted:
            assignee_id = None
            if task_data.get("assignee_name"):
                name = task_data["assignee_name"].lower()
                assignee_id = name_to_id.get(name)
                
            due_date = None
            if task_data.get("due_date"):
                try:
                    due_date = datetime.strptime(task_data["due_date"], "%Y-%m-%d")
                except ValueError:
                    pass
                    
            task = await db.task.create(
                data={
                    "workspaceId": req.workspace_id,
                    "description": task_data["description"],
                    "assigneeId": assignee_id,
                    "dueDate": due_date,
                    "sourceUrl": req.source_url,
                }
            )
            created_tasks.append(task)
            
    return {"tasks": [t.model_dump(mode='json') for t in created_tasks]}


# ─── Semantic Search ──────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    workspace_id: str
    limit: int = 5

@router.post("/search")
async def semantic_search(
    req: SearchRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    # Check workspace access
    member = await db.workspacemember.find_unique(
        where={"workspaceId_userId": {"workspaceId": req.workspace_id, "userId": current_user.id}}
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a workspace member")
        
    # Generate embedding for query
    embedding = await AIService.generate_embedding(req.query)
    emb_str = f"[{','.join(map(str, embedding))}]"
    
    # Run raw SQL to find closest documents (cosine distance <=>)
    # Cast emb_str to vector
    
    docs = await db.query_raw(f"""
        SELECT id, title, content, 1 - (embedding <=> '{emb_str}'::vector) as similarity
        FROM documents
        WHERE "workspaceId" = '{req.workspace_id}' AND embedding IS NOT NULL
        ORDER BY embedding <=> '{emb_str}'::vector
        LIMIT {req.limit}
    """)
    
    msgs = await db.query_raw(f"""
        SELECT m.id, m.content, c.name as channel_name, 1 - (m.embedding <=> '{emb_str}'::vector) as similarity
        FROM messages m
        JOIN channels c ON m."channelId" = c.id
        WHERE c."workspaceId" = '{req.workspace_id}' AND m.embedding IS NOT NULL
        ORDER BY m.embedding <=> '{emb_str}'::vector
        LIMIT {req.limit}
    """)
    
    return {
        "documents": [dict(d) for d in docs] if docs else [],
        "messages": [dict(m) for m in msgs] if msgs else []
    }
