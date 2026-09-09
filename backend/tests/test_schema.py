"""Structural assertions about the migrated schema.

These lock in the tenant-isolation guarantees, the deletion policy and the
indexes the spec requires, so a future migration cannot quietly drop them.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session

#: The six Phase 1 business entities.
PHASE_1_TABLES = {
    "tenants",
    "users",
    "attendance_locations",
    "qr_challenges",
    "attendance_events",
    "audit_logs",
}

#: Phase 2 added exactly one table: authentication state.
PHASE_2_TABLES = {"refresh_tokens"}

#: Phase 11 added self-service onboarding (email verification) and the
#: office-display kiosk mechanism (display tokens).
PHASE_11_TABLES = {"email_verification_tokens", "display_tokens"}

EXPECTED_TABLES = PHASE_1_TABLES | PHASE_2_TABLES | PHASE_11_TABLES

#: Tables that are tenant-owned and therefore must carry tenant_id.
TENANT_SCOPED_TABLES = {
    "users",
    "attendance_locations",
    "qr_challenges",
    "attendance_events",
    "audit_logs",
    "refresh_tokens",
    "email_verification_tokens",
    "display_tokens",
}

#: (table, column) -> (referenced table, ON DELETE action)
EXPECTED_FOREIGN_KEYS = {
    ("users", "tenant_id"): ("tenants", "RESTRICT"),
    ("attendance_locations", "tenant_id"): ("tenants", "RESTRICT"),
    ("qr_challenges", "tenant_id"): ("tenants", "CASCADE"),
    ("qr_challenges", "location_id"): ("attendance_locations", "CASCADE"),
    ("attendance_events", "tenant_id"): ("tenants", "RESTRICT"),
    ("attendance_events", "user_id"): ("users", "RESTRICT"),
    ("audit_logs", "tenant_id"): ("tenants", "SET NULL"),
    ("audit_logs", "actor_user_id"): ("users", "SET NULL"),
    # Phase 2. Refresh tokens are sessions, not records worth preserving, so
    # they cascade - unlike the attendance/audit rules above, left untouched.
    ("refresh_tokens", "user_id"): ("users", "CASCADE"),
    ("refresh_tokens", "tenant_id"): ("tenants", "CASCADE"),
    # Phase 11. Verification tokens are authentication-adjacent ephemeral
    # state, like refresh tokens - they cascade with their user/tenant.
    ("email_verification_tokens", "user_id"): ("users", "CASCADE"),
    ("email_verification_tokens", "tenant_id"): ("tenants", "CASCADE"),
    # Display tokens are kiosk *configuration*, not a session - RESTRICT
    # matches attendance_locations (a tenant with a live display cannot be
    # deleted by accident). The creating admin alone is SET NULL, matching
    # audit_logs.actor_user_id: the record of which kiosk exists must
    # outlive whichever admin happened to set it up.
    ("display_tokens", "tenant_id"): ("tenants", "RESTRICT"),
    ("display_tokens", "location_id"): ("attendance_locations", "RESTRICT"),
    ("display_tokens", "created_by_user_id"): ("users", "SET NULL"),
}


def test_all_expected_tables_exist(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert PHASE_1_TABLES <= tables
    assert PHASE_2_TABLES <= tables
    # Only the declared entities plus Alembic's bookkeeping table.
    assert tables - EXPECTED_TABLES == {"alembic_version"}


@pytest.mark.parametrize("table", sorted(TENANT_SCOPED_TABLES))
def test_tenant_scoped_tables_have_tenant_id(engine: Engine, table: str) -> None:
    columns = {c["name"] for c in inspect(engine).get_columns(table)}
    assert "tenant_id" in columns


def test_no_plaintext_password_column_exists(engine: Session | Engine) -> None:
    """Passwords may only ever be stored hashed."""
    inspector = inspect(engine)
    for table in EXPECTED_TABLES:
        for column in inspector.get_columns(table):
            name = column["name"].lower()
            assert name != "password", f"{table}.{name}"
            assert "password" not in name or name == "password_hash", f"{table}.{name}"


def test_foreign_keys_and_delete_rules(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT tc.table_name,
                   kcu.column_name,
                   ccu.table_name AS referenced_table,
                   rc.delete_rule
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON kcu.constraint_name = tc.constraint_name
             AND kcu.constraint_schema = tc.constraint_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.constraint_schema = tc.constraint_schema
            JOIN information_schema.referential_constraints rc
              ON rc.constraint_name = tc.constraint_name
             AND rc.constraint_schema = tc.constraint_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
            """
        )
    ).all()

    actual = {
        (r.table_name, r.column_name): (r.referenced_table, r.delete_rule) for r in rows
    }
    assert actual == EXPECTED_FOREIGN_KEYS


def test_unique_constraints(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT tc.table_name, tc.constraint_name,
                   string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position) AS cols
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON kcu.constraint_name = tc.constraint_name
             AND kcu.constraint_schema = tc.constraint_schema
            WHERE tc.constraint_type = 'UNIQUE'
              AND tc.table_schema = 'public'
            GROUP BY tc.table_name, tc.constraint_name
            """
        )
    ).all()

    actual = {(r.table_name, r.cols) for r in rows}
    assert actual == {
        ("tenants", "slug"),
        ("users", "tenant_id,employee_code"),
        ("users", "tenant_id,email"),
        ("attendance_locations", "tenant_id"),
        ("qr_challenges", "nonce"),
        ("refresh_tokens", "token_hash"),
        ("email_verification_tokens", "token_hash"),
        ("display_tokens", "token_hash"),
    }


def test_required_indexes_exist(engine: Engine) -> None:
    inspector = inspect(engine)

    def indexed_column_sets(table: str) -> set[tuple[str, ...]]:
        """Column tuples covered by an index or a unique constraint."""
        sets = {
            tuple(ix["column_names"]) for ix in inspector.get_indexes(table)  # type: ignore[arg-type]
        }
        sets |= {
            tuple(uc["column_names"]) for uc in inspector.get_unique_constraints(table)
        }
        return sets

    users = indexed_column_sets("users")
    assert ("tenant_id",) in users

    events = indexed_column_sets("attendance_events")
    assert ("tenant_id",) in events
    assert ("user_id",) in events
    assert ("event_timestamp",) in events
    assert ("tenant_id", "user_id", "event_timestamp") in events

    challenges = indexed_column_sets("qr_challenges")
    assert ("tenant_id",) in challenges
    assert ("expires_at",) in challenges
    # `nonce` is served by the UNIQUE constraint's index, not a second index.
    assert ("nonce",) in challenges

    logs = indexed_column_sets("audit_logs")
    assert ("tenant_id",) in logs
    assert ("actor_user_id",) in logs
    assert ("created_at",) in logs

    # Phase 2.
    tokens = indexed_column_sets("refresh_tokens")
    assert ("user_id",) in tokens
    assert ("tenant_id",) in tokens
    assert ("expires_at",) in tokens
    # token_hash lookups ride the UNIQUE constraint's index.
    assert ("token_hash",) in tokens

    # Phase 11.
    verifications = indexed_column_sets("email_verification_tokens")
    assert ("user_id",) in verifications
    assert ("expires_at",) in verifications
    assert ("token_hash",) in verifications

    displays = indexed_column_sets("display_tokens")
    assert ("tenant_id",) in displays
    assert ("location_id",) in displays
    assert ("token_hash",) in displays


def test_active_refresh_token_index_is_partial(db_session: Session) -> None:
    """The active-session index must carry its WHERE clause."""
    definition = db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes"
            " WHERE schemaname = 'public'"
            "   AND indexname = 'ix_refresh_tokens_user_id_active'"
        )
    ).scalar_one()

    assert "WHERE (revoked_at IS NULL)" in definition


def test_refresh_tokens_store_no_raw_token_column(engine: Engine) -> None:
    """There must be no column that could hold a usable raw token."""
    columns = {c["name"] for c in inspect(engine).get_columns("refresh_tokens")}

    assert "token_hash" in columns
    assert "token" not in columns
    assert "raw_token" not in columns
    assert columns == {
        "id",
        "user_id",
        "tenant_id",
        "token_hash",
        "expires_at",
        "revoked_at",
        "created_at",
    }


def test_verification_and_display_tokens_store_no_raw_token_column(
    engine: Engine,
) -> None:
    """Same guarantee as `test_refresh_tokens_store_no_raw_token_column`,
    extended to Phase 11's two new hashed-token tables."""
    for table in ("email_verification_tokens", "display_tokens"):
        columns = {c["name"] for c in inspect(engine).get_columns(table)}
        assert "token_hash" in columns, table
        assert "token" not in columns, table
        assert "raw_token" not in columns, table


def test_restrict_protects_attendance_data(db_session: Session) -> None:
    """Deleting a tenant that still has users/attendance must fail loudly."""
    from app.models import AttendanceEvent, AttendanceEventType, Tenant, User, VerificationStatus
    from sqlalchemy.exc import IntegrityError

    tenant = Tenant(name="Delete Me", slug="delete-me")
    db_session.add(tenant)
    db_session.flush()
    user = User(
        tenant_id=tenant.id,
        employee_code="EMP-001",
        name="Ada",
        email="ada@delete-me.test",
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(
        AttendanceEvent(
            tenant_id=tenant.id,
            user_id=user.id,
            event_type=AttendanceEventType.CHECK_IN,
            verification_status=VerificationStatus.VERIFIED,
        )
    )
    db_session.commit()

    db_session.delete(tenant)
    with pytest.raises(IntegrityError):
        db_session.flush()
