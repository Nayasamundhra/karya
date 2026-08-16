"""Configuration loading and fail-safe behaviour (spec checks 47-48)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import MIN_JWT_SECRET_LENGTH, Settings

GOOD_SECRET = "a-sufficiently-long-test-secret-key-1234"


def build(**overrides: object) -> Settings:
    """Construct Settings without reading the developer's .env file."""
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 47. A missing JWT secret is handled safely
# ---------------------------------------------------------------------------


def test_missing_secret_is_tolerated_in_local_but_disables_tokens() -> None:
    """A fresh checkout still boots; it simply cannot issue tokens."""
    config = build(environment="local", jwt_secret_key=None)

    assert config.is_auth_configured is False
    # Accessing the key fails loudly rather than falling back to a default.
    with pytest.raises(RuntimeError):
        _ = config.jwt_secret


def test_missing_secret_refuses_to_start_outside_local() -> None:
    for environment in ("production", "staging", "prod"):
        with pytest.raises(ValidationError):
            build(environment=environment, jwt_secret_key=None)


def test_short_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build(environment="production", jwt_secret_key="too-short")

    # Exactly at the boundary is acceptable.
    config = build(
        environment="production", jwt_secret_key="x" * MIN_JWT_SECRET_LENGTH
    )
    assert len(config.jwt_secret) == MIN_JWT_SECRET_LENGTH


def test_secret_is_never_rendered_in_plain_text() -> None:
    config = build(environment="production", jwt_secret_key=GOOD_SECRET)

    assert GOOD_SECRET not in repr(config)
    assert GOOD_SECRET not in str(config)
    assert GOOD_SECRET not in repr(config.jwt_secret_key)
    # Available only via an explicit, deliberate call.
    assert config.jwt_secret == GOOD_SECRET


def test_database_credentials_are_never_rendered_in_plain_text() -> None:
    config = build(
        environment="production",
        jwt_secret_key=GOOD_SECRET,
        postgres_password="super-secret-db-password",
    )

    assert "super-secret-db-password" not in repr(config)
    assert "super-secret-db-password" not in str(config)
    assert "super-secret-db-password" not in config.safe_database_uri
    assert "***" in config.safe_database_uri


# ---------------------------------------------------------------------------
# 48. Configuration loads from the environment
# ---------------------------------------------------------------------------


def test_auth_settings_load_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", GOOD_SECRET)
    monkeypatch.setenv("JWT_ALGORITHM", "HS512")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "45")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.karya.io,http://localhost:5173")

    config = build()

    assert config.jwt_secret == GOOD_SECRET
    assert config.jwt_algorithm == "HS512"
    assert config.access_token_expire_minutes == 45
    assert config.access_token_expire_seconds == 45 * 60
    assert config.refresh_token_expire_days == 7
    assert config.cors_origins == ["https://app.karya.io", "http://localhost:5173"]


def test_defaults_match_the_specification() -> None:
    config = build(environment="local", jwt_secret_key=GOOD_SECRET)

    assert config.jwt_algorithm == "HS256"
    assert config.access_token_expire_minutes == 15
    assert config.access_token_expire_seconds == 900
    assert config.refresh_token_expire_days == 30


def test_non_positive_token_lifetimes_are_rejected() -> None:
    """No unlimited or nonsensical lifetimes."""
    for overrides in (
        {"access_token_expire_minutes": 0},
        {"access_token_expire_minutes": -5},
        {"refresh_token_expire_days": 0},
        {"refresh_token_expire_days": -1},
    ):
        with pytest.raises(ValidationError):
            build(environment="local", jwt_secret_key=GOOD_SECRET, **overrides)


def test_wildcard_cors_origin_is_rejected() -> None:
    """A wildcard is invalid for credentialed requests and unsafe."""
    with pytest.raises(ValidationError):
        build(
            environment="production",
            jwt_secret_key=GOOD_SECRET,
            cors_allowed_origins="*",
        )
    with pytest.raises(ValidationError):
        build(
            environment="production",
            jwt_secret_key=GOOD_SECRET,
            cors_allowed_origins="https://app.karya.io,*",
        )


def test_empty_cors_configuration_allows_no_origin() -> None:
    config = build(environment="local", jwt_secret_key=GOOD_SECRET)

    assert config.cors_origins == []


def test_presence_settings_load_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", GOOD_SECRET)
    monkeypatch.setenv("MAX_GPS_ACCURACY_METERS", "35.5")
    monkeypatch.setenv("QR_CHALLENGE_TTL_SECONDS", "45")

    config = build()

    assert config.max_gps_accuracy_meters == 35.5
    assert config.qr_challenge_ttl_seconds == 45


def test_presence_defaults_match_the_specification() -> None:
    config = build(environment="local", jwt_secret_key=GOOD_SECRET)

    assert config.max_gps_accuracy_meters == 100.0
    assert config.qr_challenge_ttl_seconds == 30


def test_non_positive_presence_thresholds_are_rejected() -> None:
    """A zero TTL or accuracy budget would make verification meaningless."""
    for overrides in (
        {"max_gps_accuracy_meters": 0.0},
        {"max_gps_accuracy_meters": -10.0},
        {"qr_challenge_ttl_seconds": 0},
        {"qr_challenge_ttl_seconds": -30},
    ):
        with pytest.raises(ValidationError):
            build(environment="local", jwt_secret_key=GOOD_SECRET, **overrides)


def test_cors_origins_are_trimmed() -> None:
    config = build(
        environment="local",
        jwt_secret_key=GOOD_SECRET,
        cors_allowed_origins=" https://a.test , https://b.test ,, ",
    )

    assert config.cors_origins == ["https://a.test", "https://b.test"]
