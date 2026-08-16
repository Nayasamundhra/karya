"""POST /api/v1/presence/verify (spec checks 30-43)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceEvent,
    AttendanceLocation,
    AuditLog,
    QRChallenge,
    QRChallengeStatus,
    Tenant,
    User,
    UserRole,
)
from app.services.presence import qr as qr_service
from app.services.presence.service import ACTION_PRESENCE_VERIFICATION_FAILED
from tests.conftest import (
    OFFICE_LATITUDE,
    OFFICE_LONGITUDE,
    auth_header,
    offset_north,
)

VERIFY_URL = "/api/v1/presence/verify"

INSIDE_LATITUDE = offset_north(OFFICE_LATITUDE, 73.0)
OUTSIDE_LATITUDE = offset_north(OFFICE_LATITUDE, 350.0)


@dataclass
class Scenario:
    tenant: Tenant
    location: AttendanceLocation
    staff: User
    token: str
    challenge: QRChallenge


@pytest.fixture
def scenario(
    db_session: Session,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., AttendanceLocation],
) -> Callable[..., Scenario]:
    """A tenant with a location, a STAFF member, and one active challenge."""

    def _make(slug: str = "acme", *, role: UserRole = UserRole.STAFF) -> Scenario:
        tenant = tenant_factory(slug=slug)
        location = location_factory(tenant)
        email = f"staff@{slug}.com"
        staff = user_factory(tenant, email=email, role=role)
        token = login(slug, email).json()["access_token"]
        challenge = qr_service.create_challenge(
            db_session, tenant_id=tenant.id, location_id=location.id
        )
        db_session.flush()
        return Scenario(tenant, location, staff, token, challenge)

    return _make


def evidence(scenario: Scenario, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "latitude": INSIDE_LATITUDE,
        "longitude": OFFICE_LONGITUDE,
        "accuracy_meters": 12.5,
        "challenge_id": str(scenario.challenge.id),
        "nonce": scenario.challenge.nonce,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 30-33. The four signal combinations
# ---------------------------------------------------------------------------


def test_valid_gps_and_valid_qr_is_verified(
    client: TestClient, scenario: Callable[..., Scenario]
) -> None:
    s = scenario()

    response = client.post(
        VERIFY_URL, json=evidence(s), headers=auth_header(s.token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert body["status"] == "PRESENCE_VERIFIED"
    assert body["gps"]["verified"] is True
    assert body["gps"]["distance_meters"] == pytest.approx(73.0, abs=1.0)
    assert body["gps"]["accuracy_meters"] == 12.5
    assert body["qr"]["verified"] is True
    assert body["reason"] is None


def test_valid_gps_and_invalid_qr_is_rejected(
    client: TestClient, scenario: Callable[..., Scenario]
) -> None:
    s = scenario()

    response = client.post(
        VERIFY_URL,
        json=evidence(s, nonce=qr_service.generate_nonce()),
        headers=auth_header(s.token),
    )

    body = response.json()
    assert response.status_code == 200
    assert body["verified"] is False
    assert body["status"] == "PRESENCE_REJECTED"
    assert body["gps"]["verified"] is True
    assert body["qr"]["verified"] is False
    assert body["reason"] == "QR_NONCE_MISMATCH"


def test_invalid_gps_and_valid_qr_is_rejected(
    client: TestClient, scenario: Callable[..., Scenario]
) -> None:
    s = scenario()

    response = client.post(
        VERIFY_URL,
        json=evidence(s, latitude=OUTSIDE_LATITUDE),
        headers=auth_header(s.token),
    )

    body = response.json()
    assert body["verified"] is False
    assert body["status"] == "PRESENCE_REJECTED"
    assert body["gps"]["verified"] is False
    assert body["gps"]["distance_meters"] == pytest.approx(350.0, abs=2.0)
    # The QR was fine, and is reported as such.
    assert body["qr"]["verified"] is True
    assert body["reason"] == "OUTSIDE_GEOFENCE"


def test_invalid_gps_and_invalid_qr_is_rejected(
    client: TestClient, scenario: Callable[..., Scenario]
) -> None:
    s = scenario()

    response = client.post(
        VERIFY_URL,
        json=evidence(s, latitude=OUTSIDE_LATITUDE, nonce=qr_service.generate_nonce()),
        headers=auth_header(s.token),
    )

    body = response.json()
    assert body["verified"] is False
    assert body["gps"]["verified"] is False
    assert body["qr"]["verified"] is False
    # GPS is reported first: it is the one the user can act on.
    assert body["reason"] == "OUTSIDE_GEOFENCE"


def test_poor_accuracy_is_rejected_over_http(
    client: TestClient, scenario: Callable[..., Scenario]
) -> None:
    s = scenario()

    response = client.post(
        VERIFY_URL,
        json=evidence(s, latitude=OFFICE_LATITUDE, accuracy_meters=400.0),
        headers=auth_header(s.token),
    )

    assert response.json()["reason"] == "GPS_ACCURACY_TOO_LOW"
    assert response.json()["verified"] is False


def test_missing_attendance_location_is_rejected(
    client: TestClient,
    db_session: Session,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="staff@acme.com")
    token = login("acme", "staff@acme.com").json()["access_token"]

    response = client.post(
        VERIFY_URL,
        json={
            "latitude": OFFICE_LATITUDE,
            "longitude": OFFICE_LONGITUDE,
            "accuracy_meters": 5.0,
            "challenge_id": str(uuid.uuid4()),
            "nonce": qr_service.generate_nonce(),
        },
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["reason"] == "NO_ACTIVE_ATTENDANCE_LOCATION"
    assert response.json()["gps"]["distance_meters"] is None


# ---------------------------------------------------------------------------
# 28 (over HTTP). Replay protection
# ---------------------------------------------------------------------------


def test_the_same_qr_cannot_be_redeemed_twice(
    client: TestClient, scenario: Callable[..., Scenario]
) -> None:
    s = scenario()
    payload = evidence(s)

    first = client.post(VERIFY_URL, json=payload, headers=auth_header(s.token))
    second = client.post(VERIFY_URL, json=payload, headers=auth_header(s.token))

    assert first.json()["verified"] is True
    assert second.json()["verified"] is False
    assert second.json()["reason"] == "QR_ALREADY_USED"
    # GPS was still fine the second time - only the QR was spent.
    assert second.json()["gps"]["verified"] is True


def test_a_rejected_attempt_does_not_burn_the_challenge(
    client: TestClient,
    db_session: Session,
    scenario: Callable[..., Scenario],
) -> None:
    """The reason GPS is checked before the QR is consumed.

    Otherwise anyone could stand outside and repeatedly destroy the office's
    current code - a trivial denial of service against everyone present.
    """
    s = scenario()

    outside = client.post(
        VERIFY_URL,
        json=evidence(s, latitude=OUTSIDE_LATITUDE),
        headers=auth_header(s.token),
    )
    assert outside.json()["verified"] is False

    challenge = db_session.scalar(
        select(QRChallenge)
        .where(QRChallenge.id == s.challenge.id)
        .execution_options(populate_existing=True)
    )
    assert challenge is not None
    assert challenge.status == QRChallengeStatus.ACTIVE
    assert challenge.used_at is None

    # Somebody actually present can still use it.
    good = client.post(VERIFY_URL, json=evidence(s), headers=auth_header(s.token))
    assert good.json()["verified"] is True


def test_expired_challenge_is_rejected_over_http(
    client: TestClient,
    db_session: Session,
    scenario: Callable[..., Scenario],
) -> None:
    s = scenario()
    s.challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()

    response = client.post(VERIFY_URL, json=evidence(s), headers=auth_header(s.token))

    assert response.json()["reason"] == "QR_EXPIRED"
    assert response.json()["verified"] is False


# ---------------------------------------------------------------------------
# 34-39. The client cannot influence identity or verdicts
# ---------------------------------------------------------------------------


def test_verify_requires_authentication(client: TestClient) -> None:
    response = client.post(
        VERIFY_URL,
        json={
            "latitude": OFFICE_LATITUDE,
            "longitude": OFFICE_LONGITUDE,
            "accuracy_meters": 5.0,
            "challenge_id": str(uuid.uuid4()),
            "nonce": "anything",
        },
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "smuggled",
    [
        {"tenant_id": "11111111-1111-1111-1111-111111111111"},
        {"user_id": "22222222-2222-2222-2222-222222222222"},
        {"gps_verified": True},
        {"qr_verified": True},
        {"presence_verified": True},
        {"distance_meters": 1.0},
        {"status": "PRESENCE_VERIFIED"},
        {"verified": True},
    ],
)
def test_verdict_and_identity_fields_are_refused(
    client: TestClient,
    scenario: Callable[..., Scenario],
    smuggled: dict[str, object],
) -> None:
    """extra="forbid" makes a spoofing attempt a loud 422, not a silent no-op."""
    s = scenario()

    response = client.post(
        VERIFY_URL, json=evidence(s, **smuggled), headers=auth_header(s.token)
    )

    assert response.status_code == 422, smuggled


def test_forcing_verified_flags_cannot_rescue_a_failing_attempt(
    client: TestClient, scenario: Callable[..., Scenario]
) -> None:
    """Even if the fields were tolerated, the verdict is computed server-side."""
    s = scenario()

    # Bad GPS plus every flag an attacker might try.
    forced = client.post(
        VERIFY_URL,
        json=evidence(s, latitude=OUTSIDE_LATITUDE, **{"gps_verified": True}),
        headers=auth_header(s.token),
    )
    assert forced.status_code == 422

    # And without the illegal field, the honest evidence still fails.
    honest = client.post(
        VERIFY_URL,
        json=evidence(s, latitude=OUTSIDE_LATITUDE),
        headers=auth_header(s.token),
    )
    assert honest.json()["gps"]["verified"] is False
    assert honest.json()["verified"] is False


def test_client_supplied_distance_is_never_used(
    client: TestClient, scenario: Callable[..., Scenario]
) -> None:
    """A flattering distance in the body is refused; the server computes its own."""
    s = scenario()

    assert (
        client.post(
            VERIFY_URL,
            json=evidence(s, latitude=OUTSIDE_LATITUDE, distance_meters=5.0),
            headers=auth_header(s.token),
        ).status_code
        == 422
    )

    computed = client.post(
        VERIFY_URL,
        json=evidence(s, latitude=OUTSIDE_LATITUDE),
        headers=auth_header(s.token),
    ).json()["gps"]["distance_meters"]
    assert computed == pytest.approx(350.0, abs=2.0)


def test_query_and_header_injection_are_ignored(
    client: TestClient, scenario: Callable[..., Scenario]
) -> None:
    s = scenario()

    response = client.post(
        VERIFY_URL,
        json=evidence(s, latitude=OUTSIDE_LATITUDE),
        params={"gps_verified": "true", "tenant_id": str(uuid.uuid4())},
        headers={**auth_header(s.token), "X-Gps-Verified": "true"},
    )

    assert response.status_code == 200
    assert response.json()["verified"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", 95.0),
        ("latitude", -91.0),
        ("longitude", 181.0),
        ("longitude", -200.0),
        ("accuracy_meters", -1.0),
        ("nonce", ""),
    ],
)
def test_malformed_evidence_is_a_validation_error(
    client: TestClient,
    scenario: Callable[..., Scenario],
    field: str,
    value: object,
) -> None:
    s = scenario()

    response = client.post(
        VERIFY_URL, json=evidence(s, **{field: value}), headers=auth_header(s.token)
    )

    assert response.status_code == 422, (field, value)


def test_tenant_context_comes_from_the_token_not_the_request(
    client: TestClient, scenario: Callable[..., Scenario]
) -> None:
    """Acme's staff verify against Acme's geofence, whatever they claim."""
    s = scenario(slug="acme")

    # These coordinates are inside Acme's geofence, and the caller sends no
    # tenant at all - the server resolved it from the authenticated user.
    response = client.post(VERIFY_URL, json=evidence(s), headers=auth_header(s.token))

    assert response.json()["verified"] is True
    assert "tenant_id" not in response.json()


# ---------------------------------------------------------------------------
# 42-43. Cross-tenant isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_qr_validation_fails(
    client: TestClient,
    db_session: Session,
    scenario: Callable[..., Scenario],
) -> None:
    """Rahul (Acme) must not redeem Beta's challenge, even standing at Beta."""
    acme = scenario(slug="acme")
    beta = scenario(slug="beta")

    response = client.post(
        VERIFY_URL,
        json=evidence(acme, challenge_id=str(beta.challenge.id), nonce=beta.challenge.nonce),
        headers=auth_header(acme.token),
    )

    body = response.json()
    assert body["verified"] is False
    assert body["qr"]["verified"] is False
    # Collapsed to NOT_FOUND: the response must not confirm the id exists
    # elsewhere.
    assert body["reason"] == "QR_NOT_FOUND"

    # Beta's challenge is untouched and still usable by Beta.
    stored = db_session.scalar(
        select(QRChallenge)
        .where(QRChallenge.id == beta.challenge.id)
        .execution_options(populate_existing=True)
    )
    assert stored is not None
    assert stored.status == QRChallengeStatus.ACTIVE
    assert stored.used_at is None


def test_cross_tenant_probe_is_audited_with_the_precise_reason(
    client: TestClient,
    db_session: Session,
    scenario: Callable[..., Scenario],
) -> None:
    """The client sees QR_NOT_FOUND; the audit trail sees a cross-tenant probe."""
    acme = scenario(slug="acme")
    beta = scenario(slug="beta")

    client.post(
        VERIFY_URL,
        json=evidence(acme, challenge_id=str(beta.challenge.id), nonce=beta.challenge.nonce),
        headers=auth_header(acme.token),
    )

    entry = db_session.scalars(
        select(AuditLog).where(AuditLog.action == ACTION_PRESENCE_VERIFICATION_FAILED)
    ).one()
    assert entry.log_metadata is not None
    assert entry.log_metadata["failure_reason"] == "QR_TENANT_MISMATCH"
    assert entry.tenant_id == acme.tenant.id
    assert entry.actor_user_id == acme.staff.id


def test_challenge_generation_is_scoped_to_the_callers_tenant(
    client: TestClient,
    db_session: Session,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    """A manager's challenge binds to their own tenant and location only."""
    acme = tenant_factory(slug="acme")
    beta = tenant_factory(slug="beta")
    acme_location = location_factory(acme)
    beta_location = location_factory(beta)
    user_factory(acme, email="m@acme.com", role=UserRole.MANAGER)
    token = login("acme", "m@acme.com").json()["access_token"]

    created = client.post(
        "/api/v1/presence/qr/challenge", headers=auth_header(token)
    ).json()

    challenge = db_session.scalar(
        select(QRChallenge).where(QRChallenge.id == uuid.UUID(created["challenge_id"]))
    )
    assert challenge is not None
    assert challenge.tenant_id == acme.id
    assert challenge.location_id == acme_location.id
    assert challenge.tenant_id != beta.id
    assert challenge.location_id != beta_location.id


# ---------------------------------------------------------------------------
# 40. Phase 3 creates no attendance events
# ---------------------------------------------------------------------------


def test_no_attendance_event_is_ever_created(
    client: TestClient,
    db_session: Session,
    scenario: Callable[..., Scenario],
) -> None:
    """Presence verification and attendance are separate concerns.

    Turning verified presence into a check-in or check-out is Phase 4's job.
    """
    s = scenario()

    # A success, a replay, a geofence failure and a bad nonce.
    client.post(VERIFY_URL, json=evidence(s), headers=auth_header(s.token))
    client.post(VERIFY_URL, json=evidence(s), headers=auth_header(s.token))
    client.post(
        VERIFY_URL,
        json=evidence(s, latitude=OUTSIDE_LATITUDE),
        headers=auth_header(s.token),
    )
    client.post(
        VERIFY_URL,
        json=evidence(s, nonce=qr_service.generate_nonce()),
        headers=auth_header(s.token),
    )

    assert db_session.scalar(select(func.count()).select_from(AttendanceEvent)) == 0


def test_successful_verification_is_not_audited_but_failures_are(
    client: TestClient,
    db_session: Session,
    scenario: Callable[..., Scenario],
) -> None:
    """Failures are the security signal; a success will become a Phase 4 event."""
    s = scenario()

    client.post(VERIFY_URL, json=evidence(s), headers=auth_header(s.token))
    failures = db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == ACTION_PRESENCE_VERIFICATION_FAILED)
    )
    assert failures == 0

    client.post(VERIFY_URL, json=evidence(s), headers=auth_header(s.token))  # replay
    failures = db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == ACTION_PRESENCE_VERIFICATION_FAILED)
    )
    assert failures == 1


def test_failure_audit_metadata_has_no_nonce(
    client: TestClient,
    db_session: Session,
    scenario: Callable[..., Scenario],
) -> None:
    s = scenario()
    nonce = s.challenge.nonce

    client.post(
        VERIFY_URL,
        json=evidence(s, latitude=OUTSIDE_LATITUDE),
        headers=auth_header(s.token),
    )

    entry = db_session.scalars(
        select(AuditLog).where(AuditLog.action == ACTION_PRESENCE_VERIFICATION_FAILED)
    ).one()
    assert entry.log_metadata is not None
    rendered = str(entry.log_metadata)
    assert nonce not in rendered
    assert "$argon2" not in rendered
    # It does keep the security-useful facts.
    assert entry.log_metadata["failure_reason"] == "OUTSIDE_GEOFENCE"
    assert entry.log_metadata["gps"]["distance_meters"] == pytest.approx(350.0, abs=2.0)
    assert entry.log_metadata["gps"]["accuracy_meters"] == 12.5


def test_decision_metadata_matches_the_documented_jsonb_shape(
    db_session: Session,
    scenario: Callable[..., Scenario],
) -> None:
    """The shape Phase 4 will persist into attendance_events.verification_metadata."""
    from app.services.presence import service as presence_service

    s = scenario()
    decision = presence_service.verify_presence(
        db_session,
        tenant_id=s.tenant.id,
        actor_user_id=s.staff.id,
        latitude=INSIDE_LATITUDE,
        longitude=OFFICE_LONGITUDE,
        accuracy_meters=12.5,
        challenge_id=s.challenge.id,
        nonce=s.challenge.nonce,
    )

    metadata = decision.to_verification_metadata()

    assert decision.verified is True
    assert set(metadata) == {"gps", "qr"}
    assert set(metadata["gps"]) == {"verified", "distance_meters", "accuracy_meters"}
    assert set(metadata["qr"]) == {"verified", "challenge_id"}
    assert metadata["gps"]["verified"] is True
    assert metadata["qr"]["challenge_id"] == str(s.challenge.id)


def test_office_coordinates_are_never_returned(
    client: TestClient, scenario: Callable[..., Scenario]
) -> None:
    """The staff client needs a distance, not the site's exact position."""
    s = scenario()

    response = client.post(VERIFY_URL, json=evidence(s), headers=auth_header(s.token))

    assert str(OFFICE_LATITUDE) not in response.text
    assert str(OFFICE_LONGITUDE) not in response.text
    assert "latitude" not in response.json()["gps"]
    assert "longitude" not in response.json()["gps"]
