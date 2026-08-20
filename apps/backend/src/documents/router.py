from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List
import structlog

from src.database import db
from src.middleware.auth_middleware import get_current_user
from src.auth.models import UserResponse

log = structlog.get_logger()
router = APIRouter()

class DocumentCreate(BaseModel):
    title: str

class DocumentResponse(BaseModel):
    id: str
    workspaceId: str
    creatorId: str
    title: str
    content: str
    revision: int

@router.post("/{workspace_id}", response_model=DocumentResponse)
async def create_document(workspace_id: str, payload: DocumentCreate, user: UserResponse = Depends(get_current_user)):
    """Create a new document in a workspace."""
    member = await db.workspacemember.find_first(
        where={
            "workspaceId": workspace_id,
            "userId": user.id
        }
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    
    doc = await db.document.create(
        data={
            "title": payload.title,
            "workspaceId": workspace_id,
            "creatorId": user.id,
            "content": "[]"  # Empty Yjs update list
        }
    )
    return doc

@router.get("/{workspace_id}", response_model=List[DocumentResponse])
async def list_documents(workspace_id: str, user: UserResponse = Depends(get_current_user)):
    """List documents in a workspace."""
    member = await db.workspacemember.find_first(
        where={
            "workspaceId": workspace_id,
            "userId": user.id
        }
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
        
    docs = await db.document.find_many(
        where={"workspaceId": workspace_id},
        order={"updatedAt": "desc"}
    )
    return docs

@router.get("/{workspace_id}/{document_id}", response_model=DocumentResponse)
async def get_document(workspace_id: str, document_id: str, user: UserResponse = Depends(get_current_user)):
    """Get a single document."""
    member = await db.workspacemember.find_first(
        where={
            "workspaceId": workspace_id,
            "userId": user.id
        }
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
        
    doc = await db.document.find_first(
        where={"id": document_id, "workspaceId": workspace_id}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    return doc
