"""Application configuration.

All configuration is sourced from the environment (or a local ``.env`` file).
No credential is ever hardcoded, and secret values are wrapped in
:class:`~pydantic.SecretStr` so they cannot leak into logs or tracebacks
through an accidental ``repr()``.

**Environments.** ``ENVIRONMENT`` is a closed set (:class:`Environment`), not a
free string, so a typo like ``prod`` or ``Production`` fails at startup instead
of silently landing in the permissive branch of some later ``if``. Phase 7 adds a
block of production-only validation (:meth:`Settings._validate_production`): the
values that are *convenient* in ``local`` - no secret, debug on, an ``http://``
origin - are exactly the values that must never reach production, so production
refuses to boot with them rather than trusting the operator to notice.
"""

from __future__ import annotations

import enum
import logging
from functools import lru_cache
from typing import Final

from pydantic import PostgresDsn, SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Version reported by ``/openapi.json`` and the startup log line. Single source
#: of truth: ``main.py`` reads it rather than restating a literal.
APP_VERSION: Final[str] = "0.7.0"

#: SQLAlchemy dialect+driver used for every PostgreSQL connection.
POSTGRES_DRIVER = "postgresql+psycopg"


class Environment(enum.StrEnum):
    """Deployment environments Karya recognises.

    A closed set on purpose. ``ENVIRONMENT=prod`` (or a stray trailing space)
    would otherwise be an unrecognised value that quietly behaves like
    development, which is the worst possible failure mode for a variable whose
    whole job is to decide how strict everything else is.
    """

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogFormat(enum.StrEnum):
    """How log records are rendered."""

    #: One JSON object per line - what a log shipper wants.
    JSON = "json"
    #: Human-readable single line - what a developer wants in a terminal.
    CONSOLE = "console"


#: Environments that may run without a configured JWT secret. Anywhere else the
#: application refuses to start rather than fall back to a guessable default.
SECRET_OPTIONAL_ENVIRONMENTS: Final[frozenset[Environment]] = frozenset(
    {Environment.LOCAL, Environment.TEST}
)

#: Minimum acceptable JWT secret length. 32 bytes matches the HMAC-SHA256 block
#: output; anything shorter measurably weakens HS256.
MIN_JWT_SECRET_LENGTH: Final[int] = 32

#: Values shipped in ``.env.example`` and similar templates. They are fine as
#: placeholders and unacceptable as production secrets, so production rejects
#: them by name - a deployment that forgot to fill the template in fails loudly
#: instead of running on a value published in the repository.
KNOWN_PLACEHOLDER_SECRETS: Final[frozenset[str]] = frozenset(
    {
        "replace-with-a-long-random-value-min-32-chars",
        "change-me-locally",
        "change-me",
        "changeme",
        "secret",
        "postgres",
    }
)


class Settings(BaseSettings):
    """Runtime settings for the Karya backend.

    The PostgreSQL connection URL can be provided in two ways:

    1. Explicitly, via ``DATABASE_URL`` (takes precedence). Useful for managed
       databases and CI.
    2. Composed from the discrete ``POSTGRES_*`` variables, which are the same
       variables ``docker-compose.yml`` uses to provision the container.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application --------------------------------------------------------
    app_name: str = "Karya"
    environment: Environment = Environment.LOCAL
    debug: bool = False

    #: Whether ``/docs``, ``/redoc`` and ``/openapi.json`` are served. Left on by
    #: default because the schema is the API's contract, not a secret - every
    #: route it documents is authenticated and authorized independently. Turn it
    #: off in production if you would rather not publish the shape of the API.
    docs_enabled: bool = True

    # --- Observability ------------------------------------------------------
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON

    # --- PostgreSQL ---------------------------------------------------------
    postgres_db: str = "karya"
    postgres_user: str = "karya"
    postgres_password: SecretStr = SecretStr("")
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # --- Optional explicit URLs --------------------------------------------
    database_url: SecretStr | None = None
    test_database_url: SecretStr | None = None

    # --- Connection pool (Phase 7) ------------------------------------------
    # Sized deliberately small. Every API instance holds up to
    # (pool_size + max_overflow) server connections, and PostgreSQL's own
    # max_connections is the shared budget - see docs/PRODUCTION.md for the
    # arithmetic. A large pool does not make a saturated database faster; it
    # just moves the queue from the application into the server.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30
    #: Recycle connections before an idle proxy or load balancer drops them.
    db_pool_recycle_seconds: int = 1_800
    db_connect_timeout_seconds: int = 10
    #: Server-side ceiling on any single statement. 0 disables. Bounds a runaway
    #: query so it cannot hold a pool slot indefinitely.
    db_statement_timeout_ms: int = 15_000
    #: Server-side ceiling on waiting for a row lock. 0 disables. Karya's
    #: attendance and last-admin paths deliberately block on ``FOR UPDATE``; the
    #: expected wait is milliseconds, so this only fires when a transaction is
    #: genuinely stuck, and then it fails fast instead of piling up connections.
    db_lock_timeout_ms: int = 5_000

    # --- Authentication (Phase 2) ------------------------------------------
    # Deliberately has NO default: there must never be a guessable fallback
    # signing key. See `jwt_secret` and the validator below for how a missing
    # secret is handled.
    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # --- CORS ---------------------------------------------------------------
    # Comma-separated list, e.g. "http://localhost:5173,https://app.karya.io".
    # Empty means "no browser origin allowed", which is the safe default; a
    # wildcard is rejected outright when credentials are permitted.
    cors_allowed_origins: str = ""

    # --- HTTP hardening (Phase 7) -------------------------------------------
    #: Largest request body accepted, in bytes. Karya's biggest payload is a
    #: presence verification of a few hundred bytes, so 64 KiB is generous while
    #: still refusing a multi-megabyte body before it is buffered or parsed.
    max_request_body_bytes: int = 65_536
    #: Largest query string accepted, in bytes.
    max_query_string_bytes: int = 2_048
    #: Send Strict-Transport-Security. ``None`` means "on in production, off
    #: elsewhere": HSTS on ``localhost`` pins the developer's whole browser
    #: profile to HTTPS for a host that has no certificate.
    hsts_enabled: bool | None = None
    hsts_max_age_seconds: int = 31_536_000  # 365 days

    # --- Rate limiting (Phase 7) --------------------------------------------
    # Limits are per process (see app/core/rate_limit.py for what that does and
    # does not protect). They are set to be invisible to a person using Karya
    # normally and obstructive to a script: a staff member checks in twice a day,
    # not twenty times a minute.
    rate_limit_enabled: bool = True
    rate_limit_login_per_minute: int = 20
    #: Failed logins tolerated per (tenant, email) per 15 minutes. Counts only
    #: failures, and a success clears the counter, so someone mistyping their
    #: password twice is unaffected while a password-guessing script is not.
    rate_limit_login_failures_per_15_min: int = 10
    rate_limit_refresh_per_minute: int = 60
    rate_limit_password_change_per_15_min: int = 5
    rate_limit_qr_challenge_per_minute: int = 60
    rate_limit_presence_per_minute: int = 30
    rate_limit_attendance_per_minute: int = 20
    rate_limit_admin_write_per_minute: int = 120
    #: Upper bound on distinct keys the in-memory limiter tracks, so a flood of
    #: unique client addresses cannot grow the process's memory without limit.
    rate_limit_max_tracked_keys: int = 100_000

    # --- Presence verification (Phase 3) ------------------------------------
    # Worst device-reported GPS accuracy still accepted. A phone claiming
    # "somewhere within 500 m" cannot evidence presence inside a 150 m
    # geofence, so such a reading is rejected rather than silently trusted.
    max_gps_accuracy_meters: float = 100.0

    # Lifetime of a dynamic QR challenge. Short by design: the office display
    # rotates the code, so a photographed QR is useless within seconds.
    qr_challenge_ttl_seconds: int = 30

    # --- Outbound email (Phase 11: onboarding) -------------------------------
    # stdlib `smtplib`, no third-party dependency - same precedent as Phase 7's
    # logging/rate-limiting/security-headers choices. Left unset, sending
    # degrades to a structured log line instead of failing, so a fresh local
    # checkout and the test suite need no mail server at all. A deployment
    # that forgets to configure this finds out from its own logs, not a 500.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_address: str = "no-reply@karya.local"
    #: STARTTLS on the plaintext connection, not implicit TLS. True fits every
    #: mainstream provider's port-587 submission endpoint; a provider that
    #: instead wants implicit TLS on 465 needs a small follow-up, not a design
    #: change - see the mailer module.
    smtp_use_tls: bool = True
    #: Socket timeout for the whole SMTP conversation (connect, STARTTLS,
    #: auth, send). A hung mail server must fail the request in seconds, not
    #: leave the onboarding transaction open indefinitely.
    smtp_timeout_seconds: int = 10

    #: Brevo's HTTP transactional-email API, as an alternative transport to
    #: SMTP above - not a replacement for it in general, but the only one
    #: that works on hosts (Render's free tier among them) that block
    #: outbound SMTP ports as an anti-spam-relay measure. When set, the
    #: mailer sends over plain HTTPS instead of opening an SMTP connection;
    #: see `app.services.email.mailer`. `smtp_from_address` is still the
    #: sender identity either way - only the wire protocol changes.
    brevo_api_key: SecretStr | None = None
    #: Socket timeout for the HTTPS call to Brevo's API. Independent of
    #: `smtp_timeout_seconds` because the two transports never run in the
    #: same request - the mailer prefers Brevo's API when both happen to be
    #: configured (see the mailer module for why).
    brevo_api_timeout_seconds: int = 10

    # --- Onboarding (Phase 11) ------------------------------------------------
    # Where the verification link points. Deliberately separate from
    # CORS_ALLOWED_ORIGINS: that list is a security allowlist enforced by the
    # browser, this is just "where to send a human" and has no security
    # meaning of its own - the token in the link is what actually authorizes
    # anything.
    public_app_url: str = "http://localhost:5173"
    email_verification_ttl_hours: int = 24

    @field_validator("public_app_url", mode="after")
    @classmethod
    def _normalize_public_app_url(cls, value: str) -> str:
        """Strip a trailing slash and require a real ``http(s)://`` origin.

        `onboarding.service._verification_url` builds a link by naive string
        concatenation (``f"{public_app_url}/onboarding/verify?token=..."``);
        a configured value with a trailing slash would silently double it
        into ``.../org//onboarding/verify``, and a value with no scheme at
        all would produce a link no mail client treats as clickable. Both
        are configuration mistakes worth failing fast on, in every
        environment, not just production.
        """
        stripped = value.strip().rstrip("/")
        if not stripped.startswith(("http://", "https://")):
            raise ValueError(
                "PUBLIC_APP_URL must start with http:// or https://; "
                f"got {value!r}."
            )
        return stripped

    #: Per-IP: this is the one public, unauthenticated *write* endpoint in the
    #: whole API, so its budget is deliberately tight - a handful of
    #: organizations signing up from one address per hour, not a volume any
    #: real user needs.
    rate_limit_onboarding_per_hour: int = 5
    #: Separate budget from onboarding itself: a legitimate user retrying a
    #: mistyped or already-clicked verification link must not compete with
    #: someone else's signup attempts from behind the same NAT.
    rate_limit_email_verification_per_hour: int = 20

    # --- Derived values -----------------------------------------------------
    def _build_url(self, database: str) -> str:
        """Compose a psycopg connection URL for ``database``.

        ``PostgresDsn.build`` performs the required percent-encoding, so
        passwords containing URL-reserved characters are handled correctly.
        """
        return str(
            PostgresDsn.build(
                scheme=POSTGRES_DRIVER,
                username=self.postgres_user,
                password=self.postgres_password.get_secret_value() or None,
                host=self.postgres_host,
                port=self.postgres_port,
                path=database,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> SecretStr:
        """Connection URL for the application database.

        Returned as a secret because it embeds the password. Call
        ``.get_secret_value()`` only where the raw string is genuinely needed
        (e.g. ``create_engine``) - never when logging.
        """
        if self.database_url is not None:
            return self.database_url
        return SecretStr(self._build_url(self.postgres_db))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_test_database_uri(self) -> SecretStr:
        """Connection URL for the test database.

        Defaults to ``<POSTGRES_DB>_test`` on the same server.
        """
        if self.test_database_url is not None:
            return self.test_database_url
        return SecretStr(self._build_url(f"{self.postgres_db}_test"))

    @property
    def safe_database_uri(self) -> str:
        """Password-free rendering of the database URL, safe to log."""
        return (
            f"{POSTGRES_DRIVER}://{self.postgres_user}:***"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # --- Validation ---------------------------------------------------------
    @model_validator(mode="after")
    def _validate_auth_settings(self) -> Settings:
        """Fail fast on an unsafe authentication configuration.

        A missing secret is tolerated only in ``local``/``test`` so that
        ``GET /health`` and the database tooling still run on a fresh checkout;
        any attempt to actually mint or verify a token then raises (see
        :attr:`jwt_secret`). Everywhere else, startup is refused.
        """
        if self.jwt_secret_key is None:
            if self.environment not in SECRET_OPTIONAL_ENVIRONMENTS:
                raise ValueError(
                    "JWT_SECRET_KEY must be set when ENVIRONMENT is "
                    f"'{self.environment}'."
                )
        elif len(self.jwt_secret_key.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                "JWT_SECRET_KEY must be at least "
                f"{MIN_JWT_SECRET_LENGTH} characters long."
            )

        if self.access_token_expire_minutes <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive.")
        if self.refresh_token_expire_days <= 0:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be positive.")

        if self.max_gps_accuracy_meters <= 0:
            raise ValueError("MAX_GPS_ACCURACY_METERS must be positive.")
        if self.qr_challenge_ttl_seconds <= 0:
            raise ValueError("QR_CHALLENGE_TTL_SECONDS must be positive.")
        if self.email_verification_ttl_hours <= 0:
            raise ValueError("EMAIL_VERIFICATION_TTL_HOURS must be positive.")
        if self.smtp_timeout_seconds <= 0:
            raise ValueError("SMTP_TIMEOUT_SECONDS must be positive.")
        if self.brevo_api_timeout_seconds <= 0:
            raise ValueError("BREVO_API_TIMEOUT_SECONDS must be positive.")

        if "*" in self.cors_origins:
            # Karya sends credentials, for which a wildcard origin is both
            # forbidden by the CORS spec and a real security hole.
            raise ValueError("CORS_ALLOWED_ORIGINS must not contain a wildcard.")
        return self

    @model_validator(mode="after")
    def _validate_operational_settings(self) -> Settings:
        """Reject nonsensical limits, timeouts and pool sizes in any environment.

        These are all "a zero here silently disables a protection" cases, so they
        are checked everywhere rather than only in production.
        """
        if self.log_level.upper() not in logging.getLevelNamesMapping():
            raise ValueError(
                f"LOG_LEVEL '{self.log_level}' is not a recognised logging level."
            )

        for name, value in (
            ("DB_POOL_SIZE", self.db_pool_size),
            ("DB_POOL_TIMEOUT_SECONDS", self.db_pool_timeout_seconds),
            ("DB_CONNECT_TIMEOUT_SECONDS", self.db_connect_timeout_seconds),
            ("MAX_REQUEST_BODY_BYTES", self.max_request_body_bytes),
            ("MAX_QUERY_STRING_BYTES", self.max_query_string_bytes),
            ("HSTS_MAX_AGE_SECONDS", self.hsts_max_age_seconds),
            ("RATE_LIMIT_MAX_TRACKED_KEYS", self.rate_limit_max_tracked_keys),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive.")

        for name, value in (
            ("DB_MAX_OVERFLOW", self.db_max_overflow),
            ("DB_POOL_RECYCLE_SECONDS", self.db_pool_recycle_seconds),
            ("DB_STATEMENT_TIMEOUT_MS", self.db_statement_timeout_ms),
            ("DB_LOCK_TIMEOUT_MS", self.db_lock_timeout_ms),
        ):
            if value < 0:
                raise ValueError(f"{name} must not be negative.")

        # A zero or negative limit would be a rate limiter that rejects every
        # request, which reads as an outage rather than as protection.
        for name, value in (
            ("RATE_LIMIT_LOGIN_PER_MINUTE", self.rate_limit_login_per_minute),
            (
                "RATE_LIMIT_LOGIN_FAILURES_PER_15_MIN",
                self.rate_limit_login_failures_per_15_min,
            ),
            ("RATE_LIMIT_REFRESH_PER_MINUTE", self.rate_limit_refresh_per_minute),
            (
                "RATE_LIMIT_PASSWORD_CHANGE_PER_15_MIN",
                self.rate_limit_password_change_per_15_min,
            ),
            (
                "RATE_LIMIT_QR_CHALLENGE_PER_MINUTE",
                self.rate_limit_qr_challenge_per_minute,
            ),
            ("RATE_LIMIT_PRESENCE_PER_MINUTE", self.rate_limit_presence_per_minute),
            ("RATE_LIMIT_ATTENDANCE_PER_MINUTE", self.rate_limit_attendance_per_minute),
            (
                "RATE_LIMIT_ADMIN_WRITE_PER_MINUTE",
                self.rate_limit_admin_write_per_minute,
            ),
            (
                "RATE_LIMIT_ONBOARDING_PER_HOUR",
                self.rate_limit_onboarding_per_hour,
            ),
            (
                "RATE_LIMIT_EMAIL_VERIFICATION_PER_HOUR",
                self.rate_limit_email_verification_per_hour,
            ),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive.")
        return self

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        """Refuse to start production on a development-shaped configuration.

        Each rule below exists because the *convenient* local value is actively
        dangerous in production, and because a configuration mistake that only
        shows up as a security weakness is one nobody notices.
        """
        if self.environment is not Environment.PRODUCTION:
            return self

        if self.debug:
            # DEBUG is not merely noisy: it is the flag every framework uses to
            # decide whether to expose internals.
            raise ValueError("DEBUG must be false when ENVIRONMENT is 'production'.")

        secret = self.jwt_secret_key.get_secret_value() if self.jwt_secret_key else ""
        if secret.lower() in KNOWN_PLACEHOLDER_SECRETS:
            raise ValueError(
                "JWT_SECRET_KEY is still the template placeholder; generate a "
                "real secret before deploying."
            )

        if self.database_url is None:
            password = self.postgres_password.get_secret_value()
            if not password:
                raise ValueError(
                    "POSTGRES_PASSWORD (or DATABASE_URL) must be set when "
                    "ENVIRONMENT is 'production'."
                )
            if password.lower() in KNOWN_PLACEHOLDER_SECRETS:
                raise ValueError(
                    "POSTGRES_PASSWORD is still a template placeholder; set a "
                    "real password before deploying."
                )

        # A browser origin is where the access token lives. Allowing an http://
        # origin in production means agreeing to have credentials sent over
        # cleartext, whatever TLS the API itself terminates.
        insecure = [
            origin for origin in self.cors_origins if not origin.startswith("https://")
        ]
        if insecure:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must use https:// in production; got "
                f"{insecure!r}."
            )

        # The verification link this URL builds is emailed to whoever just
        # typed a password into the signup form - the same "credentials
        # must never cross the wire in cleartext" reasoning as the CORS
        # check above.
        if not self.public_app_url.startswith("https://"):
            raise ValueError(
                "PUBLIC_APP_URL must use https:// in production; got "
                f"{self.public_app_url!r}."
            )

        # Unconfigured email degrades to logging the onboarding email - link,
        # token and all - at INFO (see `app.services.email.mailer`). That
        # fallback exists for a bare local checkout; in production it would
        # mean every admin's account-verification link lands in whatever
        # aggregates the app's own logs. Either transport satisfies this -
        # SMTP_HOST for a host that allows outbound SMTP, BREVO_API_KEY for
        # one (Render's free tier among them) that blocks it.
        if not self.smtp_host and not self.brevo_api_key:
            raise ValueError(
                "SMTP_HOST or BREVO_API_KEY must be set when ENVIRONMENT is "
                "'production'; without one of them, onboarding verification "
                "links are logged instead of emailed."
            )
        return self

    # --- Convenience --------------------------------------------------------
    @property
    def is_production(self) -> bool:
        """Whether this process is configured as production."""
        return self.environment is Environment.PRODUCTION

    @property
    def jwt_secret(self) -> str:
        """The raw JWT signing key.

        Raises:
            RuntimeError: if no secret is configured. Failing here means an
                unconfigured deployment cannot issue or accept tokens at all,
                rather than silently signing them with a default value.
        """
        if self.jwt_secret_key is None:
            raise RuntimeError(
                "JWT_SECRET_KEY is not configured; authentication is disabled."
            )
        return self.jwt_secret_key.get_secret_value()

    @property
    def is_auth_configured(self) -> bool:
        """Whether tokens can be issued/verified in this process."""
        return self.jwt_secret_key is not None

    @property
    def access_token_expire_seconds(self) -> int:
        """Access-token lifetime in seconds, for the ``expires_in`` field."""
        return self.access_token_expire_minutes * 60

    @property
    def cors_origins(self) -> list[str]:
        """``CORS_ALLOWED_ORIGINS`` parsed into a list of exact origins."""
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def hsts_active(self) -> bool:
        """Whether to send Strict-Transport-Security, resolving the ``None``."""
        if self.hsts_enabled is None:
            return self.is_production
        return self.hsts_enabled

    @property
    def log_level_number(self) -> int:
        """``log_level`` as the numeric level ``logging`` expects."""
        return logging.getLevelNamesMapping()[self.log_level.upper()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()
