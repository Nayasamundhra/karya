"""Request/response schemas for the attendance lifecycle.

The request **subclasses** the Phase 3 presence request rather than restating
its fields. That is not just brevity: it means the coordinate bounds, the
``allow_inf_nan=False`` guard and - most importantly - ``extra="forbid"`` are
defined once. If a future phase tightens presence validation, attendance
tightens with it automatically instead of quietly falling behind.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.attendance_event import AttendanceEventType
from app.schemas.presence import (
    GPSVerificationResult,
    PresenceVerificationRequest,
    QRVerificationResult,
)
from app.services.attendance.results import (
    AttendanceDay,
    AttendanceHistoryPage,
    AttendanceOutcome,
    AttendanceSession,
    AttendanceState,
    DayStatus,
    TeamAttendance,
    TeamMemberDay,
)


class AttendanceActionRequest(PresenceVerificationRequest):
    """Evidence for a check-in or check-out.

    Identical to the presence contract: coordinates, accuracy, challenge id and
    nonce. Note what is *absent* - no user, no tenant, no timestamp, no event
    type and no verdict. Those are all determined by the server, and inherited
    ``extra="forbid"`` turns an attempt to supply one into a 422 rather than a
    silently ignored field.
    """


class PresenceSummary(BaseModel):
    """The presence evidence behind an attendance decision."""

    model_config = ConfigDict(extra="forbid")

    verified: bool
    gps: GPSVerificationResult
    qr: QRVerificationResult


class AttendanceActionResponse(BaseModel):
    """The outcome of a check-in or check-out attempt.

    A refusal is reported as ``success: false`` with HTTP 200, matching
    ``/presence/verify``. The request was well-formed and fully processed; the
    answer is "no, and here is exactly why". Returning the presence breakdown
    alongside the reason is what lets a client tell the user *"you are 350 m
    away"* rather than just *"failed"*. HTTP error codes stay reserved for
    requests that could not be processed at all - 401 unauthenticated, 422
    malformed or smuggled fields.
    """

    model_config = ConfigDict(extra="forbid")

    success: bool
    #: The action attempted, regardless of outcome.
    event_type: AttendanceEventType
    #: The user's attendance state *after* the attempt. On a rejection this is
    #: the unchanged current state, which usually explains the rejection.
    status: AttendanceState
    #: Present only on success - a refusal writes no row.
    attendance_event_id: uuid.UUID | None = None
    #: Server-generated (PostgreSQL ``now()``), never the device clock.
    event_timestamp: datetime | None = None
    #: ``None`` when the attempt was refused on state grounds before any
    #: evidence was examined.
    presence: PresenceSummary | None = None
    reason: str | None = None

    @classmethod
    def from_outcome(cls, outcome: AttendanceOutcome) -> AttendanceActionResponse:
        """Build the wire response from a service outcome."""
        presence = None
        if outcome.presence is not None:
            decision = outcome.presence
            presence = PresenceSummary(
                verified=decision.verified,
                gps=GPSVerificationResult(
                    verified=decision.gps.verified,
                    distance_meters=(
                        round(decision.gps.distance_meters, 2)
                        if decision.gps.distance_meters is not None
                        else None
                    ),
                    accuracy_meters=decision.gps.accuracy_meters,
                ),
                qr=QRVerificationResult(verified=decision.qr.verified),
            )

        return cls(
            success=outcome.success,
            event_type=outcome.event_type,
            status=outcome.state,
            attendance_event_id=outcome.event_id,
            event_timestamp=outcome.event_timestamp,
            presence=presence,
            reason=outcome.reason.value if outcome.reason is not None else None,
        )


# ---------------------------------------------------------------------------
# Phase 5 - read responses
# ---------------------------------------------------------------------------
#
# These deliberately expose only what a client needs to render attendance:
# timestamps, event ids for traceability, and the derived status. They carry no
# `verification_metadata`, no GPS coordinates, no distance, no challenge id and
# no nonce. That evidence is retained on the event row for audit, but a history
# screen has no use for it and every field exposed is a field that can leak.


class AttendanceSessionResponse(BaseModel):
    """One check-in/check-out pair.

    Either side may be ``null``: an open session has no ``check_out``, and a
    session that began the previous day (a night shift) has no ``check_in`` on
    the day it closes.
    """

    model_config = ConfigDict(extra="forbid")

    check_in: datetime | None = None
    check_out: datetime | None = None
    check_in_event_id: uuid.UUID | None = None
    check_out_event_id: uuid.UUID | None = None

    @classmethod
    def from_session(cls, session: AttendanceSession) -> AttendanceSessionResponse:
        return cls(
            check_in=session.check_in,
            check_out=session.check_out,
            check_in_event_id=session.check_in_event_id,
            check_out_event_id=session.check_out_event_id,
        )


class AttendanceDayResponse(BaseModel):
    """One user's attendance for one UTC calendar day.

    ``NO_RECORD`` means no attendance event was recorded - **not** that the
    person was absent from work. Karya cannot distinguish leave, travel, or a
    failure to reach the QR display.
    """

    model_config = ConfigDict(extra="forbid")

    date: date_type
    status: DayStatus
    sessions: list[AttendanceSessionResponse] = Field(default_factory=list)
    #: Convenience for the common single-session day; the full detail is in
    #: `sessions`, which is authoritative when there is more than one.
    first_check_in: datetime | None = None
    last_check_out: datetime | None = None

    @classmethod
    def from_day(cls, day: AttendanceDay) -> AttendanceDayResponse:
        return cls(
            date=day.date,
            status=day.status,
            sessions=[
                AttendanceSessionResponse.from_session(s) for s in day.sessions
            ],
            first_check_in=day.first_check_in,
            last_check_out=day.last_check_out,
        )


class AttendanceTodayResponse(BaseModel):
    """The caller's (or a named user's) attendance for a single day."""

    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    #: Derived live from the events, never stored.
    state: AttendanceState
    day: AttendanceDayResponse

    @classmethod
    def build(cls, *, user_id: uuid.UUID, day: AttendanceDay) -> AttendanceTodayResponse:
        state = (
            AttendanceState.CHECKED_IN
            if day.status is DayStatus.CHECKED_IN
            else AttendanceState.NOT_CHECKED_IN
        )
        return cls(
            user_id=user_id, state=state, day=AttendanceDayResponse.from_day(day)
        )


class PaginationResponse(BaseModel):
    """Page metadata. ``total`` counts **days** in the range, not events."""

    model_config = ConfigDict(extra="forbid")

    page: int
    page_size: int
    total: int
    total_pages: int


class AttendanceHistoryResponse(BaseModel):
    """A page of daily attendance, newest day first.

    Every date in the requested range appears, including days with no events, so
    a calendar can distinguish "nothing recorded" from "outside the range".
    """

    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    from_date: date_type
    to_date: date_type
    items: list[AttendanceDayResponse]
    pagination: PaginationResponse

    @classmethod
    def build(
        cls,
        *,
        user_id: uuid.UUID,
        from_date: date_type,
        to_date: date_type,
        page: AttendanceHistoryPage,
    ) -> AttendanceHistoryResponse:
        total_pages = -(-page.total // page.page_size) if page.page_size else 0
        return cls(
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
            items=[AttendanceDayResponse.from_day(d) for d in page.days],
            pagination=PaginationResponse(
                page=page.page,
                page_size=page.page_size,
                total=page.total,
                total_pages=total_pages,
            ),
        )


class TeamAttendanceMember(BaseModel):
    """One colleague on the tenant dashboard.

    Identity is limited to what a manager needs to recognise the person. Email is
    deliberately omitted - it is contact data, not attendance data.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    name: str
    employee_code: str
    status: DayStatus
    check_in: datetime | None = None
    check_out: datetime | None = None
    sessions: list[AttendanceSessionResponse] = Field(default_factory=list)

    @classmethod
    def from_member(cls, member: TeamMemberDay) -> TeamAttendanceMember:
        return cls(
            user_id=member.user_id,
            name=member.name,
            employee_code=member.employee_code,
            status=member.day.status,
            check_in=member.day.first_check_in,
            check_out=member.day.last_check_out,
            sessions=[
                AttendanceSessionResponse.from_session(s) for s in member.day.sessions
            ],
        )


class TeamAttendanceSummary(BaseModel):
    """Headcount by status. The three buckets always sum to ``total_staff``."""

    model_config = ConfigDict(extra="forbid")

    total_staff: int
    no_record: int
    checked_in: int
    completed: int


class TeamAttendanceResponse(BaseModel):
    """Today's attendance across the caller's own tenant."""

    model_config = ConfigDict(extra="forbid")

    date: date_type
    summary: TeamAttendanceSummary
    employees: list[TeamAttendanceMember]

    @classmethod
    def from_team(cls, team: TeamAttendance) -> TeamAttendanceResponse:
        return cls(
            date=team.date,
            summary=TeamAttendanceSummary(
                total_staff=team.total_staff,
                no_record=team.count(DayStatus.NO_RECORD),
                checked_in=team.count(DayStatus.CHECKED_IN),
                completed=team.count(DayStatus.COMPLETED),
            ),
            employees=[TeamAttendanceMember.from_member(m) for m in team.members],
        )
