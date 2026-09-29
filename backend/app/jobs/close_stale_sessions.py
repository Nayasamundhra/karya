"""Scheduled sweep: auto-close CHECK_INs left open past the shift cutoff.

The common case never needs this - `app.services.attendance.service.record_attendance`
closes a stale session in-band the moment the same user next checks in or
out. This script exists only for the tail case: someone who never comes
back at all, whose row nothing else would ever touch, but whose team
dashboard should still stop showing them as checked in without waiting for
that.

Run it on whatever schedule the deployment platform already offers for
periodic jobs - a Render Cron Job, Windows Task Scheduler locally, cron on a
plain VM. Deliberately not an in-process scheduler: that would be a new
dependency (APScheduler or similar) for something the platform already
does, the same "no dependency was added in Phase 7" reasoning `CLAUDE.md`
documents for logging, rate limiting and the rest. Safe to run repeatedly
and from multiple instances at once - each candidate is only ever acted on
under that user's row lock, the same one `record_attendance` takes, and a
user who turns out not to be stale by the time their turn comes (already
closed by someone else, or they checked out in the last few seconds) is
skipped rather than acted on with stale information.

    python -m app.jobs.close_stale_sessions
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.models.attendance_event import AttendanceEvent, AttendanceEventType
from app.services.attendance.service import close_stale_session_for_user

logger = logging.getLogger(__name__)


def _open_sessions(session) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """``(tenant_id, user_id)`` pairs whose latest event is a CHECK_IN.

    ``DISTINCT ON (user_id)`` (PostgreSQL-specific, expressed here via
    ``Select.distinct(...)``) reads each user's single most recent event in
    one query rather than one round trip per user across the whole
    database.

    Deliberately **not** filtered by age here: the real staleness cutoff
    (``attendance_locations.max_shift_hours``) is per tenant, not a single
    global value, so there is no one cutoff this query could filter by
    without risking under-inclusion. Every currently-open session is a
    candidate; `close_stale_session_for_user` does the real, per-location
    check under lock and simply no-ops on anyone who isn't actually stale
    yet - cheap enough at the scale this runs at.
    """
    rows = session.execute(
        select(
            AttendanceEvent.tenant_id,
            AttendanceEvent.user_id,
            AttendanceEvent.event_type,
        )
        .distinct(AttendanceEvent.user_id)
        .order_by(
            AttendanceEvent.user_id,
            AttendanceEvent.event_timestamp.desc(),
            AttendanceEvent.created_at.desc(),
        )
    ).all()

    return [
        (tenant_id, user_id)
        for tenant_id, user_id, event_type in rows
        if AttendanceEventType(event_type) is AttendanceEventType.CHECK_IN
    ]


def run() -> int:
    """Close every stale session found in one pass. Returns the count closed."""
    session_factory = get_sessionmaker()

    with session_factory() as scan_session:
        candidates = _open_sessions(scan_session)

    closed = 0
    for tenant_id, user_id in candidates:
        with session_factory() as session:
            try:
                if close_stale_session_for_user(
                    session, tenant_id=tenant_id, user_id=user_id
                ):
                    session.commit()
                    closed += 1
                else:
                    session.rollback()
            except Exception:
                session.rollback()
                logger.exception(
                    "close_stale_session_failed",
                    extra={
                        "event": "close_stale_session_failed",
                        "tenant_id": str(tenant_id),
                        "user_id": str(user_id),
                    },
                )

    logger.info(
        "close_stale_sessions_swept",
        extra={
            "event": "close_stale_sessions_swept",
            "candidates": len(candidates),
            "closed": closed,
        },
    )
    return closed


def main() -> None:
    configure_logging()
    run()


if __name__ == "__main__":
    main()
