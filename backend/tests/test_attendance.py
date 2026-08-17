"""Attendance check-in / check-out (spec checks 1-36).

Everything goes through the HTTP endpoints, because the security properties
being asserted (server-derived identity, refused smuggled fields) only exist at
that boundary.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import (
    AttendanceEvent,
    AttendanceEventType,
    AttendanceLocation,
    AuditLog,
    QRChallenge,
    QRChallengeStatus,
    Tenant,
    User,
    UserRole,
    UserStatus,
)
from app.services.attendance.service import (
    ACTION_CHECK_IN,
    ACTION_CHECK_IN_FAILED,
    ACTION_CHECK_OUT,
)
from app.services.presence import qr as qr_service
from tests.conftest import (
    OFFICE_LATITUDE,
    OFFICE_LONGITUDE,
    auth_header,
    offset_north,
)

CHECK_IN_URL = "/api/v1/attendance/check-in"
CHECK_OUT_URL = "/api/v1/attendance/check-out"
CHALLENGE_URL = "/api/v1/presence/qr/challenge"

INSIDE = offset_north(OFFICE_LATITUDE, 73.0)
OUTSIDE = offset_north(OFFICE_LATITUDE, 350.0)


@dataclass
class Office:
    tenant: Tenant
    location: AttendanceLocation
    staff: User
    token: str
    manager_token: str


@pytest.fixture
def office(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., AttendanceLocation],
) -> Callable[..., Office]:
    """A tenant with a geofenced site, a STAFF member and a MANAGER."""

    def _make(slug: str = "acme", *, staff_status: UserStatus = UserStatus.ACTIVE) -> Office:
        tenant = tenant_factory(slug=slug)
        location = location_factory(tenant)
        staff = user_factory(
            tenant,
            email=f"rahul@{slug}.com",
            employee_code="EMP-1",
            role=UserRole.STAFF,
            status=staff_status,
        )
        user_factory(
            tenant,
            email=f"manager@{slug}.com",
            employee_code="MGR-1",
            role=UserRole.MANAGER,
        )
        manager_token = login(slug, f"manager@{slug}.com").json()["access_token"]
        staff_login = login(slug, f"rahul@{slug}.com")
        token = (
            staff_login.json()["access_token"]
            if staff_login.status_code == 200
            else ""
        )
        return Office(tenant, location, staff, token, manager_token)

    return _make


def new_challenge(client: TestClient, office: Office) -> dict:
    """Issue a fresh QR challenge through the real endpoint."""
    response = client.post(CHALLENGE_URL, headers=auth_header(office.manager_token))
    assert response.status_code == 201
    return response.json()


def evidence(challenge: dict, *, lat: float = INSIDE, accuracy: float = 12.5) -> dict:
    return {
        "latitude": lat,
        "longitude": OFFICE_LONGITUDE,
        "accuracy_meters": accuracy,
        "challenge_id": challenge["challenge_id"],
        "nonce": challenge["nonce"],
    }


def act(client: TestClient, url: str, office: Office, challenge: dict, **kw) -> Response:
    return client.post(url, json=evidence(challenge, **kw), headers=auth_header(office.token))


def check_in(client: TestClient, office: Office, **kw) -> Response:
    return act(client, CHECK_IN_URL, office, new_challenge(client, office), **kw)


def check_out(client: TestClient, office: Office, **kw) -> Response:
    return act(client, CHECK_OUT_URL, office, new_challenge(client, office), **kw)


def event_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(AttendanceEvent)) or 0


# ---------------------------------------------------------------------------
# 1-8. Successful check-in
# ---------------------------------------------------------------------------


def test_staff_can_check_in(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    assert event_count(db_session) == 0

    response = check_in(client, o)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["event_type"] == "CHECK_IN"
    assert body["status"] == "CHECKED_IN"
    assert uuid.UUID(body["attendance_event_id"])
    assert body["event_timestamp"] is not None
    assert body["presence"]["verified"] is True
    assert body["presence"]["gps"]["distance_meters"] == pytest.approx(73.0, abs=1.0)
    assert body["reason"] is None


def test_check_in_creates_exactly_one_event_with_correct_content(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()

    body = check_in(client, o).json()

    event = db_session.scalars(select(AttendanceEvent)).one()
    assert str(event.id) == body["attendance_event_id"]
    assert event.tenant_id == o.tenant.id
    assert event.user_id == o.staff.id
    assert event.event_type == AttendanceEventType.CHECK_IN
    assert event.verification_status == "VERIFIED"
    assert event.latitude == pytest.approx(INSIDE)
    assert event.gps_accuracy_meters == 12.5


def test_event_timestamp_is_server_generated(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    """The device clock never reaches event_timestamp."""
    o = office()
    before = db_session.scalar(select(text("now()")))

    body = check_in(client, o).json()

    event = db_session.scalars(select(AttendanceEvent)).one()
    after = db_session.scalar(select(text("now()")))
    assert event.event_timestamp.tzinfo is not None
    assert before <= event.event_timestamp <= after
    # Same instant surfaced to the client (offsets may differ; compare moments).
    returned = datetime.fromisoformat(body["event_timestamp"])
    assert abs((returned - event.event_timestamp).total_seconds()) < 0.001


def test_verification_metadata_is_stored_without_the_nonce(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    challenge = new_challenge(client, o)
    nonce = challenge["nonce"]

    act(client, CHECK_IN_URL, o, challenge)

    event = db_session.scalars(select(AttendanceEvent)).one()
    metadata = event.verification_metadata
    assert metadata is not None
    assert metadata["presence"]["verified"] is True
    assert metadata["gps"]["verified"] is True
    assert metadata["gps"]["distance_meters"] == pytest.approx(73.0, abs=1.0)
    assert metadata["gps"]["accuracy_meters"] == 12.5
    assert metadata["qr"]["verified"] is True
    assert metadata["qr"]["challenge_id"] == challenge["challenge_id"]
    assert metadata["attendance_state"] == "CHECKED_IN"
    # The challenge id is enough to audit the decision; the nonce is a secret.
    assert nonce not in str(metadata)
    assert "nonce" not in str(metadata).lower()


def test_check_in_consumes_the_qr_challenge(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    challenge = new_challenge(client, o)

    act(client, CHECK_IN_URL, o, challenge)

    stored = db_session.scalar(
        select(QRChallenge)
        .where(QRChallenge.id == uuid.UUID(challenge["challenge_id"]))
        .execution_options(populate_existing=True)
    )
    assert stored is not None
    assert stored.status == QRChallengeStatus.USED
    assert stored.used_at is not None


# ---------------------------------------------------------------------------
# 9-16. Check-in refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "kwargs", "reason"),
    [
        ("outside geofence", {"lat": OUTSIDE}, "OUTSIDE_GEOFENCE"),
        ("poor accuracy", {"accuracy": 400.0}, "GPS_ACCURACY_TOO_LOW"),
    ],
)
def test_gps_failure_refuses_check_in_and_writes_no_event(
    client: TestClient,
    db_session: Session,
    office: Callable[..., Office],
    label: str,
    kwargs: dict,
    reason: str,
) -> None:
    o = office()

    body = check_in(client, o, **kwargs).json()

    assert body["success"] is False
    assert body["reason"] == reason
    assert body["status"] == "NOT_CHECKED_IN"
    assert body["presence"]["verified"] is False
    assert event_count(db_session) == 0


def test_wrong_nonce_refuses_check_in(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    challenge = new_challenge(client, o)
    challenge["nonce"] = qr_service.generate_nonce()

    body = act(client, CHECK_IN_URL, o, challenge).json()

    assert body["success"] is False
    assert body["reason"] == "QR_NONCE_MISMATCH"
    assert event_count(db_session) == 0


def test_unknown_challenge_refuses_check_in(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    challenge = new_challenge(client, o)
    challenge["challenge_id"] = str(uuid.uuid4())

    body = act(client, CHECK_IN_URL, o, challenge).json()

    assert body["reason"] == "QR_NOT_FOUND"
    assert event_count(db_session) == 0


def test_expired_challenge_refuses_check_in(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    challenge = new_challenge(client, o)
    row = db_session.scalar(
        select(QRChallenge).where(QRChallenge.id == uuid.UUID(challenge["challenge_id"]))
    )
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()

    body = act(client, CHECK_IN_URL, o, challenge).json()

    assert body["reason"] == "QR_EXPIRED"
    assert event_count(db_session) == 0


def test_already_used_challenge_refuses_check_in(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    """A challenge spent on a check-in cannot authorise a second one."""
    o = office()
    challenge = new_challenge(client, o)
    assert act(client, CHECK_IN_URL, o, challenge).json()["success"] is True
    act(client, CHECK_OUT_URL, o, new_challenge(client, o))  # back to NOT_CHECKED_IN

    body = act(client, CHECK_IN_URL, o, challenge).json()

    assert body["success"] is False
    assert body["reason"] == "QR_ALREADY_USED"
    assert event_count(db_session) == 2  # the original pair, nothing more


def test_unauthenticated_cannot_check_in(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    challenge = new_challenge(client, o)

    response = client.post(CHECK_IN_URL, json=evidence(challenge))

    assert response.status_code == 401
    assert event_count(db_session) == 0


def test_inactive_user_cannot_check_in(
    client: TestClient,
    db_session: Session,
    office: Callable[..., Office],
) -> None:
    """Deactivation takes effect on the next request, via the auth dependency."""
    o = office()
    challenge = new_challenge(client, o)
    o.staff.status = UserStatus.INACTIVE.value
    db_session.flush()

    response = client.post(
        CHECK_IN_URL, json=evidence(challenge), headers=auth_header(o.token)
    )

    assert response.status_code == 401
    assert event_count(db_session) == 0


# ---------------------------------------------------------------------------
# 17-21. State transitions
# ---------------------------------------------------------------------------


def test_duplicate_check_in_is_refused(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    assert check_in(client, o).json()["success"] is True

    body = check_in(client, o).json()

    assert body["success"] is False
    assert body["reason"] == "ALREADY_CHECKED_IN"
    assert body["status"] == "CHECKED_IN"
    assert event_count(db_session) == 1


def test_duplicate_check_in_does_not_burn_the_challenge(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    """State is checked before evidence, so a rejected duplicate wastes nothing.

    Otherwise a user tapping twice would destroy the office's current code for
    everyone else queuing behind them.
    """
    o = office()
    check_in(client, o)
    challenge = new_challenge(client, o)

    assert act(client, CHECK_IN_URL, o, challenge).json()["reason"] == "ALREADY_CHECKED_IN"

    stored = db_session.scalar(
        select(QRChallenge)
        .where(QRChallenge.id == uuid.UUID(challenge["challenge_id"]))
        .execution_options(populate_existing=True)
    )
    assert stored is not None
    assert stored.status == QRChallengeStatus.ACTIVE
    assert stored.used_at is None
    # And it still works for the legitimate next action.
    assert act(client, CHECK_OUT_URL, o, challenge).json()["success"] is True


def test_check_out_without_check_in_is_refused(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()

    body = check_out(client, o).json()

    assert body["success"] is False
    assert body["reason"] == "NOT_CHECKED_IN"
    assert body["status"] == "NOT_CHECKED_IN"
    assert body["presence"] is None  # refused before evidence was examined
    assert event_count(db_session) == 0


def test_duplicate_check_out_is_refused(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    check_in(client, o)
    assert check_out(client, o).json()["success"] is True

    body = check_out(client, o).json()

    assert body["success"] is False
    assert body["reason"] == "NOT_CHECKED_IN"
    assert event_count(db_session) == 2


def test_full_cycle_and_repeat(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    """CHECK_IN -> CHECK_OUT -> CHECK_IN -> CHECK_OUT, as on consecutive days."""
    o = office()

    sequence = []
    for _ in range(2):
        sequence.append(check_in(client, o).json())
        sequence.append(check_out(client, o).json())

    assert [s["success"] for s in sequence] == [True] * 4
    assert [s["event_type"] for s in sequence] == [
        "CHECK_IN",
        "CHECK_OUT",
        "CHECK_IN",
        "CHECK_OUT",
    ]
    assert [s["status"] for s in sequence] == [
        "CHECKED_IN",
        "NOT_CHECKED_IN",
        "CHECKED_IN",
        "NOT_CHECKED_IN",
    ]

    stored = db_session.scalars(
        select(AttendanceEvent).order_by(AttendanceEvent.event_timestamp)
    ).all()
    assert [e.event_type for e in stored] == [
        "CHECK_IN",
        "CHECK_OUT",
        "CHECK_IN",
        "CHECK_OUT",
    ]
    # Strictly alternating - never two of the same in a row.
    assert all(a.event_type != b.event_type for a, b in zip(stored, stored[1:]))


# ---------------------------------------------------------------------------
# 22-25. Check-out specifics
# ---------------------------------------------------------------------------


def test_check_out_records_a_correct_event(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    check_in(client, o)
    before = db_session.scalar(select(text("now()")))

    body = check_out(client, o).json()

    event = db_session.scalar(
        select(AttendanceEvent).where(AttendanceEvent.id == uuid.UUID(body["attendance_event_id"]))
    )
    assert event is not None
    assert event.event_type == AttendanceEventType.CHECK_OUT
    assert event.tenant_id == o.tenant.id
    assert event.user_id == o.staff.id
    assert event.event_timestamp >= before
    assert event.verification_metadata is not None
    assert event.verification_metadata["presence"]["verified"] is True
    assert event.verification_metadata["attendance_state"] == "NOT_CHECKED_IN"
    assert body["status"] == "NOT_CHECKED_IN"


# ---------------------------------------------------------------------------
# 26-32. Security
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "smuggled",
    [
        {"tenant_id": "11111111-1111-1111-1111-111111111111"},
        {"user_id": "22222222-2222-2222-2222-222222222222"},
        {"gps_verified": True},
        {"qr_verified": True},
        {"presence_verified": True},
        {"distance_meters": 0.0},
        {"event_timestamp": "2020-01-01T00:00:00Z"},
        {"attendance_event_id": "33333333-3333-3333-3333-333333333333"},
        {"status": "CHECKED_IN"},
        {"event_type": "CHECK_OUT"},
        {"success": True},
    ],
)
@pytest.mark.parametrize("url", [CHECK_IN_URL, CHECK_OUT_URL])
def test_smuggled_fields_are_refused(
    client: TestClient,
    db_session: Session,
    office: Callable[..., Office],
    smuggled: dict,
    url: str,
) -> None:
    o = office()
    challenge = new_challenge(client, o)

    response = client.post(
        url, json={**evidence(challenge), **smuggled}, headers=auth_header(o.token)
    )

    assert response.status_code == 422, smuggled
    assert event_count(db_session) == 0


def test_distance_spoof_cannot_rescue_a_failing_check_in(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    """Claiming distance 0 from 350 m away is refused, and honestly re-checked."""
    o = office()
    challenge = new_challenge(client, o)

    spoofed = client.post(
        CHECK_IN_URL,
        json={**evidence(challenge, lat=OUTSIDE), "distance_meters": 0.0},
        headers=auth_header(o.token),
    )
    assert spoofed.status_code == 422

    honest = act(client, CHECK_IN_URL, o, challenge, lat=OUTSIDE).json()
    assert honest["success"] is False
    assert honest["presence"]["gps"]["distance_meters"] == pytest.approx(350.0, abs=2.0)
    assert event_count(db_session) == 0


def test_event_is_always_recorded_for_the_authenticated_user(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    """Query and header injection must not redirect the event to someone else."""
    o = office()
    other = o.staff  # the manager is the only other user; grab their id
    victim = db_session.scalars(
        select(User).where(User.tenant_id == o.tenant.id, User.employee_code == "MGR-1")
    ).one()
    challenge = new_challenge(client, o)

    response = client.post(
        f"{CHECK_IN_URL}?user_id={victim.id}&tenant_id={uuid.uuid4()}",
        json=evidence(challenge),
        headers={**auth_header(o.token), "X-User-Id": str(victim.id)},
    )

    assert response.status_code == 200
    event = db_session.scalars(select(AttendanceEvent)).one()
    assert event.user_id == o.staff.id
    assert event.user_id != victim.id
    assert other.id == o.staff.id


def test_cross_tenant_challenge_cannot_create_an_event(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    acme = office(slug="acme")
    beta = office(slug="beta")
    beta_challenge = new_challenge(client, beta)

    body = act(client, CHECK_IN_URL, acme, beta_challenge).json()

    assert body["success"] is False
    assert body["reason"] == "QR_NOT_FOUND"
    assert event_count(db_session) == 0
    # Beta's challenge is untouched and still usable by Beta's own staff.
    assert act(client, CHECK_IN_URL, beta, beta_challenge).json()["success"] is True
    event = db_session.scalars(select(AttendanceEvent)).one()
    assert event.tenant_id == beta.tenant.id


def test_attendance_state_is_per_user_and_per_tenant(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    """One user checking in must not check anyone else in."""
    acme = office(slug="acme")
    beta = office(slug="beta")

    assert check_in(client, acme).json()["success"] is True

    # Beta's staff are still NOT_CHECKED_IN, so a check-out is refused...
    assert check_out(client, beta).json()["reason"] == "NOT_CHECKED_IN"
    # ...and their own check-in works.
    assert check_in(client, beta).json()["success"] is True

    events = db_session.scalars(select(AttendanceEvent)).all()
    assert {e.user_id for e in events} == {acme.staff.id, beta.staff.id}
    assert {e.tenant_id for e in events} == {acme.tenant.id, beta.tenant.id}


# ---------------------------------------------------------------------------
# 33-36. QR single-use across the lifecycle
# ---------------------------------------------------------------------------


def test_check_in_qr_cannot_be_reused_for_check_out(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    """The single-use guarantee spans the two endpoints, not just one."""
    o = office()
    challenge = new_challenge(client, o)
    assert act(client, CHECK_IN_URL, o, challenge).json()["success"] is True

    body = act(client, CHECK_OUT_URL, o, challenge).json()

    assert body["success"] is False
    assert body["reason"] == "QR_ALREADY_USED"
    assert body["status"] == "CHECKED_IN"  # still checked in
    assert event_count(db_session) == 1


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_successful_actions_are_audited(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    check_in_body = check_in(client, o).json()
    check_out_body = check_out(client, o).json()

    entries = {
        e.action: e
        for e in db_session.scalars(
            select(AuditLog).where(AuditLog.action.in_([ACTION_CHECK_IN, ACTION_CHECK_OUT]))
        )
    }
    assert set(entries) == {ACTION_CHECK_IN, ACTION_CHECK_OUT}

    entry = entries[ACTION_CHECK_IN]
    assert entry.tenant_id == o.tenant.id
    assert entry.actor_user_id == o.staff.id
    assert entry.target_type == "AttendanceEvent"
    assert str(entry.target_id) == check_in_body["attendance_event_id"]
    assert entry.log_metadata is not None
    assert entry.log_metadata["event_type"] == "CHECK_IN"
    assert entry.log_metadata["distance_meters"] == pytest.approx(73.0, abs=1.0)
    assert entries[ACTION_CHECK_OUT].log_metadata["event_type"] == "CHECK_OUT"
    assert str(entries[ACTION_CHECK_OUT].target_id) == check_out_body["attendance_event_id"]


def test_failed_attempts_are_audited_once(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    """One rejected action produces one audit row, not a presence row as well."""
    o = office()

    check_in(client, o, lat=OUTSIDE)

    rows = db_session.scalars(select(AuditLog).where(AuditLog.action.like("%FAILED%"))).all()
    assert len(rows) == 1
    assert rows[0].action == ACTION_CHECK_IN_FAILED
    assert rows[0].log_metadata is not None
    assert rows[0].log_metadata["failure_reason"] == "OUTSIDE_GEOFENCE"
    assert rows[0].log_metadata["attempted_event_type"] == "CHECK_IN"
    # The presence service did not also log it.
    presence_rows = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "PRESENCE_VERIFICATION_FAILED")
    ).all()
    assert presence_rows == []


def test_cross_tenant_probe_keeps_its_precise_reason_in_the_audit(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    acme = office(slug="acme")
    beta = office(slug="beta")

    body = act(client, CHECK_IN_URL, acme, new_challenge(client, beta)).json()

    assert body["reason"] == "QR_NOT_FOUND"  # client sees the collapsed reason
    entry = db_session.scalars(
        select(AuditLog).where(AuditLog.action == ACTION_CHECK_IN_FAILED)
    ).one()
    assert entry.log_metadata is not None
    assert entry.log_metadata["failure_reason"] == "QR_TENANT_MISMATCH"
    assert entry.tenant_id == acme.tenant.id


def test_no_audit_metadata_contains_a_nonce(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    o = office()
    challenge = new_challenge(client, o)
    nonce = challenge["nonce"]
    act(client, CHECK_IN_URL, o, challenge)
    check_in(client, o)  # duplicate -> failure audit

    for entry in db_session.scalars(select(AuditLog)):
        rendered = str(entry.log_metadata)
        assert nonce not in rendered
        assert "$argon2" not in rendered


# ---------------------------------------------------------------------------
# Presence endpoint still works alongside attendance
# ---------------------------------------------------------------------------


def test_presence_endpoint_still_works_and_creates_no_attendance(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    """Phase 3's endpoint is unchanged: it verifies, but records no attendance."""
    o = office()
    challenge = new_challenge(client, o)

    body = client.post(
        "/api/v1/presence/verify",
        json=evidence(challenge),
        headers=auth_header(o.token),
    ).json()

    assert body["status"] == "PRESENCE_VERIFIED"
    assert event_count(db_session) == 0


def test_a_prior_presence_verification_does_not_authorise_check_in(
    client: TestClient, db_session: Session, office: Callable[..., Office]
) -> None:
    """The server re-verifies; it never trusts a previous PRESENCE_VERIFIED.

    The challenge consumed by /presence/verify is spent, so re-presenting it to
    check-in fails - there is no way to convert an earlier "I was verified" into
    an attendance event.
    """
    o = office()
    challenge = new_challenge(client, o)
    assert (
        client.post(
            "/api/v1/presence/verify",
            json=evidence(challenge),
            headers=auth_header(o.token),
        ).json()["verified"]
        is True
    )

    body = act(client, CHECK_IN_URL, o, challenge).json()

    assert body["success"] is False
    assert body["reason"] == "QR_ALREADY_USED"
    assert event_count(db_session) == 0
