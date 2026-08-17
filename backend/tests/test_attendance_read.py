"""Staff self-service attendance reads (spec checks 1-15, 61-65).

Covers ``GET /attendance/me`` and ``GET /attendance/me/history``: session
shaping, day status, date filtering, pagination and the UTC boundary rules.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceEvent,
    AttendanceEventType,
    AttendanceLocation,
    Tenant,
    User,
    UserRole,
)
from app.services.attendance import queries
from tests.conftest import auth_header

ME_URL = "/api/v1/attendance/me"
HISTORY_URL = "/api/v1/attendance/me/history"

TODAY = queries.utc_today()
YESTERDAY = TODAY - timedelta(days=1)


def at(day: date, hour: int, minute: int = 0, second: int = 0) -> datetime:
    """A UTC instant on ``day``."""
    return datetime.combine(day, time(hour, minute, second), tzinfo=UTC)


def utc_clock(iso_timestamp: str) -> str:
    """The UTC wall-clock time of a serialised timestamp, as ``HH:MM:SS``.

    Never slice the ISO string: responses carry whatever offset the database
    session is in (+05:30 on this machine, +00:00 under Docker), so
    ``iso[11:19]`` reads a different clock in the two environments. Parsing and
    converting compares the actual instant.
    """
    return datetime.fromisoformat(iso_timestamp).astimezone(UTC).strftime("%H:%M:%S")


@pytest.fixture
def staff(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> tuple[User, str]:
    tenant = tenant_factory(slug="acme")
    user = user_factory(tenant, email="rahul@acme.com", role=UserRole.STAFF)
    token = login("acme", "rahul@acme.com").json()["access_token"]
    return user, token


def event_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(AttendanceEvent)) or 0


# ---------------------------------------------------------------------------
# 1-2, 6-7. /attendance/me
# ---------------------------------------------------------------------------


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get(ME_URL).status_code == 401
    assert client.get(HISTORY_URL).status_code == 401


def test_me_with_no_events_reports_no_record(
    client: TestClient, staff: tuple[User, str]
) -> None:
    user, token = staff

    body = client.get(ME_URL, headers=auth_header(token)).json()

    assert body["user_id"] == str(user.id)
    assert body["state"] == "NOT_CHECKED_IN"
    assert body["day"]["date"] == TODAY.isoformat()
    assert body["day"]["status"] == "NO_RECORD"
    assert body["day"]["sessions"] == []
    assert body["day"]["first_check_in"] is None
    assert body["day"]["last_check_out"] is None


def test_me_after_check_in_reports_checked_in(
    client: TestClient,
    staff: tuple[User, str],
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    user, token = staff
    event = attendance_event_factory(
        user, event_type=AttendanceEventType.CHECK_IN, at=at(TODAY, 9)
    )

    body = client.get(ME_URL, headers=auth_header(token)).json()

    assert body["state"] == "CHECKED_IN"
    assert body["day"]["status"] == "CHECKED_IN"
    assert len(body["day"]["sessions"]) == 1
    session = body["day"]["sessions"][0]
    assert session["check_in_event_id"] == str(event.id)
    assert session["check_out"] is None
    assert session["check_out_event_id"] is None


def test_me_after_check_out_reports_completed(
    client: TestClient,
    staff: tuple[User, str],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    user, token = staff
    check_in, check_out = attendance_day_factory(user, TODAY, (9, 17))

    body = client.get(ME_URL, headers=auth_header(token)).json()

    assert body["state"] == "NOT_CHECKED_IN"
    assert body["day"]["status"] == "COMPLETED"
    session = body["day"]["sessions"][0]
    assert session["check_in_event_id"] == str(check_in.id)
    assert session["check_out_event_id"] == str(check_out.id)
    assert datetime.fromisoformat(session["check_in"]) == check_in.event_timestamp
    assert datetime.fromisoformat(session["check_out"]) == check_out.event_timestamp


def test_me_accepts_an_explicit_day(
    client: TestClient,
    staff: tuple[User, str],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    user, token = staff
    attendance_day_factory(user, YESTERDAY, (9, 17))

    today = client.get(ME_URL, headers=auth_header(token)).json()
    yesterday = client.get(
        ME_URL, params={"day": YESTERDAY.isoformat()}, headers=auth_header(token)
    ).json()

    assert today["day"]["status"] == "NO_RECORD"
    assert yesterday["day"]["status"] == "COMPLETED"
    assert yesterday["day"]["date"] == YESTERDAY.isoformat()


# ---------------------------------------------------------------------------
# 9, 62-64. Session shaping
# ---------------------------------------------------------------------------


def test_multiple_sessions_are_not_collapsed(
    client: TestClient,
    staff: tuple[User, str],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    """CHECK_IN/OUT twice in a day must surface as two sessions."""
    user, token = staff
    attendance_day_factory(user, TODAY, (9, 12), (13, 17))

    day = client.get(ME_URL, headers=auth_header(token)).json()["day"]

    assert day["status"] == "COMPLETED"
    assert len(day["sessions"]) == 2
    assert [utc_clock(s["check_in"]) for s in day["sessions"]] == ["09:00:00", "13:00:00"]
    assert [utc_clock(s["check_out"]) for s in day["sessions"]] == ["12:00:00", "17:00:00"]
    # The convenience fields span the whole day.
    assert utc_clock(day["first_check_in"]) == "09:00:00"
    assert utc_clock(day["last_check_out"]) == "17:00:00"


def test_open_session_after_a_completed_one(
    client: TestClient,
    staff: tuple[User, str],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    user, token = staff
    attendance_day_factory(user, TODAY, (9, 12))
    attendance_event_factory(
        user, event_type=AttendanceEventType.CHECK_IN, at=at(TODAY, 13)
    )

    day = client.get(ME_URL, headers=auth_header(token)).json()["day"]

    assert day["status"] == "CHECKED_IN"
    assert len(day["sessions"]) == 2
    assert day["sessions"][1]["check_out"] is None
    assert utc_clock(day["last_check_out"]) == "12:00:00"


def test_overnight_checkout_appears_as_a_session_without_a_check_in(
    client: TestClient,
    staff: tuple[User, str],
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    """A night shift closes on the next UTC day.

    Phase 4 guarantees events alternate per *user*, not per calendar day, so a
    day can legitimately open with a CHECK_OUT. Dropping it would lose a real
    event, so it becomes a session with a null check_in.
    """
    user, token = staff
    attendance_event_factory(
        user, event_type=AttendanceEventType.CHECK_IN, at=at(YESTERDAY, 22)
    )
    closing = attendance_event_factory(
        user, event_type=AttendanceEventType.CHECK_OUT, at=at(TODAY, 6)
    )

    today = client.get(ME_URL, headers=auth_header(token)).json()["day"]

    assert today["status"] == "COMPLETED"
    assert len(today["sessions"]) == 1
    assert today["sessions"][0]["check_in"] is None
    assert today["sessions"][0]["check_in_event_id"] is None
    assert today["sessions"][0]["check_out_event_id"] == str(closing.id)

    # And yesterday still shows the open half.
    yesterday = client.get(
        ME_URL, params={"day": YESTERDAY.isoformat()}, headers=auth_header(token)
    ).json()["day"]
    assert yesterday["status"] == "CHECKED_IN"
    assert yesterday["sessions"][0]["check_out"] is None


# ---------------------------------------------------------------------------
# 42, 65. UTC boundaries - the trap a bare date() would fall into
# ---------------------------------------------------------------------------


def test_days_are_bucketed_by_utc_not_by_server_locale(
    client: TestClient,
    staff: tuple[User, str],
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    """An event at 23:00 UTC belongs to that UTC day.

    The regression this guards: PostgreSQL's session TimeZone follows the host
    (``Asia/Calcutta`` on this machine, ``UTC`` in the Docker image), so a bare
    ``date(event_timestamp)`` would file 23:00 UTC under the *next* day locally
    and the correct day under Docker. Same data, different answers.
    """
    user, token = staff
    late = attendance_event_factory(
        user, event_type=AttendanceEventType.CHECK_IN, at=at(YESTERDAY, 23, 30)
    )

    yesterday = client.get(
        ME_URL, params={"day": YESTERDAY.isoformat()}, headers=auth_header(token)
    ).json()["day"]
    today = client.get(ME_URL, headers=auth_header(token)).json()["day"]

    assert yesterday["status"] == "CHECKED_IN"
    assert yesterday["sessions"][0]["check_in_event_id"] == str(late.id)
    assert today["status"] == "NO_RECORD"


def test_midnight_boundaries_are_half_open(
    client: TestClient,
    staff: tuple[User, str],
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    """00:00:00 starts a day; 23:59:59 ends the previous one."""
    user, token = staff
    attendance_event_factory(
        user, event_type=AttendanceEventType.CHECK_IN, at=at(YESTERDAY, 23, 59, 59)
    )
    attendance_event_factory(
        user, event_type=AttendanceEventType.CHECK_OUT, at=at(TODAY, 0, 0, 0)
    )

    yesterday = client.get(
        ME_URL, params={"day": YESTERDAY.isoformat()}, headers=auth_header(token)
    ).json()["day"]
    today = client.get(ME_URL, headers=auth_header(token)).json()["day"]

    assert len(yesterday["sessions"]) == 1
    assert yesterday["sessions"][0]["check_out"] is None
    assert len(today["sessions"]) == 1
    assert today["sessions"][0]["check_in"] is None
    assert utc_clock(today["sessions"][0]["check_out"]) == "00:00:00"


# ---------------------------------------------------------------------------
# 3, 10-14, 61. History
# ---------------------------------------------------------------------------


def test_history_returns_every_day_in_range_including_empty_ones(
    client: TestClient,
    staff: tuple[User, str],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    """Gaps must be visible, or a calendar cannot tell 'nothing' from 'no data'."""
    user, token = staff
    day1, day2, day3 = TODAY - timedelta(days=2), TODAY - timedelta(days=1), TODAY
    attendance_day_factory(user, day1, (9, 17))
    attendance_day_factory(user, day3, (10, 18))

    body = client.get(
        HISTORY_URL,
        params={"from_date": day1.isoformat(), "to_date": day3.isoformat()},
        headers=auth_header(token),
    ).json()

    assert [item["date"] for item in body["items"]] == [
        day3.isoformat(),
        day2.isoformat(),
        day1.isoformat(),
    ]
    assert [item["status"] for item in body["items"]] == [
        "COMPLETED",
        "NO_RECORD",
        "COMPLETED",
    ]
    assert body["pagination"]["total"] == 3
    assert body["user_id"] == str(user.id)


@pytest.mark.parametrize(
    ("offset_from", "offset_to", "expected"),
    [
        (1, 1, ["day2"]),
        (2, 1, ["day2", "day1"]),
        (0, 0, ["day3"]),
        (2, 0, ["day3", "day2", "day1"]),
    ],
)
def test_date_filters_select_the_right_days(
    client: TestClient,
    staff: tuple[User, str],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
    offset_from: int,
    offset_to: int,
    expected: list[str],
) -> None:
    user, token = staff
    days = {
        "day1": TODAY - timedelta(days=2),
        "day2": TODAY - timedelta(days=1),
        "day3": TODAY,
    }
    for day in days.values():
        attendance_day_factory(user, day, (9, 17))

    body = client.get(
        HISTORY_URL,
        params={
            "from_date": (TODAY - timedelta(days=offset_from)).isoformat(),
            "to_date": (TODAY - timedelta(days=offset_to)).isoformat(),
        },
        headers=auth_header(token),
    ).json()

    assert [item["date"] for item in body["items"]] == [
        days[name].isoformat() for name in expected
    ]
    assert all(item["status"] == "COMPLETED" for item in body["items"])


def test_history_pagination_is_stable_and_complete(
    client: TestClient, staff: tuple[User, str]
) -> None:
    _user, token = staff
    span_from = TODAY - timedelta(days=9)

    seen: list[str] = []
    for page in (1, 2, 3):
        body = client.get(
            HISTORY_URL,
            params={
                "from_date": span_from.isoformat(),
                "to_date": TODAY.isoformat(),
                "page": page,
                "page_size": 4,
            },
            headers=auth_header(token),
        ).json()
        assert body["pagination"] == {
            "page": page,
            "page_size": 4,
            "total": 10,
            "total_pages": 3,
        }
        seen.extend(item["date"] for item in body["items"])

    assert len(seen) == 10
    assert len(set(seen)) == 10  # no duplicates across pages
    assert seen == sorted(seen, reverse=True)  # newest first, stable


def test_history_page_beyond_the_end_is_empty_not_an_error(
    client: TestClient, staff: tuple[User, str]
) -> None:
    _user, token = staff

    body = client.get(
        HISTORY_URL,
        params={"page": 99, "page_size": 10},
        headers=auth_header(token),
    ).json()

    assert body["items"] == []
    assert body["pagination"]["page"] == 99


def test_history_defaults_to_the_last_30_days(
    client: TestClient, staff: tuple[User, str]
) -> None:
    _user, token = staff

    body = client.get(HISTORY_URL, headers=auth_header(token)).json()

    assert body["to_date"] == TODAY.isoformat()
    assert body["from_date"] == (TODAY - timedelta(days=29)).isoformat()
    assert body["pagination"]["total"] == 30
    assert body["pagination"]["page_size"] == queries.DEFAULT_PAGE_SIZE


# ---------------------------------------------------------------------------
# 12-13, 28. Guard rails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"page_size": 101}, "page size above the maximum"),
        ({"page_size": 0}, "zero page size"),
        ({"page": 0}, "zero page"),
        ({"page": -1}, "negative page"),
        ({"from_date": "not-a-date"}, "unparseable date"),
        ({"from_date": "2026-13-01"}, "impossible month"),
        ({"day": "nonsense"}, "unparseable day"),
    ],
)
def test_invalid_query_parameters_are_rejected(
    client: TestClient, staff: tuple[User, str], params: dict, reason: str
) -> None:
    _user, token = staff
    url = ME_URL if "day" in params else HISTORY_URL

    response = client.get(url, params=params, headers=auth_header(token))

    assert response.status_code == 422, reason


def test_reversed_date_range_is_rejected(
    client: TestClient, staff: tuple[User, str]
) -> None:
    _user, token = staff

    response = client.get(
        HISTORY_URL,
        params={
            "from_date": TODAY.isoformat(),
            "to_date": (TODAY - timedelta(days=5)).isoformat(),
        },
        headers=auth_header(token),
    )

    assert response.status_code == 422
    assert "from_date" in response.json()["detail"]


def test_oversized_date_range_is_rejected(
    client: TestClient, staff: tuple[User, str]
) -> None:
    """A caller must not be able to ask for an unbounded slice of history."""
    _user, token = staff

    too_wide = client.get(
        HISTORY_URL,
        params={
            "from_date": (TODAY - timedelta(days=queries.MAX_RANGE_DAYS)).isoformat(),
            "to_date": TODAY.isoformat(),
        },
        headers=auth_header(token),
    )
    assert too_wide.status_code == 422

    at_limit = client.get(
        HISTORY_URL,
        params={
            "from_date": (
                TODAY - timedelta(days=queries.MAX_RANGE_DAYS - 1)
            ).isoformat(),
            "to_date": TODAY.isoformat(),
        },
        headers=auth_header(token),
    )
    assert at_limit.status_code == 200
    assert at_limit.json()["pagination"]["total"] == queries.MAX_RANGE_DAYS


# ---------------------------------------------------------------------------
# 45-46. Identity cannot be supplied by the client
# ---------------------------------------------------------------------------


def test_me_ignores_client_supplied_identity(
    client: TestClient,
    staff: tuple[User, str],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    """Query, header and body identity must all be inert."""
    user, token = staff
    colleague = user_factory(
        user.tenant, email="priya@acme.com", employee_code="A-2"
    )
    attendance_day_factory(colleague, TODAY, (8, 16))

    attempts = [
        client.get(ME_URL, params={"user_id": str(colleague.id)}, headers=auth_header(token)),
        client.get(
            ME_URL,
            params={"tenant_id": str(uuid.uuid4())},
            headers=auth_header(token),
        ),
        client.get(
            ME_URL,
            headers={
                **auth_header(token),
                "X-User-Id": str(colleague.id),
                "X-Tenant-Id": str(uuid.uuid4()),
            },
        ),
        client.request(
            "GET", ME_URL, json={"user_id": str(colleague.id)}, headers=auth_header(token)
        ),
    ]

    for response in attempts:
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == str(user.id)
        # The caller has no events; the colleague does. Leaking would show here.
        assert body["day"]["status"] == "NO_RECORD"


def test_history_ignores_client_supplied_identity(
    client: TestClient,
    staff: tuple[User, str],
    user_factory: Callable[..., User],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    user, token = staff
    colleague = user_factory(user.tenant, email="priya@acme.com", employee_code="A-2")
    attendance_day_factory(colleague, TODAY, (8, 16))

    body = client.get(
        HISTORY_URL,
        params={"user_id": str(colleague.id), "tenant_id": str(uuid.uuid4())},
        headers=auth_header(token),
    ).json()

    assert body["user_id"] == str(user.id)
    assert all(item["status"] == "NO_RECORD" for item in body["items"])


# ---------------------------------------------------------------------------
# 26, 48. Privacy
# ---------------------------------------------------------------------------


def test_reads_expose_no_verification_evidence(
    client: TestClient,
    staff: tuple[User, str],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    """Timestamps and event ids only - no GPS, distance, challenge or nonce."""
    user, token = staff
    attendance_day_factory(user, TODAY, (9, 17))

    for url in (ME_URL, HISTORY_URL):
        text = client.get(url, headers=auth_header(token)).text.lower()
        for leaked in (
            "nonce",
            "challenge",
            "latitude",
            "longitude",
            "distance",
            "accuracy",
            "verification_metadata",
            "password",
            "$argon2",
            "token",
        ):
            assert leaked not in text, (url, leaked)


# ---------------------------------------------------------------------------
# 25, 47, 74. Reads never mutate
# ---------------------------------------------------------------------------


def test_read_endpoints_create_no_attendance_events(
    client: TestClient,
    db_session: Session,
    staff: tuple[User, str],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    user, token = staff
    attendance_day_factory(user, TODAY, (9, 17))
    before = event_count(db_session)
    before_ids = {
        e.id for e in db_session.scalars(select(AttendanceEvent))
    }

    for _ in range(3):
        client.get(ME_URL, headers=auth_header(token))
        client.get(HISTORY_URL, headers=auth_header(token))
        client.get(
            ME_URL, params={"day": YESTERDAY.isoformat()}, headers=auth_header(token)
        )

    db_session.expire_all()
    assert event_count(db_session) == before == 2
    assert {e.id for e in db_session.scalars(select(AttendanceEvent))} == before_ids


def test_read_endpoints_reject_write_methods(
    client: TestClient, staff: tuple[User, str]
) -> None:
    _user, token = staff

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = client.request(method, ME_URL, headers=auth_header(token))
        assert response.status_code == 405, method
