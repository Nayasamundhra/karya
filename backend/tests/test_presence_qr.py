"""Dynamic QR challenge lifecycle (spec checks 13-28).

Covers issuance authorization, nonce quality, expiry, replay protection and the
tenant/location binding.
"""

from __future__ import annotations

import string
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceLocation,
    AuditLog,
    QRChallenge,
    QRChallengeStatus,
    Tenant,
    User,
    UserRole,
)
from app.services.presence import qr as qr_service
from app.services.presence.results import FailureReason
from app.services.presence.service import ACTION_QR_CHALLENGE_CREATED
from tests.conftest import auth_header

CHALLENGE_URL = "/api/v1/presence/qr/challenge"


@pytest.fixture
def issue(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., AttendanceLocation],
) -> Callable[..., Response]:
    """Issue a challenge as a user holding ``role`` in a fresh tenant."""

    def _issue(role: UserRole = UserRole.MANAGER, *, with_location: bool = True) -> Response:
        tenant = tenant_factory(slug="acme")
        if with_location:
            location_factory(tenant)
        user_factory(tenant, email="issuer@acme.com", role=role)
        token = login("acme", "issuer@acme.com").json()["access_token"]
        return client.post(CHALLENGE_URL, headers=auth_header(token))

    return _issue


# ---------------------------------------------------------------------------
# 13-16. Who may issue a challenge
# ---------------------------------------------------------------------------


def test_manager_can_generate_a_challenge(issue: Callable[..., Response]) -> None:
    response = issue(UserRole.MANAGER)

    assert response.status_code == 201
    body = response.json()
    assert uuid.UUID(body["challenge_id"])
    assert body["nonce"]
    assert body["expires_in"] == 30
    assert set(body) == {"challenge_id", "nonce", "expires_at", "expires_in"}


def test_tenant_admin_can_generate_a_challenge(issue: Callable[..., Response]) -> None:
    assert issue(UserRole.TENANT_ADMIN).status_code == 201


def test_staff_cannot_generate_a_challenge(issue: Callable[..., Response]) -> None:
    """STAFF issuing codes would defeat the second signal entirely."""
    response = issue(UserRole.STAFF)

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


def test_super_admin_cannot_generate_a_tenant_challenge(
    issue: Callable[..., Response],
) -> None:
    """Consistent with Phase 2: SUPER_ADMIN is not an implicit wildcard."""
    assert issue(UserRole.SUPER_ADMIN).status_code == 403


def test_challenge_generation_requires_authentication(client: TestClient) -> None:
    assert client.post(CHALLENGE_URL).status_code == 401


def test_challenge_generation_needs_an_active_location(
    issue: Callable[..., Response],
) -> None:
    response = issue(UserRole.MANAGER, with_location=False)

    assert response.status_code == 409
    assert "location" in response.json()["detail"].lower()


def test_inactive_location_is_not_usable(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    tenant = tenant_factory(slug="acme")
    location_factory(tenant, status="INACTIVE")
    user_factory(tenant, email="m@acme.com", role=UserRole.MANAGER)
    token = login("acme", "m@acme.com").json()["access_token"]

    assert client.post(CHALLENGE_URL, headers=auth_header(token)).status_code == 409


# ---------------------------------------------------------------------------
# 17-19. Nonce and expiry are server-generated
# ---------------------------------------------------------------------------


def test_nonce_is_unpredictable_and_unique() -> None:
    nonces = {qr_service.generate_nonce() for _ in range(200)}

    # 200 draws from a 256-bit space: a collision would mean the generator is
    # not what it claims to be.
    assert len(nonces) == 200

    alphabet = set(string.ascii_letters + string.digits + "-_")
    for nonce in nonces:
        # 32 bytes, url-safe base64 encoded.
        assert len(nonce) >= 40
        assert set(nonce) <= alphabet
        # Not a timestamp, counter or bare UUID.
        assert not nonce.isdigit()
        with pytest.raises(ValueError):
            uuid.UUID(nonce)


def test_nonce_entropy_is_spread_across_the_alphabet() -> None:
    """A sequential or time-derived source would show far less variety."""
    sample = "".join(qr_service.generate_nonce() for _ in range(50))

    # A CSPRNG over a 64-character alphabet should hit most of it in ~2000 draws.
    assert len(set(sample)) > 40
    # And no single character should dominate.
    assert max(sample.count(c) for c in set(sample)) < len(sample) // 4


def test_nonce_is_persisted_and_unique_across_tenants(
    db_session: Session,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    acme = tenant_factory(slug="acme")
    beta = tenant_factory(slug="beta")
    a = qr_service.create_challenge(
        db_session, tenant_id=acme.id, location_id=location_factory(acme).id
    )
    b = qr_service.create_challenge(
        db_session, tenant_id=beta.id, location_id=location_factory(beta).id
    )

    assert a.nonce != b.nonce
    assert a.status == QRChallengeStatus.ACTIVE
    assert a.used_at is None


def test_expires_at_is_generated_by_the_server(
    db_session: Session,
    issue: Callable[..., Response],
) -> None:
    """The client neither sends nor influences the expiry."""
    before = datetime.now(UTC)
    response = issue(UserRole.MANAGER)
    after = datetime.now(UTC)

    challenge = db_session.scalars(select(QRChallenge)).one()
    assert challenge.expires_at.tzinfo is not None
    assert before + timedelta(seconds=29) <= challenge.expires_at
    assert challenge.expires_at <= after + timedelta(seconds=31)

    # Compare instants, not strings. TIMESTAMPTZ stores an absolute point in
    # time; the offset it comes back with depends on the server's TimeZone
    # setting (+05:30 here, UTC in the Docker image), so the same instant has
    # more than one valid spelling.
    returned = datetime.fromisoformat(response.json()["expires_at"])
    assert returned.tzinfo is not None
    assert abs((returned - challenge.expires_at).total_seconds()) < 0.001


def test_client_cannot_choose_the_expiry(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., AttendanceLocation],
    db_session: Session,
) -> None:
    tenant = tenant_factory(slug="acme")
    location_factory(tenant)
    user_factory(tenant, email="m@acme.com", role=UserRole.MANAGER)
    token = login("acme", "m@acme.com").json()["access_token"]

    # A body is not even part of the contract; anything sent is ignored.
    response = client.post(
        CHALLENGE_URL,
        json={"expires_in": 86400, "ttl_seconds": 86400},
        headers=auth_header(token),
    )

    assert response.status_code == 201
    assert response.json()["expires_in"] == 30
    challenge = db_session.scalars(select(QRChallenge)).one()
    assert challenge.expires_at < datetime.now(UTC) + timedelta(minutes=1)


def test_ttl_is_configurable(
    db_session: Session,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    from app.core.config import Settings

    config = Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="test",
        jwt_secret_key="a-sufficiently-long-test-secret-key-1234",
        qr_challenge_ttl_seconds=90,
    )
    tenant = tenant_factory(slug="acme")

    challenge = qr_service.create_challenge(
        db_session,
        tenant_id=tenant.id,
        location_id=location_factory(tenant).id,
        config=config,
    )

    lifetime = challenge.expires_at - datetime.now(UTC)
    assert timedelta(seconds=85) < lifetime <= timedelta(seconds=90)


# ---------------------------------------------------------------------------
# 41. Audit logging of issuance
# ---------------------------------------------------------------------------


def test_challenge_creation_is_audited_without_the_nonce(
    db_session: Session,
    issue: Callable[..., Response],
) -> None:
    response = issue(UserRole.MANAGER)
    nonce = response.json()["nonce"]

    entry = db_session.scalars(
        select(AuditLog).where(AuditLog.action == ACTION_QR_CHALLENGE_CREATED)
    ).one()

    assert entry.target_type == "QRChallenge"
    assert str(entry.target_id) == response.json()["challenge_id"]
    assert entry.actor_user_id is not None
    assert entry.tenant_id is not None
    assert entry.log_metadata is not None
    assert entry.log_metadata["challenge_id"] == response.json()["challenge_id"]
    # The nonce is the secret the challenge protects; it must not be logged.
    assert "nonce" not in entry.log_metadata
    assert nonce not in str(entry.log_metadata)


# ---------------------------------------------------------------------------
# 20-28. Validation and consumption
# ---------------------------------------------------------------------------


@pytest.fixture
def challenge_setup(
    db_session: Session,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> tuple[Tenant, AttendanceLocation, QRChallenge]:
    tenant = tenant_factory(slug="acme")
    location = location_factory(tenant)
    challenge = qr_service.create_challenge(
        db_session, tenant_id=tenant.id, location_id=location.id
    )
    return tenant, location, challenge


def validate(
    session: Session,
    setup: tuple[Tenant, AttendanceLocation, QRChallenge],
    **overrides: object,
) -> object:
    tenant, location, challenge = setup
    kwargs: dict[str, object] = {
        "challenge_id": challenge.id,
        "nonce": challenge.nonce,
        "tenant_id": tenant.id,
        "location_id": location.id,
    }
    kwargs.update(overrides)
    return qr_service.validate_challenge(session, **kwargs)  # type: ignore[arg-type]


def test_fresh_challenge_validates(
    db_session: Session,
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    result = validate(db_session, challenge_setup)

    assert result.verified is True  # type: ignore[attr-defined]
    assert result.reason is None  # type: ignore[attr-defined]


def test_expired_challenge_is_rejected_and_marked_expired(
    db_session: Session,
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    _tenant, _location, challenge = challenge_setup
    challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()

    result = validate(db_session, challenge_setup)

    assert result.verified is False  # type: ignore[attr-defined]
    assert result.reason is FailureReason.QR_EXPIRED  # type: ignore[attr-defined]
    # Lazy expiration: the row is tidied up on detection, no worker needed.
    db_session.flush()
    assert challenge.status == QRChallengeStatus.EXPIRED


def test_used_challenge_is_rejected(
    db_session: Session,
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    tenant, location, challenge = challenge_setup
    assert qr_service.consume_challenge(
        db_session,
        challenge_id=challenge.id,
        nonce=challenge.nonce,
        tenant_id=tenant.id,
        location_id=location.id,
    )

    result = validate(db_session, challenge_setup)

    assert result.verified is False  # type: ignore[attr-defined]
    assert result.reason is FailureReason.QR_ALREADY_USED  # type: ignore[attr-defined]


def test_revoked_challenge_is_rejected(
    db_session: Session,
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    tenant, _location, challenge = challenge_setup
    assert qr_service.revoke_challenge(
        db_session, challenge_id=challenge.id, tenant_id=tenant.id
    )

    result = validate(db_session, challenge_setup)

    assert result.verified is False  # type: ignore[attr-defined]
    assert result.reason is FailureReason.QR_REVOKED  # type: ignore[attr-defined]


def test_revocation_is_tenant_scoped(
    db_session: Session,
    tenant_factory: Callable[..., Tenant],
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    _tenant, _location, challenge = challenge_setup
    other = tenant_factory(slug="beta")

    # Another tenant cannot revoke it.
    assert (
        qr_service.revoke_challenge(
            db_session, challenge_id=challenge.id, tenant_id=other.id
        )
        is False
    )
    assert challenge.status == QRChallengeStatus.ACTIVE


def test_wrong_nonce_is_rejected(
    db_session: Session,
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    result = validate(db_session, challenge_setup, nonce=qr_service.generate_nonce())

    assert result.verified is False  # type: ignore[attr-defined]
    assert result.reason is FailureReason.QR_NONCE_MISMATCH  # type: ignore[attr-defined]


def test_unknown_challenge_is_rejected(
    db_session: Session,
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    result = validate(db_session, challenge_setup, challenge_id=uuid.uuid4())

    assert result.verified is False  # type: ignore[attr-defined]
    assert result.reason is FailureReason.QR_NOT_FOUND  # type: ignore[attr-defined]


def test_tenant_mismatch_is_rejected(
    db_session: Session,
    tenant_factory: Callable[..., Tenant],
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    """Internally distinguishable so a probe is auditable; hidden from clients."""
    other = tenant_factory(slug="beta")

    result = validate(db_session, challenge_setup, tenant_id=other.id)

    assert result.verified is False  # type: ignore[attr-defined]
    assert result.reason is FailureReason.QR_TENANT_MISMATCH  # type: ignore[attr-defined]

    from app.services.presence.results import to_client_reason

    assert to_client_reason(result.reason) is FailureReason.QR_NOT_FOUND  # type: ignore[attr-defined]


def test_location_mismatch_is_rejected(
    db_session: Session,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    """Binding holds even though V1 has one location per tenant."""
    other_location = location_factory(tenant_factory(slug="beta"))

    result = validate(db_session, challenge_setup, location_id=other_location.id)

    assert result.verified is False  # type: ignore[attr-defined]
    assert result.reason is FailureReason.QR_LOCATION_MISMATCH  # type: ignore[attr-defined]


def test_same_challenge_cannot_be_consumed_twice(
    db_session: Session,
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    tenant, location, challenge = challenge_setup
    consume = lambda: qr_service.consume_challenge(  # noqa: E731
        db_session,
        challenge_id=challenge.id,
        nonce=challenge.nonce,
        tenant_id=tenant.id,
        location_id=location.id,
    )

    assert consume() is True
    assert consume() is False
    assert consume() is False


def test_consumption_records_used_at_and_status(
    db_session: Session,
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    tenant, location, challenge = challenge_setup

    qr_service.consume_challenge(
        db_session,
        challenge_id=challenge.id,
        nonce=challenge.nonce,
        tenant_id=tenant.id,
        location_id=location.id,
    )

    stored = db_session.scalar(
        select(QRChallenge)
        .where(QRChallenge.id == challenge.id)
        .execution_options(populate_existing=True)
    )
    assert stored is not None
    assert stored.status == QRChallengeStatus.USED
    assert stored.used_at is not None
    assert stored.used_at.tzinfo is not None


def test_consumption_refuses_wrong_nonce_tenant_location_or_expiry(
    db_session: Session,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    """Every guard is re-checked inside the atomic UPDATE, not just beforehand."""
    tenant, location, challenge = challenge_setup
    other_tenant = tenant_factory(slug="beta")
    other_location = location_factory(other_tenant)

    base = {
        "challenge_id": challenge.id,
        "nonce": challenge.nonce,
        "tenant_id": tenant.id,
        "location_id": location.id,
    }

    assert not qr_service.consume_challenge(db_session, **{**base, "nonce": "wrong"})
    assert not qr_service.consume_challenge(
        db_session, **{**base, "tenant_id": other_tenant.id}
    )
    assert not qr_service.consume_challenge(
        db_session, **{**base, "location_id": other_location.id}
    )
    assert not qr_service.consume_challenge(
        db_session, **{**base, "challenge_id": uuid.uuid4()}
    )
    # Still unconsumed after all of those.
    assert qr_service.consume_challenge(db_session, **base) is True


def test_expired_challenge_cannot_be_consumed(
    db_session: Session,
    challenge_setup: tuple[Tenant, AttendanceLocation, QRChallenge],
) -> None:
    """Expiry is enforced inside the UPDATE by PostgreSQL's own clock."""
    tenant, location, challenge = challenge_setup
    challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()

    assert (
        qr_service.consume_challenge(
            db_session,
            challenge_id=challenge.id,
            nonce=challenge.nonce,
            tenant_id=tenant.id,
            location_id=location.id,
        )
        is False
    )
