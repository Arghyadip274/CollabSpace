"""Settings validation — no database or Redis required."""

import pytest
from pydantic import ValidationError

from src.config import (
    DEFAULT_ACCESS_SECRET,
    DEFAULT_REFRESH_SECRET,
    Settings,
)

ENV_VARS = ("APP_ENV", "JWT_ACCESS_SECRET", "JWT_REFRESH_SECRET", "CORS_ORIGINS")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make(**overrides) -> Settings:
    # _env_file=None keeps a developer's local .env out of the test
    return Settings(_env_file=None, **overrides)


def test_development_allows_default_secrets():
    s = make()
    assert s.app_env == "development"
    assert s.jwt_access_secret == DEFAULT_ACCESS_SECRET


@pytest.mark.parametrize("env", ["production", "Production", "PRODUCTION", "  production "])
def test_production_rejects_missing_secrets(env):
    # secrets unset -> fall back to the (public) defaults
    with pytest.raises(ValidationError, match="must be set in production"):
        make(app_env=env)


def test_production_rejects_default_access_secret():
    with pytest.raises(ValidationError):
        make(
            app_env="production",
            jwt_access_secret=DEFAULT_ACCESS_SECRET,
            jwt_refresh_secret="x" * 32,
        )


def test_production_rejects_default_refresh_secret():
    with pytest.raises(ValidationError):
        make(
            app_env="production",
            jwt_access_secret="x" * 32,
            jwt_refresh_secret=DEFAULT_REFRESH_SECRET,
        )


def test_production_rejects_empty_secrets():
    with pytest.raises(ValidationError):
        make(app_env="production", jwt_access_secret="", jwt_refresh_secret="y" * 32)


def test_production_accepts_custom_secrets():
    s = make(app_env="Production", jwt_access_secret="a" * 32, jwt_refresh_secret="b" * 32)
    assert s.app_env == "production"


def test_production_reads_secrets_from_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "a" * 32)
    monkeypatch.setenv("JWT_REFRESH_SECRET", "b" * 32)
    assert make().app_env == "production"


def test_cors_origins_parse_as_json_list(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["https://example.test"]')
    assert make().cors_origins == ["https://example.test"]


def test_cors_origins_reject_comma_separated(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test,http://b.test")
    with pytest.raises(Exception):
        make()
