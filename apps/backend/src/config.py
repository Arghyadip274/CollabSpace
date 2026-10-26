"""
Application settings — loaded from .env via pydantic-settings.
All config is accessed through the `settings` singleton.
"""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ACCESS_SECRET = "access-secret-change-me"
DEFAULT_REFRESH_SECRET = "refresh-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/collabspace_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_access_secret: str = DEFAULT_ACCESS_SECRET
    jwt_refresh_secret: str = DEFAULT_REFRESH_SECRET
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # Gemini AI (Phase 6)
    gemini_api_key: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("app_env")
    @classmethod
    def _normalize_app_env(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def _reject_default_secrets_in_production(self) -> "Settings":
        if self.app_env == "production" and (
            not self.jwt_access_secret
            or not self.jwt_refresh_secret
            or self.jwt_access_secret == DEFAULT_ACCESS_SECRET
            or self.jwt_refresh_secret == DEFAULT_REFRESH_SECRET
        ):
            raise ValueError(
                "JWT_ACCESS_SECRET and JWT_REFRESH_SECRET must be set in production"
            )
        return self


settings = Settings()
