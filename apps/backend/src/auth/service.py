"""
Auth business logic — signup, login, refresh, logout.

Refresh token lifecycle:
  1. On login/signup  : create token → store in DB → set httpOnly cookie
  2. On /refresh      : verify JWT → lookup DB (must exist, not revoked)
                        → revoke old → issue new pair → update cookie
  3. On /logout       : revoke DB record → clear cookie
  4. Re-use detection : if a revoked token is used, it means theft;
                        we revoke ALL tokens for that user (future enhancement).
"""

from datetime import datetime, timezone

import bcrypt
from prisma.errors import UniqueViolationError

from src.auth.jwt import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
)
from src.auth.models import AuthResponse, LoginRequest, SignupRequest, UserResponse
from src.database import db


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _user_response(user) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatarUrl,
        created_at=user.createdAt.isoformat(),
    )


async def signup(payload: SignupRequest) -> tuple[AuthResponse, str]:
    """
    Create a new user account.
    Returns (AuthResponse, refresh_token_string).
    Raises ValueError on duplicate email.
    """
    try:
        user = await db.user.create(
            data={
                "email": payload.email,
                "name": payload.name,
                "passwordHash": hash_password(payload.password),
            }
        )
    except UniqueViolationError:
        raise ValueError("An account with this email already exists.")

    return await _issue_tokens(user)


async def login(payload: LoginRequest) -> tuple[AuthResponse, str]:
    """
    Authenticate a user with email + password.
    Returns (AuthResponse, refresh_token_string).
    Raises ValueError on bad credentials.
    """
    user = await db.user.find_unique(where={"email": payload.email})
    if not user or not user.passwordHash:
        raise ValueError("Invalid email or password.")
    if not verify_password(payload.password, user.passwordHash):
        raise ValueError("Invalid email or password.")

    return await _issue_tokens(user)


async def _issue_tokens(user) -> tuple[AuthResponse, str]:
    """Create access + refresh tokens, persist refresh token in DB."""
    access_token = create_access_token(user.id)
    refresh_token, expires_at = create_refresh_token(user.id)

    await db.refreshtoken.create(
        data={
            "token": refresh_token,
            "userId": user.id,
            "expiresAt": expires_at,
        }
    )

    auth_resp = AuthResponse(
        access_token=access_token,
        user=_user_response(user),
    )
    return auth_resp, refresh_token


async def refresh_tokens(old_refresh_token: str) -> tuple[AuthResponse, str]:
    """
    Rotate refresh token:
      verify JWT → look up DB → revoke old → issue new pair.
    Raises ValueError if token is invalid or already revoked.
    """
    # 1. Verify JWT signature + expiry
    try:
        user_id = verify_refresh_token(old_refresh_token)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    # 2. Look up in DB (must exist and not be revoked)
    record = await db.refreshtoken.find_unique(where={"token": old_refresh_token})
    if not record or record.revokedAt is not None:
        raise ValueError("Refresh token has been revoked or does not exist.")

    # 3. Revoke old token
    await db.refreshtoken.update(
        where={"token": old_refresh_token},
        data={"revokedAt": datetime.now(timezone.utc)},
    )

    # 4. Issue new pair
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise ValueError("User not found.")

    return await _issue_tokens(user)


async def logout(refresh_token: str) -> None:
    """Revoke the refresh token in the DB."""
    record = await db.refreshtoken.find_unique(where={"token": refresh_token})
    if record and record.revokedAt is None:
        await db.refreshtoken.update(
            where={"token": refresh_token},
            data={"revokedAt": datetime.now(timezone.utc)},
        )
