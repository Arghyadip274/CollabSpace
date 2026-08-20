"""
Auth middleware — FastAPI dependency that validates the JWT access token
from the Authorization header and attaches the current user to the request.

Usage:
    @router.get("/me")
    async def me(user = Depends(get_current_user)):
        return user
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.jwt import verify_access_token
from src.auth.models import UserResponse
from src.database import db

bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserResponse:
    """
    Extracts JWT from 'Authorization: Bearer <token>' header.
    Returns the authenticated UserResponse or raises 401.
    """
    if not credentials:
        raise CREDENTIALS_EXCEPTION

    try:
        user_id = verify_access_token(credentials.credentials)
    except ValueError:
        raise CREDENTIALS_EXCEPTION

    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise CREDENTIALS_EXCEPTION

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatarUrl,
        created_at=user.createdAt.isoformat(),
    )
