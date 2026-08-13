"""Schema-level tests for the six Karya entities.

These cover persistence, relationships, tenant-isolation constraints and the
PostgreSQL-specific behaviour the schema depends on (UUID defaults, TIMESTAMPTZ,
JSONB). No business logic exists yet, so nothing beyond the schema is asserted.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
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
    VerificationStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_tenant(session: Session, slug: str = "acme") -> Tenant:
    tenant = Tenant(name=f"{slug.title()} Technologies", slug=slug)
    session.add(tenant)
    session.flush()
    return tenant


def make_user(
    session: Session,
    tenant: Tenant,
    *,
    employee_code: str = "EMP-001",
    email: str = "staff@acme.test",
) -> User:
    user = User(
        tenant_id=tenant.id,
        employee_code=employee_code,
        name="Ada Lovelace",
        email=email,
    )
    session.add(user)
    session.flush()
    return user


def make_location(
    session: Session, tenant: Tenant, *, name: str = "Head Office"
) -> AttendanceLocation:
    location = AttendanceLocation(
        tenant_id=tenant.id,
        name=name,
        latitude=12.9716,
        longitude=77.5946,
    )
    session.add(location)
    session.flush()
    return location


# ---------------------------------------------------------------------------
# 1. Tenant creation
# ---------------------------------------------------------------------------


def test_tenant_can_be_created(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    db_session.commit()

    stored = db_session.get(Tenant, tenant.id)
    assert stored is not None
    assert stored.name == "Acme Technologies"
    assert stored.slug == "acme"
    # Server default.
    assert stored.status == "ACTIVE"


def test_tenant_slug_is_globally_unique(db_session: Session) -> None:
    make_tenant(db_session, slug="acme")
    db_session.commit()

    db_session.add(Tenant(name="Acme Imposter", slug="acme"))
    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# 2. User references a tenant
# ---------------------------------------------------------------------------


def test_user_references_tenant(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    user = make_user(db_session, tenant)
    db_session.commit()

    assert user.tenant_id == tenant.id
    # Both directions of the relationship resolve.
    assert user.tenant.slug == "acme"
    db_session.refresh(tenant)
    assert [u.id for u in tenant.users] == [user.id]

    # Defaults from the spec.
    assert user.role == UserRole.STAFF
    assert user.status == UserStatus.ACTIVE
    # Authentication is not implemented; no hash is stored yet.
    assert user.password_hash is None


def test_user_requires_an_existing_tenant(db_session: Session) -> None:
    db_session.add(
        User(
            tenant_id=uuid.uuid4(),  # no such tenant
            employee_code="EMP-404",
            name="Ghost",
            email="ghost@nowhere.test",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# 3-5. Per-tenant uniqueness of email and employee_code
# ---------------------------------------------------------------------------


def test_duplicate_email_in_same_tenant_is_rejected(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    make_user(db_session, tenant, employee_code="EMP-001", email="dup@acme.test")
    db_session.commit()

    db_session.add(
        User(
            tenant_id=tenant.id,
            employee_code="EMP-002",  # different code, same email
            name="Second Ada",
            email="dup@acme.test",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_same_email_in_different_tenants_is_allowed(db_session: Session) -> None:
    tenant_a = make_tenant(db_session, slug="acme")
    tenant_b = make_tenant(db_session, slug="globex")

    make_user(db_session, tenant_a, employee_code="EMP-001", email="shared@x.test")
    make_user(db_session, tenant_b, employee_code="EMP-001", email="shared@x.test")
    db_session.commit()

    emails = db_session.scalars(
        select(User.email).where(User.email == "shared@x.test")
    ).all()
    assert len(emails) == 2


def test_duplicate_employee_code_in_same_tenant_is_rejected(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    make_user(db_session, tenant, employee_code="EMP-001", email="one@acme.test")
    db_session.commit()

    db_session.add(
        User(
            tenant_id=tenant.id,
            employee_code="EMP-001",  # same code, different email
            name="Second Ada",
            email="two@acme.test",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# 6-7. Attendance location
# ---------------------------------------------------------------------------


def test_attendance_location_references_tenant(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    location = make_location(db_session, tenant)
    db_session.commit()

    assert location.tenant_id == tenant.id
    assert location.tenant.slug == "acme"
    # Spec defaults.
    assert location.geofence_radius_meters == 150
    assert location.status == "ACTIVE"
    assert location.latitude == pytest.approx(12.9716)
    assert location.longitude == pytest.approx(77.5946)


def test_only_one_attendance_location_per_tenant(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    make_location(db_session, tenant, name="Head Office")
    db_session.commit()

    db_session.add(
        AttendanceLocation(
            tenant_id=tenant.id,
            name="Second Office",
            latitude=1.0,
            longitude=2.0,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_different_tenants_may_each_have_one_location(db_session: Session) -> None:
    tenant_a = make_tenant(db_session, slug="acme")
    tenant_b = make_tenant(db_session, slug="globex")
    make_location(db_session, tenant_a)
    make_location(db_session, tenant_b)
    db_session.commit()

    assert db_session.scalar(select(AttendanceLocation).where(
        AttendanceLocation.tenant_id == tenant_b.id
    )) is not None


# ---------------------------------------------------------------------------
# 8-9. QR challenges
# ---------------------------------------------------------------------------


def test_qr_challenge_references_tenant_and_location(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    location = make_location(db_session, tenant)

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    challenge = QRChallenge(
        tenant_id=tenant.id,
        location_id=location.id,
        nonce="nonce-abc-123",
        expires_at=expires_at,
    )
    db_session.add(challenge)
    db_session.commit()

    assert challenge.tenant.id == tenant.id
    assert challenge.location.id == location.id
    assert challenge.status == QRChallengeStatus.ACTIVE
    assert challenge.used_at is None

    db_session.refresh(location)
    assert [c.id for c in location.qr_challenges] == [challenge.id]


def test_qr_nonce_is_unique(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    location = make_location(db_session, tenant)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)

    db_session.add(
        QRChallenge(
            tenant_id=tenant.id,
            location_id=location.id,
            nonce="collide",
            expires_at=expires_at,
        )
    )
    db_session.commit()

    db_session.add(
        QRChallenge(
            tenant_id=tenant.id,
            location_id=location.id,
            nonce="collide",
            expires_at=expires_at,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# 10. Attendance events
# ---------------------------------------------------------------------------


def test_attendance_event_references_tenant_and_user(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    user = make_user(db_session, tenant)

    event = AttendanceEvent(
        tenant_id=tenant.id,
        user_id=user.id,
        event_type=AttendanceEventType.CHECK_IN,
        verification_status=VerificationStatus.VERIFIED,
        latitude=12.9716,
        longitude=77.5946,
        gps_accuracy_meters=11.5,
    )
    db_session.add(event)
    db_session.commit()

    assert event.tenant.id == tenant.id
    assert event.user.id == user.id
    assert event.event_type == "CHECK_IN"
    assert event.verification_status == "VERIFIED"

    db_session.refresh(user)
    assert [e.id for e in user.attendance_events] == [event.id]


def test_attendance_event_timestamp_is_server_generated(db_session: Session) -> None:
    """The client is never trusted for the authoritative attendance time."""
    tenant = make_tenant(db_session)
    user = make_user(db_session, tenant)

    before = db_session.scalar(select(text("now()")))
    event = AttendanceEvent(
        tenant_id=tenant.id,
        user_id=user.id,
        event_type=AttendanceEventType.CHECK_OUT,
        verification_status=VerificationStatus.MANUAL_REVIEW,
        # event_timestamp deliberately not supplied.
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert event.event_timestamp is not None
    assert event.event_timestamp.tzinfo is not None
    assert event.event_timestamp >= before


def test_attendance_event_gps_fields_are_optional(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    user = make_user(db_session, tenant)

    event = AttendanceEvent(
        tenant_id=tenant.id,
        user_id=user.id,
        event_type=AttendanceEventType.CHECK_IN,
        verification_status=VerificationStatus.REJECTED,
    )
    db_session.add(event)
    db_session.commit()

    assert event.latitude is None
    assert event.longitude is None
    assert event.gps_accuracy_meters is None
    assert event.verification_metadata is None


# ---------------------------------------------------------------------------
# 11. Audit logs
# ---------------------------------------------------------------------------


def test_audit_log_references_tenant_and_actor(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    actor = make_user(db_session, tenant)

    entry = AuditLog(
        tenant_id=tenant.id,
        actor_user_id=actor.id,
        action="USER_CREATED",
        target_type="User",
        target_id=actor.id,
    )
    db_session.add(entry)
    db_session.commit()

    assert entry.tenant is not None and entry.tenant.id == tenant.id
    assert entry.actor is not None and entry.actor.id == actor.id

    db_session.refresh(actor)
    assert [a.id for a in actor.audit_logs] == [entry.id]


def test_audit_log_allows_system_actions(db_session: Session) -> None:
    """Platform-level / system-initiated actions have no tenant and no actor."""
    entry = AuditLog(action="TENANT_SETTINGS_UPDATED")
    db_session.add(entry)
    db_session.commit()

    assert entry.tenant_id is None
    assert entry.actor_user_id is None
    assert entry.target_type is None
    assert entry.log_metadata is None


# ---------------------------------------------------------------------------
# 12. UUID primary keys
# ---------------------------------------------------------------------------


def test_uuid_primary_keys_are_generated(db_session: Session) -> None:
    tenant_a = make_tenant(db_session, slug="acme")
    tenant_b = make_tenant(db_session, slug="globex")
    db_session.commit()

    for tenant in (tenant_a, tenant_b):
        assert isinstance(tenant.id, uuid.UUID)
        assert tenant.id.version == 4
    assert tenant_a.id != tenant_b.id


def test_uuid_primary_key_has_a_server_default(db_session: Session) -> None:
    """A raw INSERT that omits `id` still gets a UUID from PostgreSQL."""
    generated = db_session.execute(
        text(
            "INSERT INTO tenants (name, slug) VALUES ('Raw Insert', 'raw-insert')"
            " RETURNING id"
        )
    ).scalar_one()
    db_session.commit()

    assert isinstance(generated, uuid.UUID)
    assert generated.version == 4


def test_primary_key_columns_are_uuid_not_integer(db_session: Session) -> None:
    inspector = inspect(db_session.get_bind())
    tables = [
        "tenants",
        "users",
        "attendance_locations",
        "qr_challenges",
        "attendance_events",
        "audit_logs",
    ]
    for table in tables:
        columns = {c["name"]: c for c in inspector.get_columns(table)}
        assert columns["id"]["type"].python_type is uuid.UUID, table
        assert columns["id"]["autoincrement"] is False, table


# ---------------------------------------------------------------------------
# 13. Timezone-aware timestamps
# ---------------------------------------------------------------------------


def test_timestamps_are_timezone_aware(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    user = make_user(db_session, tenant)
    location = make_location(db_session, tenant)
    challenge = QRChallenge(
        tenant_id=tenant.id,
        location_id=location.id,
        nonce="tz-check",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    event = AttendanceEvent(
        tenant_id=tenant.id,
        user_id=user.id,
        event_type=AttendanceEventType.CHECK_IN,
        verification_status=VerificationStatus.VERIFIED,
    )
    entry = AuditLog(tenant_id=tenant.id, actor_user_id=user.id, action="USER_CREATED")
    db_session.add_all([challenge, event, entry])
    db_session.commit()

    for obj in (tenant, user, location, challenge, event, entry):
        db_session.refresh(obj)

    aware = [
        tenant.created_at,
        tenant.updated_at,
        user.created_at,
        user.updated_at,
        location.created_at,
        location.updated_at,
        challenge.created_at,
        challenge.expires_at,
        event.created_at,
        event.event_timestamp,
        entry.created_at,
    ]
    for value in aware:
        assert value.tzinfo is not None
        assert value.utcoffset() is not None


def test_timestamp_columns_are_timestamptz(db_session: Session) -> None:
    """Guard against a naive TIMESTAMP slipping into the schema."""
    rows = db_session.execute(
        text(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND data_type LIKE 'timestamp%'
            """
        )
    ).all()

    assert rows, "expected timestamp columns to exist"
    naive = [r for r in rows if r.data_type != "timestamp with time zone"]
    assert naive == []


def test_updated_at_advances_on_update(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    db_session.commit()
    original = tenant.updated_at

    tenant.name = "Acme Technologies International"
    db_session.commit()
    db_session.refresh(tenant)

    assert tenant.updated_at >= original
    assert tenant.created_at <= tenant.updated_at


# ---------------------------------------------------------------------------
# 14. JSONB
# ---------------------------------------------------------------------------


def test_verification_metadata_roundtrips_as_jsonb(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    user = make_user(db_session, tenant)

    metadata = {
        "gps": {"verified": True, "distance_meters": 73, "accuracy_meters": 12},
        "qr": {"verified": True, "challenge_id": str(uuid.uuid4())},
        "signals": ["wifi", "device_integrity"],
        "risk_score": 0.12,
    }
    event = AttendanceEvent(
        tenant_id=tenant.id,
        user_id=user.id,
        event_type=AttendanceEventType.CHECK_IN,
        verification_status=VerificationStatus.VERIFIED,
        verification_metadata=metadata,
    )
    db_session.add(event)
    db_session.commit()

    db_session.expire_all()
    stored = db_session.get(AttendanceEvent, event.id)
    assert stored is not None
    assert stored.verification_metadata == metadata

    # Querying with a JSONB path operator proves the column really is JSONB.
    found = db_session.scalar(
        select(AttendanceEvent.id).where(
            AttendanceEvent.id == event.id,
            AttendanceEvent.verification_metadata["gps"]["distance_meters"].as_integer()
            == 73,
        )
    )
    assert found == event.id


def test_audit_log_metadata_roundtrips_as_jsonb(db_session: Session) -> None:
    tenant = make_tenant(db_session)
    actor = make_user(db_session, tenant)

    payload = {"changed": {"geofence_radius_meters": [150, 200]}, "source": "admin_ui"}
    entry = AuditLog(
        tenant_id=tenant.id,
        actor_user_id=actor.id,
        action="LOCATION_UPDATED",
        target_type="AttendanceLocation",
        target_id=uuid.uuid4(),
        log_metadata=payload,
    )
    db_session.add(entry)
    db_session.commit()

    db_session.expire_all()
    stored = db_session.get(AuditLog, entry.id)
    assert stored is not None
    assert stored.log_metadata == payload

    # The attribute is `log_metadata`, but the column is named `metadata`.
    assert "metadata" in {
        c["name"] for c in inspect(db_session.get_bind()).get_columns("audit_logs")
    }


def test_jsonb_columns_use_the_jsonb_type(db_session: Session) -> None:
    rows = dict(
        db_session.execute(
            text(
                """
                SELECT table_name || '.' || column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND column_name IN ('verification_metadata', 'metadata')
                """
            )
        ).all()
    )
    assert rows == {
        "attendance_events.verification_metadata": "jsonb",
        "audit_logs.metadata": "jsonb",
    }
