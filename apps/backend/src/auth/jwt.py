"""
JWT token operations:
  - Access tokens  : short-lived (15 min), sent in response body
  - Refresh tokens : long-lived (7 days), stored in httpOnly cookie + DB

Rotation strategy:
  On every /auth/refresh the old refresh token is revoked in the DB and a
  brand-new pair is issued.  If a revoked token is used again we know the
  token was stolen and can revoke the entire family.
"""

import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from src.config import settings

ALGORITHM = "HS256"


# ─── Access Tokens ────────────────────────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_expire_minutes
    )
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_access_secret, algorithm=ALGORITHM)


def verify_access_token(token: str) -> str:
    """Decode and validate an access token. Returns user_id on success."""
    try:
        payload = jwt.decode(
            token, settings.jwt_access_secret, algorithms=[ALGORITHM]
        )
        if payload.get("type") != "access":
            raise JWTError("Wrong token type")
        user_id: str = payload["sub"]
        return user_id
    except JWTError as exc:
        raise ValueError(f"Invalid access token: {exc}") from exc


# ─── Refresh Tokens ───────────────────────────────────────────────────────────

def create_refresh_token(user_id: str) -> tuple[str, datetime]:
    """
    Returns (raw_token_string, expires_at).
    The raw string is stored in the DB; we also encode it as a JWT so
    the server can extract user_id without a DB lookup on every refresh.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_expire_days
    )
    # Add jti (JWT ID) to make every token unique even for the same user
    jti = secrets.token_hex(16)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
        "jti": jti,
    }
    token = jwt.encode(payload, settings.jwt_refresh_secret, algorithm=ALGORITHM)
    return token, expire


def verify_refresh_token(token: str) -> str:
    """Decode and validate a refresh token. Returns user_id on success."""
    try:
        payload = jwt.decode(
            token, settings.jwt_refresh_secret, algorithms=[ALGORITHM]
        )
        if payload.get("type") != "refresh":
            raise JWTError("Wrong token type")
        return payload["sub"]
    except JWTError as exc:
        raise ValueError(f"Invalid refresh token: {exc}") from exc
