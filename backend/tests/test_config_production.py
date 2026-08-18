"""Production configuration must fail fast, not fail quietly (Phase 7).

Every rule checked here exists because the value that is *convenient* while
developing is dangerous in production, and because a misconfiguration whose only
symptom is a weaker security posture is one nobody notices until it matters.

``test_config.py`` covers the Phase 2 authentication rules. This module covers the
environment separation and the production-only requirements.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Environment, LogFormat, Settings

GOOD_SECRET = "a-sufficiently-long-test-secret-key-1234"
GOOD_PASSWORD = "a-real-production-password"


def build(**overrides: object) -> Settings:
    """Construct Settings without reading the developer's .env file."""
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def production(**overrides: object) -> Settings:
    """A valid production configuration, with ``overrides`` applied."""
    base: dict[str, object] = {
        "environment": "production",
        "jwt_secret_key": GOOD_SECRET,
        "postgres_password": GOOD_PASSWORD,
        "debug": False,
    }
    return build(**{**base, **overrides})


# ---------------------------------------------------------------------------
# Environment separation
# ---------------------------------------------------------------------------


def test_the_four_environments_are_accepted() -> None:
    for name in ("local", "test", "staging", "production"):
        config = production(environment=name)
        assert config.environment is Environment(name)


def test_an_unrecognised_environment_is_rejected() -> None:
    """A typo must not silently behave like development.

    ``prod`` reads as production to a human and is not production to a string
    comparison, which is the whole reason the field is a closed set.
    """
    for name in ("prod", "Production", "production ", "dev", "development", ""):
        with pytest.raises(ValidationError):
            production(environment=name)


def test_is_production_only_true_for_production() -> None:
    assert production().is_production is True
    for name in ("local", "test", "staging"):
        assert production(environment=name).is_production is False


def test_a_valid_production_configuration_is_accepted() -> None:
    """The happy path, so the rules below are known to be the only obstacles."""
    config = production(cors_allowed_origins="https://app.karya.io")

    assert config.is_production
    assert config.cors_origins == ["https://app.karya.io"]
    assert config.jwt_secret == GOOD_SECRET


# ---------------------------------------------------------------------------
# Production-only requirements
# ---------------------------------------------------------------------------


def test_debug_cannot_be_enabled_in_production() -> None:
    """DEBUG is the flag frameworks use to decide whether to expose internals."""
    with pytest.raises(ValidationError):
        production(debug=True)

    # Harmless anywhere else.
    assert build(environment="local", debug=True).debug is True


def test_a_placeholder_secret_is_rejected_in_production() -> None:
    """A deployment that forgot to fill the template in must not start.

    The placeholder is long enough to satisfy the length rule and is published in
    ``.env.example``, so length alone would let it through.
    """
    placeholder = "replace-with-a-long-random-value-min-32-chars"
    assert len(placeholder) >= 32

    with pytest.raises(ValidationError):
        production(jwt_secret_key=placeholder)

    # Still usable locally, where it is a placeholder and nothing more.
    assert build(environment="local", jwt_secret_key=placeholder).jwt_secret


def test_a_placeholder_database_password_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        production(postgres_password="change-me-locally")


def test_an_empty_database_password_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        production(postgres_password="")


def test_an_explicit_database_url_satisfies_the_password_requirement() -> None:
    """A managed database is configured by URL, and the URL carries its own auth."""
    config = production(
        postgres_password="",
        database_url="postgresql+psycopg://u:p@db.internal:5432/karya",
    )

    assert "db.internal" in config.sqlalchemy_database_uri.get_secret_value()


def test_production_cors_origins_must_be_https() -> None:
    """A browser origin is where the access token lives.

    Allowing an ``http://`` origin means agreeing to have credentials travel in
    cleartext, however much TLS the API itself terminates.
    """
    with pytest.raises(ValidationError):
        production(cors_allowed_origins="http://app.karya.io")
    with pytest.raises(ValidationError):
        production(cors_allowed_origins="https://app.karya.io,http://localhost:5173")

    # The local development origin is fine locally.
    assert build(
        environment="local", cors_allowed_origins="http://localhost:5173"
    ).cors_origins == ["http://localhost:5173"]


def test_no_cors_origins_is_valid_in_production() -> None:
    """A backend with no browser client is the safest configuration, not an error."""
    assert production(cors_allowed_origins="").cors_origins == []


# ---------------------------------------------------------------------------
# Operational limits (checked in every environment)
# ---------------------------------------------------------------------------


def test_an_unknown_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build(environment="local", log_level="CHATTY")

    assert build(environment="local", log_level="debug").log_level_number == 10


def test_log_format_defaults_to_json() -> None:
    """Machine-readable by default: a log nobody can parse is a log nobody reads."""
    assert build(environment="local").log_format is LogFormat.JSON
    assert (
        build(environment="local", log_format="console").log_format is LogFormat.CONSOLE
    )
    with pytest.raises(ValidationError):
        build(environment="local", log_format="xml")


@pytest.mark.parametrize(
    "field",
    [
        "db_pool_size",
        "db_pool_timeout_seconds",
        "db_connect_timeout_seconds",
        "max_request_body_bytes",
        "max_query_string_bytes",
        "hsts_max_age_seconds",
        "rate_limit_max_tracked_keys",
    ],
)
def test_settings_that_must_be_positive(field: str) -> None:
    for value in (0, -1):
        with pytest.raises(ValidationError):
            build(environment="local", **{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "db_max_overflow",
        "db_pool_recycle_seconds",
        "db_statement_timeout_ms",
        "db_lock_timeout_ms",
    ],
)
def test_settings_where_zero_means_disabled(field: str) -> None:
    """Zero is a meaningful value for these, so only negatives are rejected."""
    assert build(environment="local", **{field: 0})
    with pytest.raises(ValidationError):
        build(environment="local", **{field: -1})


@pytest.mark.parametrize(
    "field",
    [
        "rate_limit_login_per_minute",
        "rate_limit_login_failures_per_15_min",
        "rate_limit_refresh_per_minute",
        "rate_limit_password_change_per_15_min",
        "rate_limit_qr_challenge_per_minute",
        "rate_limit_presence_per_minute",
        "rate_limit_attendance_per_minute",
        "rate_limit_admin_write_per_minute",
    ],
)
def test_a_rate_limit_of_zero_is_rejected(field: str) -> None:
    """A limit of zero is not "no limit", it is an outage."""
    with pytest.raises(ValidationError):
        build(environment="local", **{field: 0})


# ---------------------------------------------------------------------------
# HSTS resolution
# ---------------------------------------------------------------------------


def test_hsts_defaults_to_on_in_production_and_off_elsewhere() -> None:
    """HSTS on localhost would pin a developer's browser to a scheme that host
    cannot serve - for the whole profile, not just this tab."""
    assert production().hsts_active is True
    assert build(environment="local").hsts_active is False
    assert production(environment="staging").hsts_active is False


def test_hsts_can_be_overridden_in_both_directions() -> None:
    assert production(hsts_enabled=False).hsts_active is False
    assert build(environment="local", hsts_enabled=True).hsts_active is True


# ---------------------------------------------------------------------------
# Secrets stay secret
# ---------------------------------------------------------------------------


def test_no_credential_appears_in_a_settings_repr() -> None:
    config = production(
        cors_allowed_origins="https://app.karya.io",
        database_url="postgresql+psycopg://u:url-password@h:5432/d",
        test_database_url="postgresql+psycopg://u:test-password@h:5432/d",
    )
    rendered = f"{config!r} {config} {config.model_dump()}"

    for secret in (GOOD_SECRET, GOOD_PASSWORD, "url-password", "test-password"):
        assert secret not in rendered, secret

    # Reachable only through a deliberate, explicit call.
    assert config.jwt_secret == GOOD_SECRET
