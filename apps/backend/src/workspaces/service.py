"""
Workspace business logic — create, list, invite.
"""

import re

from prisma.errors import UniqueViolationError

from src.auth.models import UserResponse
from src.database import db
from src.workspaces.models import (
    CreateWorkspaceRequest,
    InviteRequest,
    WorkspaceMemberResponse,
    WorkspaceResponse,
)


def _slugify(name: str) -> str:
    """Convert workspace name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = slug.strip("-")
    return slug


def _build_response(workspace, members=None) -> WorkspaceResponse:
    member_list: list[WorkspaceMemberResponse] = []
    if members:
        for m in members:
            member_list.append(
                WorkspaceMemberResponse(
                    user_id=m.userId,
                    name=m.user.name,
                    email=m.user.email,
                    role=m.role,
                )
            )
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        owner_id=workspace.ownerId,
        created_at=workspace.createdAt.isoformat(),
        members=member_list,
    )


async def create_workspace(
    payload: CreateWorkspaceRequest,
    current_user: UserResponse,
) -> WorkspaceResponse:
    """
    Create a workspace and automatically add the creator as OWNER.
    Slug is derived from the name; a suffix is added on collision.
    """
    base_slug = _slugify(payload.name)
    slug = base_slug

    # Handle slug collisions (e.g., "my-team", "my-team-2", ...)
    for suffix in range(1, 100):
        existing = await db.workspace.find_unique(where={"slug": slug})
        if not existing:
            break
        slug = f"{base_slug}-{suffix}"

    workspace = await db.workspace.create(
        data={
            "name": payload.name,
            "slug": slug,
            "ownerId": current_user.id,
            "members": {
                "create": {
                    "userId": current_user.id,
                    "role": "OWNER",
                }
            },
        }
    )
    return _build_response(workspace)


async def list_workspaces(current_user: UserResponse) -> list[WorkspaceResponse]:
    """Return all workspaces the current user is a member of."""
    memberships = await db.workspacemember.find_many(
        where={"userId": current_user.id},
        include={"workspace": True},
    )
    return [_build_response(m.workspace) for m in memberships]


async def get_workspace(
    workspace_id: str,
    current_user: UserResponse,
) -> WorkspaceResponse:
    """
    Fetch a workspace with its members.
    Raises ValueError if not found or user is not a member.
    """
    # Verify membership
    membership = await db.workspacemember.find_unique(
        where={
            "workspaceId_userId": {
                "workspaceId": workspace_id,
                "userId": current_user.id,
            }
        }
    )
    if not membership:
        raise ValueError("Workspace not found or access denied.")

    workspace = await db.workspace.find_unique(where={"id": workspace_id})
    if not workspace:
        raise ValueError("Workspace not found.")

    members = await db.workspacemember.find_many(
        where={"workspaceId": workspace_id},
        include={"user": True},
    )
    return _build_response(workspace, members)


async def invite_member(
    workspace_id: str,
    payload: InviteRequest,
    current_user: UserResponse,
) -> WorkspaceMemberResponse:
    """
    Invite a registered user to the workspace by email.
    Only OWNER or ADMIN can invite.
    Raises ValueError if unauthorized or user not found.
    """
    # Check caller has permission
    caller_membership = await db.workspacemember.find_unique(
        where={
            "workspaceId_userId": {
                "workspaceId": workspace_id,
                "userId": current_user.id,
            }
        }
    )
    if not caller_membership or caller_membership.role not in ("OWNER", "ADMIN"):
        raise PermissionError("Only workspace owners and admins can invite members.")

    # Find target user
    target_user = await db.user.find_unique(where={"email": payload.email})
    if not target_user:
        raise ValueError(f"No account found for email: {payload.email}")

    # Check not already a member
    existing = await db.workspacemember.find_unique(
        where={
            "workspaceId_userId": {
                "workspaceId": workspace_id,
                "userId": target_user.id,
            }
        }
    )
    if existing:
        raise ValueError("User is already a member of this workspace.")

    member = await db.workspacemember.create(
        data={
            "workspaceId": workspace_id,
            "userId": target_user.id,
            "role": payload.role,
        }
    )
    return WorkspaceMemberResponse(
        user_id=member.userId,
        name=target_user.name,
        email=target_user.email,
        role=member.role,
    )
