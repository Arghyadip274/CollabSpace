"""
Workspace HTTP routes.

GET  /workspaces              — list workspaces the current user belongs to
POST /workspaces              — create a new workspace (caller becomes OWNER)
GET  /workspaces/:id          — get workspace details + member list
POST /workspaces/:id/invite   — invite a registered user by email
"""

from fastapi import APIRouter, Depends, HTTPException, status

from src.auth.models import UserResponse
from src.middleware.auth_middleware import get_current_user
from src.workspaces import service
from src.workspaces.models import (
    CreateWorkspaceRequest,
    InviteRequest,
    WorkspaceMemberResponse,
    WorkspaceResponse,
)

router = APIRouter()


@router.get(
    "",
    response_model=list[WorkspaceResponse],
    summary="List workspaces the current user is a member of",
)
async def list_workspaces(
    current_user: UserResponse = Depends(get_current_user),
) -> list[WorkspaceResponse]:
    return await service.list_workspaces(current_user)


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workspace",
)
async def create_workspace(
    payload: CreateWorkspaceRequest,
    current_user: UserResponse = Depends(get_current_user),
) -> WorkspaceResponse:
    return await service.create_workspace(payload, current_user)


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Get workspace details and member list",
)
async def get_workspace(
    workspace_id: str,
    current_user: UserResponse = Depends(get_current_user),
) -> WorkspaceResponse:
    try:
        return await service.get_workspace(workspace_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{workspace_id}/invite",
    response_model=WorkspaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a registered user to the workspace by email",
)
async def invite_member(
    workspace_id: str,
    payload: InviteRequest,
    current_user: UserResponse = Depends(get_current_user),
) -> WorkspaceMemberResponse:
    try:
        return await service.invite_member(workspace_id, payload, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
