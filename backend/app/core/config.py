"""Application configuration.

All configuration is sourced from the environment (or a local ``.env`` file).
No credential is ever hardcoded, and secret values are wrapped in
:class:`~pydantic.SecretStr` so they cannot leak into logs or tracebacks
through an accidental ``repr()``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from pydantic import PostgresDsn, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: SQLAlchemy dialect+driver used for every PostgreSQL connection.
POSTGRES_DRIVER = "postgresql+psycopg"

#: Environments that may run without a configured JWT secret. Anywhere else the
#: application refuses to start rather than fall back to a guessable default.
SECRET_OPTIONAL_ENVIRONMENTS: Final[frozenset[str]] = frozenset({"local", "test"})

#: Minimum acceptable JWT secret length. 32 bytes matches the HMAC-SHA256 block
#: output; anything shorter measurably weakens HS256.
MIN_JWT_SECRET_LENGTH: Final[int] = 32


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
    environment: str = "local"
    debug: bool = False

    # --- PostgreSQL ---------------------------------------------------------
    postgres_db: str = "karya"
    postgres_user: str = "karya"
    postgres_password: SecretStr = SecretStr("")
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # --- Optional explicit URLs --------------------------------------------
    database_url: SecretStr | None = None
    test_database_url: SecretStr | None = None

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

    # --- Authentication -----------------------------------------------------
    @model_validator(mode="after")
    def _validate_auth_settings(self) -> Settings:
        """Fail fast on an unsafe authentication configuration.

        A missing secret is tolerated only in ``local``/``test`` so that
        ``GET /health`` and the database tooling still run on a fresh checkout;
        any attempt to actually mint or verify a token then raises (see
        :attr:`jwt_secret`). Everywhere else, startup is refused.
        """
        if self.jwt_secret_key is None:
            if self.environment.lower() not in SECRET_OPTIONAL_ENVIRONMENTS:
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

        if "*" in self.cors_origins:
            # Karya sends credentials, for which a wildcard origin is both
            # forbidden by the CORS spec and a real security hole.
            raise ValueError("CORS_ALLOWED_ORIGINS must not contain a wildcard.")
        return self

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()
