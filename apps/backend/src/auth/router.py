"""
Auth HTTP routes.

POST /auth/signup  — create account, return access token + set refresh cookie
POST /auth/login   — authenticate, return access token + set refresh cookie
POST /auth/refresh — rotate refresh token, return new access token
POST /auth/logout  — revoke refresh token, clear cookie
GET  /auth/me      — return current user profile
"""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from src.auth import service
from src.auth.models import AuthResponse, LoginRequest, SignupRequest, UserResponse
from src.middleware.auth_middleware import get_current_user
from src.middleware.rate_limit import rate_limit

router = APIRouter()

REFRESH_COOKIE = "refresh_token"
COOKIE_OPTS: dict = dict(
    key=REFRESH_COOKIE,
    httponly=True,
    samesite="lax",
    secure=False,   # set to True in production (HTTPS)
    path="/auth",
    max_age=7 * 24 * 3600,
)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(value=token, **COOKIE_OPTS)


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path="/auth")


# ─── Signup ───────────────────────────────────────────────────────────────────

@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
)
async def signup(payload: SignupRequest, response: Response) -> AuthResponse:
    try:
        auth_resp, refresh_token = await service.signup(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    _set_refresh_cookie(response, refresh_token)
    return auth_resp


# ─── Login ────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Authenticate and receive tokens",
    dependencies=[Depends(rate_limit(max_requests=100, window_seconds=60, key_prefix="login"))],
)
async def login(payload: LoginRequest, response: Response) -> AuthResponse:
    try:
        auth_resp, refresh_token = await service.login(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        )

    _set_refresh_cookie(response, refresh_token)
    return auth_resp


# ─── Refresh ──────────────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Rotate refresh token and get new access token",
)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> AuthResponse:
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided.",
        )
    try:
        auth_resp, new_refresh_token = await service.refresh_tokens(refresh_token)
    except ValueError as exc:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        )

    _set_refresh_cookie(response, new_refresh_token)
    return auth_resp


# ─── Logout ───────────────────────────────────────────────────────────────────

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke refresh token and clear cookie",
)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> None:
    if refresh_token:
        await service.logout(refresh_token)
    _clear_refresh_cookie(response)


# ─── Me ───────────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user",
)
async def me(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    return current_user
