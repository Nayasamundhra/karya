"""Refresh-token issuance, rotation, revocation (spec checks 26-34)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RefreshToken, Tenant, User, UserStatus
from app.services.auth.refresh_tokens import (
    REFRESH_TOKEN_BYTES,
    generate_raw_token,
    hash_refresh_token,
)

REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
GENERIC_ERROR = "Invalid credentials"


# ---------------------------------------------------------------------------
# 26-27. Generation and storage
# ---------------------------------------------------------------------------


def test_refresh_token_is_opaque_and_high_entropy() -> None:
    tokens = {generate_raw_token() for _ in range(50)}

    assert len(tokens) == 50  # no collisions
    for token in tokens:
        # url-safe base64 of 32 bytes, so not a JWT.
        assert "." not in token
        assert len(token) >= REFRESH_TOKEN_BYTES


def test_raw_refresh_token_is_never_stored(
    db_session: Session,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    raw = login("acme", "rahul@acme.com").json()["refresh_token"]
    record = db_session.scalars(select(RefreshToken)).one()

    assert record.token_hash == hash_refresh_token(raw)
    assert record.token_hash != raw
    # A SHA-256 hex digest, and the raw value appears nowhere in the row.
    assert len(record.token_hash) == 64
    assert raw not in record.token_hash
    assert record.revoked_at is None
    assert record.expires_at > datetime.now(UTC)


def test_refresh_token_lifetime_follows_configuration(
    db_session: Session,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    login("acme", "rahul@acme.com")
    record = db_session.scalars(select(RefreshToken)).one()

    expected = datetime.now(UTC) + timedelta(days=30)
    assert abs((record.expires_at - expected).total_seconds()) < 60
    assert record.expires_at.tzinfo is not None


# ---------------------------------------------------------------------------
# 28-30. Rotation
# ---------------------------------------------------------------------------


def test_refresh_token_can_be_exchanged(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    original = login("acme", "rahul@acme.com").json()

    response = client.post(
        REFRESH_URL, json={"refresh_token": original["refresh_token"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert body["access_token"]
    assert body["refresh_token"]


def test_rotation_replaces_the_refresh_token(
    db_session: Session,
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    old_raw = login("acme", "rahul@acme.com").json()["refresh_token"]

    new_raw = client.post(REFRESH_URL, json={"refresh_token": old_raw}).json()[
        "refresh_token"
    ]

    assert new_raw != old_raw

    old_record = db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(old_raw)
        )
    )
    new_record = db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(new_raw)
        )
    )

    # The old row is revoked, not deleted, so a replay is identifiable.
    assert old_record is not None
    assert old_record.revoked_at is not None
    assert new_record is not None
    assert new_record.revoked_at is None


def test_old_refresh_token_cannot_be_reused(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """Replaying a rotated token must be rejected, never silently re-issued."""
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    old_raw = login("acme", "rahul@acme.com").json()["refresh_token"]

    assert client.post(REFRESH_URL, json={"refresh_token": old_raw}).status_code == 200

    replay = client.post(REFRESH_URL, json={"refresh_token": old_raw})

    assert replay.status_code == 401
    assert replay.json()["detail"] == GENERIC_ERROR


def test_rotation_chain_invalidates_every_earlier_token(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    used: list[str] = [login("acme", "rahul@acme.com").json()["refresh_token"]]
    for _ in range(3):
        response = client.post(REFRESH_URL, json={"refresh_token": used[-1]})
        assert response.status_code == 200
        used.append(response.json()["refresh_token"])

    # Every superseded token is dead; only the newest survives.
    for spent in used[:-1]:
        assert client.post(REFRESH_URL, json={"refresh_token": spent}).status_code == 401
    assert client.post(REFRESH_URL, json={"refresh_token": used[-1]}).status_code == 200


# ---------------------------------------------------------------------------
# 31-33. Rejection paths
# ---------------------------------------------------------------------------


def test_unknown_refresh_token_fails(client: TestClient) -> None:
    response = client.post(REFRESH_URL, json={"refresh_token": generate_raw_token()})

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_ERROR


def test_expired_refresh_token_fails(
    db_session: Session,
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    raw = login("acme", "rahul@acme.com").json()["refresh_token"]

    record = db_session.scalars(select(RefreshToken)).one()
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()

    assert client.post(REFRESH_URL, json={"refresh_token": raw}).status_code == 401


def test_revoked_refresh_token_fails(
    db_session: Session,
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    raw = login("acme", "rahul@acme.com").json()["refresh_token"]

    record = db_session.scalars(select(RefreshToken)).one()
    record.revoked_at = datetime.now(UTC)
    db_session.flush()

    assert client.post(REFRESH_URL, json={"refresh_token": raw}).status_code == 401


def test_inactive_user_cannot_refresh(
    db_session: Session,
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user = user_factory(tenant, email="rahul@acme.com")
    raw = login("acme", "rahul@acme.com").json()["refresh_token"]

    user.status = UserStatus.INACTIVE.value
    db_session.flush()

    assert client.post(REFRESH_URL, json={"refresh_token": raw}).status_code == 401


def test_rejected_rotation_leaves_the_token_unrevoked(
    db_session: Session,
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """A failed refresh must not leave half-applied state behind."""
    tenant = tenant_factory(slug="acme")
    user = user_factory(tenant, email="rahul@acme.com")
    raw = login("acme", "rahul@acme.com").json()["refresh_token"]

    user.status = UserStatus.INACTIVE.value
    db_session.flush()
    assert client.post(REFRESH_URL, json={"refresh_token": raw}).status_code == 401

    # Re-activating must restore the ability to use the still-valid token.
    user.status = UserStatus.ACTIVE.value
    db_session.flush()
    assert client.post(REFRESH_URL, json={"refresh_token": raw}).status_code == 200


# ---------------------------------------------------------------------------
# 34. Logout
# ---------------------------------------------------------------------------


def test_logout_revokes_the_refresh_token(
    db_session: Session,
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    raw = login("acme", "rahul@acme.com").json()["refresh_token"]

    response = client.post(LOGOUT_URL, json={"refresh_token": raw})

    assert response.status_code == 204
    record = db_session.scalars(select(RefreshToken)).one()
    assert record.revoked_at is not None

    # The token is unusable afterwards.
    assert client.post(REFRESH_URL, json={"refresh_token": raw}).status_code == 401


def test_logout_is_idempotent_and_does_not_probe(client: TestClient) -> None:
    """Unknown/already-revoked tokens return the same 204, revealing nothing."""
    unknown = generate_raw_token()

    assert client.post(LOGOUT_URL, json={"refresh_token": unknown}).status_code == 204
    assert client.post(LOGOUT_URL, json={"refresh_token": unknown}).status_code == 204


def test_logout_only_affects_the_supplied_session(
    db_session: Session,
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """Logging out on one device must not sign the user out everywhere."""
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    first = login("acme", "rahul@acme.com").json()["refresh_token"]
    second = login("acme", "rahul@acme.com").json()["refresh_token"]

    assert client.post(LOGOUT_URL, json={"refresh_token": first}).status_code == 204

    assert client.post(REFRESH_URL, json={"refresh_token": first}).status_code == 401
    assert client.post(REFRESH_URL, json={"refresh_token": second}).status_code == 200
