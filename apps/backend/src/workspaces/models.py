"""
Pydantic schemas for workspaces and workspace membership.
"""

import re
from typing import Literal

from pydantic import BaseModel, field_validator


# ─── Requests ─────────────────────────────────────────────────────────────────

class CreateWorkspaceRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Workspace name cannot be empty")
        if len(v) > 80:
            raise ValueError("Workspace name must be 80 characters or fewer")
        return v


class InviteRequest(BaseModel):
    email: str
    role: Literal["ADMIN", "MEMBER"] = "MEMBER"


# ─── Responses ────────────────────────────────────────────────────────────────

class WorkspaceMemberResponse(BaseModel):
    user_id: str
    name: str
    email: str
    role: str

    model_config = {"from_attributes": True}


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    owner_id: str
    created_at: str
    members: list[WorkspaceMemberResponse] = []

    model_config = {"from_attributes": True}
