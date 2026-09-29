"""Static QR resolution: a printed code identifies a location, nothing else.

Karya originally rotated the QR every few seconds so a photograph of it was
worthless - see the removed dynamic-challenge machinery in git history. That
traded away the operational simplicity of "print one code and stick it on
the wall", which is what this module now provides instead: the QR encodes
`AttendanceLocation.qr_token`, an opaque value that never expires and is
never consumed. Scanning it only tells the client which location to submit
evidence against; it is GPS, not the QR, that actually gates a check-in/out
(see `app.services.presence.gps` and `service.py`).

Because the token is not a secret in the way the old nonce was - it is
printed publicly on purpose - "protection" here means *regeneration*, not
expiry: `app.services.tenant.service.regenerate_location_qr_token` mints a
fresh one and the old value simply stops resolving.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attendance_location import (
    LOCATION_STATUS_ACTIVE,
    AttendanceLocation,
)


def resolve_location_by_qr_token(
    session: Session, *, qr_token: uuid.UUID
) -> AttendanceLocation | None:
    """Return the ACTIVE location a QR token belongs to, or ``None``.

    Deliberately **not** scoped by tenant here - the caller (``service.py``)
    still needs to know whether the match is the caller's own tenant so it
    can report the internal ``QR_TENANT_MISMATCH`` reason before collapsing
    it to the client-safe ``QR_NOT_FOUND``, the same "missing or not yours"
    posture used everywhere else in Phase 3.
    """
    return session.scalar(
        select(AttendanceLocation).where(
            AttendanceLocation.qr_token == qr_token,
            AttendanceLocation.status == LOCATION_STATUS_ACTIVE,
        )
    )
