"""
Application settings — loaded from .env via pydantic-settings.
All config is accessed through the `settings` singleton.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    jwt_access_secret: str = "access-secret-change-me"
    jwt_refresh_secret: str = "refresh-secret-change-me"
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


settings = Settings()
