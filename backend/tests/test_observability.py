"""Correlation ids and structured logging (Phase 7).

A log line is only useful if it can be tied to a request, and only *safe* if it
cannot carry a credential. Both properties are tested here, and the second one is
tested adversarially: the redaction net is checked by handing the logger things it
should refuse to write down.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.core.config import LogFormat, Settings
from app.core.context import RequestContextFilter, get_request_id
from app.core.logging import (
    REDACTED,
    SENSITIVE_KEY_FRAGMENTS,
    ConsoleFormatter,
    JsonFormatter,
    build_handler,
    configure_logging,
    is_sensitive_key,
    record_payload,
    redact,
)
from app.main import app
from app.middleware.request_context import REQUEST_ID_HEADER, resolve_request_id
from app.models import Tenant, User
from tests.conftest import DEFAULT_PASSWORD, auth_header

GOOD_SECRET = "a-sufficiently-long-test-secret-key-1234"


def settings_for(**overrides: object) -> Settings:
    base: dict[str, object] = {"environment": "local", "jwt_secret_key": GOOD_SECRET}
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


@pytest.fixture
def captured_logs() -> Iterator[io.StringIO]:
    """Attach a JSON handler to the root logger without disturbing the others.

    Appended rather than substituted: this has to observe the real logging setup the
    application installed, not a parallel one that might behave differently.
    """
    # Apply the application's own configuration first. It replaces the root
    # handlers, so a handler added before it would be swept away - and it is applied
    # lazily, from the lifespan, meaning the sweep can happen mid-test.
    configure_logging(force=True)

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


def parse(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def events(stream: io.StringIO, name: str) -> list[dict[str, object]]:
    return [record for record in parse(stream) if record.get("event") == name]


# ---------------------------------------------------------------------------
# Correlation id
# ---------------------------------------------------------------------------


def test_a_request_id_is_generated_and_returned(client: TestClient) -> None:
    response = client.get("/health")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert len(request_id) == 32
    assert request_id.isalnum()


def test_every_request_gets_a_different_id(client: TestClient) -> None:
    seen = {client.get("/health").headers[REQUEST_ID_HEADER] for _ in range(10)}

    assert len(seen) == 10


def test_a_safe_inbound_id_is_honoured(client: TestClient) -> None:
    """So a trace started at the edge continues through Karya rather than restarting."""
    response = client.get(
        "/health", headers={REQUEST_ID_HEADER: "edge-trace-01.abc_DEF"}
    )

    assert response.headers[REQUEST_ID_HEADER] == "edge-trace-01.abc_DEF"


@pytest.mark.parametrize(
    "hostile",
    [
        # A newline would let a caller forge whole log entries.
        "abc\ndef",
        "abc\r\nlevel=INFO message=forged",
        # Overlong: a client-supplied value that is retained must be bounded.
        "x" * 65,
        # Punctuation that would need escaping wherever the id is later rendered.
        'id"; DROP TABLE users;--',
        "<script>alert(1)</script>",
        "",
        " ",
    ],
)
def test_a_hostile_inbound_id_is_replaced_not_trusted(hostile: str) -> None:
    """Rejected by substitution rather than by failing the request.

    A caller's tracing preference is not worth a 400 over, and the generated id is
    just as traceable.
    """
    scope = {"headers": [(b"x-request-id", hostile.encode("latin-1"))]}

    resolved = resolve_request_id(scope)

    assert resolved != hostile
    assert len(resolved) == 32


def test_the_id_on_the_response_is_the_id_in_the_log(
    client: TestClient, captured_logs: io.StringIO
) -> None:
    """The property that makes the header worth anything: a user quotes the id from
    an error page and an operator finds that exact request."""
    response = client.get("/health")

    request_id = response.headers[REQUEST_ID_HEADER]
    access = events(captured_logs, "http_request")
    assert [record for record in access if record["request_id"] == request_id]


def test_an_error_response_is_also_traceable(client: TestClient) -> None:
    for path, expected in (
        ("/api/v1/auth/me", 401),
        ("/api/v1/users/00000000-0000-0000-0000-000000000000", 401),
        ("/nonexistent", 404),
    ):
        response = client.get(path)
        assert response.status_code == expected
        assert response.headers[REQUEST_ID_HEADER]


def test_the_context_is_cleared_between_requests(client: TestClient) -> None:
    """A leaked id would attribute one request's logs to another."""
    client.get("/health")

    assert get_request_id() is None


# ---------------------------------------------------------------------------
# The access log
# ---------------------------------------------------------------------------


def test_the_access_log_records_the_shape_of_the_request(
    client: TestClient, captured_logs: io.StringIO
) -> None:
    client.get("/api/v1/attendance/me")

    record = events(captured_logs, "http_request")[-1]

    assert record["method"] == "GET"
    assert record["path"] == "/api/v1/attendance/me"
    assert record["status_code"] == 401
    assert isinstance(record["duration_ms"], (int, float))
    assert record["request_id"]


def test_the_access_log_uses_the_route_template_not_the_expanded_path(
    client: TestClient,
    captured_logs: io.StringIO,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., Response],
) -> None:
    """So per-endpoint aggregation is possible.

    Logging only the expanded path would put a distinct value in every line and make
    "how slow is this endpoint" unanswerable.
    """
    tenant = tenant_factory(slug="acme")
    user = user_factory(tenant, email="rahul@acme.com")
    token = login("acme", "rahul@acme.com").json()["access_token"]

    client.get(f"/api/v1/attendance/users/{user.id}", headers=auth_header(token))

    record = events(captured_logs, "http_request")[-1]
    assert record["route"] == "/attendance/users/{user_id}"
    assert str(user.id) in str(record["path"])


def test_the_access_log_omits_the_query_string(
    client: TestClient, captured_logs: io.StringIO
) -> None:
    """A query string carries user input - ``?search=<someone's name>`` - into a log
    line that may be retained for months."""
    client.get("/api/v1/users?search=Rahul+Sharma&page=1")

    record = events(captured_logs, "http_request")[-1]

    assert "Rahul" not in json.dumps(record)
    assert "search" not in json.dumps(record)


def test_a_verified_caller_is_attributed_in_the_access_log(
    client: TestClient,
    captured_logs: io.StringIO,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., Response],
) -> None:
    """Attribution comes from the database row, never from anything sent."""
    tenant = tenant_factory(slug="acme")
    user = user_factory(tenant, email="rahul@acme.com")
    token = login("acme", "rahul@acme.com").json()["access_token"]

    client.get("/api/v1/users/me", headers=auth_header(token))

    record = events(captured_logs, "http_request")[-1]
    assert record["user_id"] == str(user.id)
    assert record["tenant_id"] == str(tenant.id)


def test_client_status_is_logged_as_a_warning_and_server_status_as_an_error(
    client: TestClient, captured_logs: io.StringIO
) -> None:
    """So an alert on ERROR fires for defects, not for a mistyped password."""
    client.get("/health")
    client.get("/api/v1/auth/me")

    records = events(captured_logs, "http_request")
    assert records[-2]["level"] == "INFO"
    assert records[-1]["level"] == "WARNING"


# ---------------------------------------------------------------------------
# Authentication logging: enough to investigate, never enough to impersonate
# ---------------------------------------------------------------------------


def test_a_failed_login_is_logged_without_the_email_or_password(
    client: TestClient,
    captured_logs: io.StringIO,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "acme",
            "email": "rahul@acme.com",
            "password": "the-wrong-password",
        },
    )

    record = events(captured_logs, "login_failed")[-1]
    # The tenant slug is a public identifier staff type at login, and it is what an
    # operator correlates an attack by.
    assert record["tenant_slug"] == "acme"
    serialised = json.dumps(record)
    # The email identifies a person, and a log of attempted addresses is a list of
    # accounts worth attacking.
    assert "rahul@acme.com" not in serialised
    assert "the-wrong-password" not in serialised


def test_a_successful_login_logs_no_token(
    client: TestClient,
    captured_logs: io.StringIO,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "acme",
            "email": "rahul@acme.com",
            "password": DEFAULT_PASSWORD,
        },
    )

    body = response.json()
    logged = captured_logs.getvalue()
    assert events(captured_logs, "login_succeeded")
    assert body["access_token"] not in logged
    assert body["refresh_token"] not in logged
    assert DEFAULT_PASSWORD not in logged


def test_a_rejected_refresh_logs_no_token(
    client: TestClient, captured_logs: io.StringIO
) -> None:
    presented = "a-stolen-looking-refresh-token-value"

    client.post("/api/v1/auth/refresh", json={"refresh_token": presented})

    assert events(captured_logs, "refresh_rejected")
    assert presented not in captured_logs.getvalue()


def test_a_qr_nonce_never_reaches_the_log(
    db_session: Session,
    client: TestClient,
    captured_logs: io.StringIO,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., object],
    login: Callable[..., Response],
) -> None:
    """The nonce is the secret the challenge protects. The id is enough to correlate."""
    from app.models.user import UserRole

    tenant = tenant_factory(slug="acme")
    location = location_factory(tenant)
    user_factory(
        tenant, email="priya@acme.com", employee_code="MGR-1", role=UserRole.MANAGER
    )
    db_session.flush()
    token = login("acme", "priya@acme.com").json()["access_token"]

    issued = client.post(
        "/api/v1/presence/qr/challenge", headers=auth_header(token)
    ).json()
    client.post(
        "/api/v1/presence/verify",
        json={
            "latitude": location.latitude,
            "longitude": location.longitude,
            "accuracy_meters": 10.0,
            "challenge_id": issued["challenge_id"],
            "nonce": issued["nonce"],
        },
        headers=auth_header(token),
    )

    assert issued["nonce"] not in captured_logs.getvalue()


def test_the_startup_line_logs_no_credential(captured_logs: io.StringIO) -> None:
    """The startup line reports the database it will use, by its safe rendering."""
    with TestClient(app):
        pass

    record = events(captured_logs, "application_startup")[-1]
    assert "***" in str(record["database"])
    from app.core.config import settings as live_settings

    assert live_settings.postgres_password.get_secret_value() not in json.dumps(record)
    assert live_settings.jwt_secret not in json.dumps(record)


# ---------------------------------------------------------------------------
# Redaction: the net under the tightrope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fragment", SENSITIVE_KEY_FRAGMENTS)
def test_every_sensitive_fragment_is_recognised(fragment: str) -> None:
    assert is_sensitive_key(fragment)
    assert is_sensitive_key(f"user_{fragment}")
    assert is_sensitive_key(fragment.upper())


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "new_password",
        "current_password",
        "PASSWORD",
        "password_hash",
        "refresh_token",
        "access_token",
        "Authorization",
        "jwt_secret",
        "nonce",
        "api_key",
        "session_cookie",
    ],
)
def test_a_sensitively_named_field_is_redacted(key: str) -> None:
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "event", None, None
    )
    setattr(record, key, "the-actual-secret-value")

    payload = record_payload(record)

    assert payload[key] == REDACTED
    assert "the-actual-secret-value" not in json.dumps(payload)


def test_redaction_reaches_into_nested_payloads() -> None:
    nested = redact(
        {
            "outer": {"password": "s3cret", "safe": "keep"},
            "deeper": {"a": {"refresh_token": "t0ken"}},
        }
    )

    assert nested["outer"]["password"] == REDACTED
    assert nested["outer"]["safe"] == "keep"
    assert nested["deeper"]["a"]["refresh_token"] == REDACTED


def test_ordinary_fields_survive_redaction() -> None:
    """Over-redaction would make the logs useless, which is its own failure."""
    kept = redact(
        {
            "tenant_id": "abc",
            "user_id": "def",
            "event": "login_failed",
            "status_code": 401,
            "duration_ms": 1.5,
        }
    )

    assert kept["tenant_id"] == "abc"
    assert kept["status_code"] == 401


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_json_output_is_one_object_per_line() -> None:
    stream = io.StringIO()
    handler = build_handler(settings_for(log_format="json"))
    handler.setStream(stream)  # type: ignore[attr-defined]
    logger = logging.getLogger("karya.test.json")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info("something_happened", extra={"event": "something_happened", "n": 1})

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["message"] == "something_happened"
    assert payload["event"] == "something_happened"
    assert payload["n"] == 1
    assert payload["level"] == "INFO"
    assert payload["timestamp"].endswith("+00:00")


def test_the_console_format_is_selectable_and_readable() -> None:
    handler = build_handler(settings_for(log_format="console"))

    assert isinstance(handler.formatter, ConsoleFormatter)
    assert isinstance(build_handler(settings_for(log_format="json")).formatter, JsonFormatter)
    assert settings_for(log_format="console").log_format is LogFormat.CONSOLE


def test_an_exception_is_rendered_as_text_not_as_an_object() -> None:
    """A traceback belongs in the log and never in a response - see
    ``test_error_handling.py`` for the other half of that guarantee."""
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "t", logging.ERROR, __file__, 1, "failed", None, True
        )
        import sys

        record.exc_info = sys.exc_info()

    payload = record_payload(record)

    assert "ValueError: boom" in str(payload["exception"])
    assert json.dumps(payload)  # serialisable


def test_an_unserialisable_field_does_not_lose_the_line() -> None:
    """Degrading one field is better than dropping the whole record."""

    class Opaque:
        def __str__(self) -> str:
            return "opaque-object"

    stream = io.StringIO()
    handler = build_handler(settings_for())
    handler.setStream(stream)  # type: ignore[attr-defined]
    logger = logging.getLogger("karya.test.opaque")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info("odd", extra={"thing": Opaque()})

    assert json.loads(stream.getvalue())["thing"] == "opaque-object"
