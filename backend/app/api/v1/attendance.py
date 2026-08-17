"""Attendance routes: check-in and check-out.

Thin, like the rest of the API layer. Identity and tenant come from the Phase 2
dependency; the whole lifecycle lives in
:mod:`app.services.attendance.service`; presence is re-verified inside that
service on every call.

Both handlers commit exactly once, at the end. That single commit is the
transaction boundary covering the state check, the QR consumption and the
attendance row - so the three cannot be persisted separately.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, require_roles
from app.models.user import User, UserRole
from app.schemas.attendance import (
    AttendanceActionRequest,
    AttendanceActionResponse,
    AttendanceHistoryResponse,
    AttendanceTodayResponse,
    TeamAttendanceResponse,
)
from app.services.attendance import queries as attendance_queries
from app.services.attendance import service as attendance_service

router = APIRouter(prefix="/attendance", tags=["attendance"])

#: Roles allowed to read other people's attendance within their own tenant.
#:
#: STAFF is excluded: attendance is sensitive operational data and a staff member
#: has no business reason to see a colleague's movements. SUPER_ADMIN is not
#: listed either - consistent with Phase 2, it is a platform role and is never an
#: implicit wildcard over tenant data.
TENANT_VIEWER_ROLES = (UserRole.TENANT_ADMIN, UserRole.MANAGER)

TenantViewer = Annotated[User, Depends(require_roles(*TENANT_VIEWER_ROLES))]

_USER_NOT_FOUND = "User not found"


def _record(
    session: DbSession,
    current_user: CurrentUser,
    payload: AttendanceActionRequest,
    action,
) -> AttendanceActionResponse:
    """Run one attendance action and commit.

    A refused attempt is committed too: it wrote an audit row and nothing else,
    and that row is the record that somebody tried. Only an unexpected exception
    skips the commit, in which case the session closes without one and
    PostgreSQL discards every write - including any QR consumption.
    """
    outcome = action(
        session,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=payload.accuracy_meters,
        challenge_id=payload.challenge_id,
        nonce=payload.nonce,
    )
    session.commit()
    return AttendanceActionResponse.from_outcome(outcome)


@router.post(
    "/check-in",
    response_model=AttendanceActionResponse,
    summary="Check in, after verifying presence",
    responses={401: {"description": "Not authenticated"}},
)
def check_in(
    payload: AttendanceActionRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> AttendanceActionResponse:
    """Record a CHECK_IN for the authenticated user.

    Presence is verified here as part of the action - a prior call to
    ``/presence/verify`` neither helps nor is trusted. The user must currently
    be ``NOT_CHECKED_IN``; a duplicate attempt is refused with
    ``ALREADY_CHECKED_IN`` and, deliberately, without consuming the QR
    challenge.
    """
    return _record(session, current_user, payload, attendance_service.check_in)


@router.post(
    "/check-out",
    response_model=AttendanceActionResponse,
    summary="Check out, after verifying presence",
    responses={401: {"description": "Not authenticated"}},
)
def check_out(
    payload: AttendanceActionRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> AttendanceActionResponse:
    """Record a CHECK_OUT for the authenticated user.

    Requires a preceding CHECK_IN: without one the attempt is refused with
    ``NOT_CHECKED_IN``. Needs its own fresh QR challenge, since the one that
    authorised the check-in was consumed by it.
    """
    return _record(session, current_user, payload, attendance_service.check_out)


# ---------------------------------------------------------------------------
# Read endpoints (Phase 5)
# ---------------------------------------------------------------------------
#
# Every handler below is read-only: none writes, and none commits. Dates are UTC
# throughout - see `app.services.attendance.queries` for why that is stated
# explicitly rather than inherited from the server's locale.


def _resolve_range(
    from_date: date_type | None, to_date: date_type | None
) -> tuple[date_type, date_type]:
    """Validate and default a history date range.

    Defaults to the last ``DEFAULT_HISTORY_DAYS`` up to today (UTC). The span is
    capped so a single request cannot ask for an unbounded slice of history.
    """
    today = attendance_queries.utc_today()
    resolved_to = to_date or today
    resolved_from = from_date or (
        resolved_to - timedelta(days=attendance_queries.DEFAULT_HISTORY_DAYS - 1)
    )

    if resolved_from > resolved_to:
        raise HTTPException(
            # Literal 422 rather than the Starlette constant: this version
            # deprecates HTTP_422_UNPROCESSABLE_ENTITY in favour of
            # ..._CONTENT, and the number is stable across both.
            status_code=422,
            detail="from_date must not be after to_date",
        )

    span_days = (resolved_to - resolved_from).days + 1
    if span_days > attendance_queries.MAX_RANGE_DAYS:
        raise HTTPException(
            # Literal 422 rather than the Starlette constant: this version
            # deprecates HTTP_422_UNPROCESSABLE_ENTITY in favour of
            # ..._CONTENT, and the number is stable across both.
            status_code=422,
            detail=(
                "Date range must not exceed "
                f"{attendance_queries.MAX_RANGE_DAYS} days"
            ),
        )
    return resolved_from, resolved_to


PageParam = Annotated[int, Query(ge=1, description="1-based page number")]
PageSizeParam = Annotated[
    int,
    Query(
        ge=1,
        le=attendance_queries.MAX_PAGE_SIZE,
        description="Days per page (max 100)",
    ),
]
FromDateParam = Annotated[
    date_type | None, Query(description="Inclusive start date (UTC)")
]
ToDateParam = Annotated[
    date_type | None, Query(description="Inclusive end date (UTC), defaults to today")
]
DayParam = Annotated[
    date_type | None, Query(description="UTC date to report on, defaults to today")
]


@router.get(
    "/me",
    response_model=AttendanceTodayResponse,
    summary="The caller's own attendance for a day",
    responses={401: {"description": "Not authenticated"}},
)
def read_my_attendance(
    session: DbSession, current_user: CurrentUser, day: DayParam = None
) -> AttendanceTodayResponse:
    """Return the authenticated user's attendance, defaulting to today (UTC).

    Identity comes from the bearer token; a ``user_id`` in the query string, a
    header or a body is ignored entirely. There is no way to ask this endpoint
    about anybody else.
    """
    result = attendance_queries.get_day(
        session, tenant_id=current_user.tenant_id, user_id=current_user.id, day=day
    )
    return AttendanceTodayResponse.build(user_id=current_user.id, day=result)


@router.get(
    "/me/history",
    response_model=AttendanceHistoryResponse,
    summary="The caller's own attendance history",
    responses={
        401: {"description": "Not authenticated"},
        422: {"description": "Invalid date range or pagination"},
    },
)
def read_my_history(
    session: DbSession,
    current_user: CurrentUser,
    from_date: FromDateParam = None,
    to_date: ToDateParam = None,
    page: PageParam = 1,
    page_size: PageSizeParam = attendance_queries.DEFAULT_PAGE_SIZE,
) -> AttendanceHistoryResponse:
    """Paginated daily history for the authenticated user, newest day first."""
    resolved_from, resolved_to = _resolve_range(from_date, to_date)
    result = attendance_queries.get_history(
        session,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        from_date=resolved_from,
        to_date=resolved_to,
        page=page,
        page_size=page_size,
    )
    return AttendanceHistoryResponse.build(
        user_id=current_user.id,
        from_date=resolved_from,
        to_date=resolved_to,
        page=result,
    )


@router.get(
    "/team/today",
    response_model=TeamAttendanceResponse,
    summary="Today's attendance across the caller's tenant",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
    },
)
def read_team_attendance(
    session: DbSession, current_user: TenantViewer, day: DayParam = None
) -> TeamAttendanceResponse:
    """Every active user in the caller's own tenant, with today's attendance.

    The tenant comes from the authenticated user, so there is no parameter that
    could widen the query to another tenant. Users with no events still appear,
    as ``NO_RECORD`` - they are precisely who a manager is looking for.
    """
    team = attendance_queries.get_team_day(
        session, tenant_id=current_user.tenant_id, day=day
    )
    return TeamAttendanceResponse.from_team(team)


@router.get(
    "/users/{user_id}",
    response_model=AttendanceTodayResponse,
    summary="One tenant user's attendance for a day",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": _USER_NOT_FOUND},
    },
)
def read_user_attendance(
    user_id: uuid.UUID,
    session: DbSession,
    current_user: TenantViewer,
    day: DayParam = None,
) -> AttendanceTodayResponse:
    """Attendance for one user in the caller's own tenant.

    A user id belonging to a different tenant returns **404**, identical to an id
    that does not exist anywhere. Distinguishing the two would confirm the id is
    real and turn this into a cross-tenant enumeration oracle.
    """
    target = attendance_queries.find_tenant_user(
        session, tenant_id=current_user.tenant_id, user_id=user_id
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_USER_NOT_FOUND
        )

    result = attendance_queries.get_day(
        session, tenant_id=current_user.tenant_id, user_id=target.id, day=day
    )
    return AttendanceTodayResponse.build(user_id=target.id, day=result)


@router.get(
    "/users/{user_id}/history",
    response_model=AttendanceHistoryResponse,
    summary="One tenant user's attendance history",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": _USER_NOT_FOUND},
        422: {"description": "Invalid date range or pagination"},
    },
)
def read_user_history(
    user_id: uuid.UUID,
    session: DbSession,
    current_user: TenantViewer,
    from_date: FromDateParam = None,
    to_date: ToDateParam = None,
    page: PageParam = 1,
    page_size: PageSizeParam = attendance_queries.DEFAULT_PAGE_SIZE,
) -> AttendanceHistoryResponse:
    """Paginated daily history for one user in the caller's own tenant.

    Remains available for **inactive** users: they are excluded from the live
    dashboard, but their recorded history is an audit record and is never hidden
    or deleted.
    """
    target = attendance_queries.find_tenant_user(
        session, tenant_id=current_user.tenant_id, user_id=user_id
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_USER_NOT_FOUND
        )

    resolved_from, resolved_to = _resolve_range(from_date, to_date)
    result = attendance_queries.get_history(
        session,
        tenant_id=current_user.tenant_id,
        user_id=target.id,
        from_date=resolved_from,
        to_date=resolved_to,
        page=page,
        page_size=page_size,
    )
    return AttendanceHistoryResponse.build(
        user_id=target.id,
        from_date=resolved_from,
        to_date=resolved_to,
        page=result,
    )
