"""Dynamic QR challenge lifecycle: creation, validation, atomic consumption.

A QR challenge is a short-lived, single-use nonce bound to one tenant *and* one
attendance location. It is the second, independent presence signal: unlike GPS,
it requires the person to be physically in front of a display whose code rotates
every few seconds, so a photograph taken earlier is worthless.

The challenge is deliberately **opaque server-side state**, not a signed token.
A JWT-in-a-QR would be self-validating and therefore impossible to revoke or
mark used without a server-side record anyway - and the record is what provides
replay protection, so the token would add nothing but size.

No route handler touches this module's SQL; the presence service coordinates it.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.qr_challenge import QRChallenge, QRChallengeStatus
from app.services.presence.results import FailureReason, QRResult

#: Bytes of entropy per nonce. 32 bytes = 256 bits from the OS CSPRNG, url-safe
#: encoded to ~43 characters (well inside the column's VARCHAR(255)).
#:
#: `secrets` is used rather than `random`: the latter is a Mersenne Twister whose
#: entire future output can be predicted from a few observed values, and QR
#: nonces are displayed publicly. A timestamp or counter would be worse still.
NONCE_BYTES: Final[int] = 32


def generate_nonce() -> str:
    """Return a fresh cryptographically secure, URL-safe nonce."""
    return secrets.token_urlsafe(NONCE_BYTES)


def create_challenge(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    config: Settings | None = None,
) -> QRChallenge:
    """Create and persist an ACTIVE challenge for a tenant's location.

    ``expires_at`` is computed here from the server clock plus the configured
    TTL - the client never proposes an expiry. The row is flushed so it has an
    id, but the caller owns the commit.

    Previously issued challenges are intentionally **not** revoked. The office
    display fetches the next code slightly before the current one lapses, so the
    two overlap briefly; revoking on creation would break anyone who scanned in
    that window. Old challenges simply expire on their own.
    """
    config = config or settings
    issued_at = datetime.now(UTC)

    challenge = QRChallenge(
        tenant_id=tenant_id,
        location_id=location_id,
        nonce=generate_nonce(),
        expires_at=issued_at + timedelta(seconds=config.qr_challenge_ttl_seconds),
        status=QRChallengeStatus.ACTIVE.value,
    )
    session.add(challenge)
    session.flush()
    return challenge


def validate_challenge(
    session: Session,
    *,
    challenge_id: uuid.UUID,
    nonce: str,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    now: datetime | None = None,
) -> QRResult:
    """Check whether a challenge is currently redeemable, **without** consuming it.

    Separating validation from consumption is what lets the presence service
    reject a request with bad GPS *without* burning an otherwise-good QR code.

    Checks: existence, tenant ownership, location binding, status, expiry and
    nonce equality. Cross-tenant and cross-location hits are reported here as
    their precise internal reasons so the audit log can record a probe for what
    it is; :func:`app.services.presence.results.to_client_reason` collapses them
    before they reach a response.
    """
    now = now or datetime.now(UTC)

    # populate_existing: always read committed state rather than a possibly
    # stale instance from the identity map. This function doubles as the
    # diagnosis path after a lost consumption race, where a cached copy would
    # report the pre-race status.
    challenge = session.scalar(
        select(QRChallenge)
        .where(QRChallenge.id == challenge_id)
        .execution_options(populate_existing=True)
    )
    if challenge is None:
        return QRResult(verified=False, reason=FailureReason.QR_NOT_FOUND)

    if challenge.tenant_id != tenant_id:
        return QRResult(
            verified=False,
            challenge_id=challenge.id,
            reason=FailureReason.QR_TENANT_MISMATCH,
        )

    # Even with one location per tenant in V1, binding is enforced so a
    # challenge cannot be redeemed against a different site once multiple
    # locations exist.
    if challenge.location_id != location_id:
        return QRResult(
            verified=False,
            challenge_id=challenge.id,
            reason=FailureReason.QR_LOCATION_MISMATCH,
        )

    if challenge.status == QRChallengeStatus.USED or challenge.used_at is not None:
        return QRResult(
            verified=False,
            challenge_id=challenge.id,
            reason=FailureReason.QR_ALREADY_USED,
        )

    if challenge.status == QRChallengeStatus.REVOKED:
        return QRResult(
            verified=False,
            challenge_id=challenge.id,
            reason=FailureReason.QR_REVOKED,
        )

    if challenge.expires_at <= now:
        # Lazy expiration: mark it EXPIRED now that we have noticed, so the row
        # stops looking ACTIVE. This is bookkeeping only - the authoritative
        # gate is the timestamp comparison (here and in the consuming UPDATE),
        # never the status column, so no background sweeper is required.
        if challenge.status == QRChallengeStatus.ACTIVE:
            challenge.status = QRChallengeStatus.EXPIRED.value
        return QRResult(
            verified=False,
            challenge_id=challenge.id,
            reason=FailureReason.QR_EXPIRED,
        )

    if challenge.status != QRChallengeStatus.ACTIVE:
        # Defensive: an unrecognised status must never be treated as usable.
        return QRResult(
            verified=False,
            challenge_id=challenge.id,
            reason=FailureReason.QR_NOT_FOUND,
        )

    if not secrets.compare_digest(challenge.nonce, nonce):
        # Constant-time comparison: the nonce is a secret, so a byte-by-byte
        # early exit would leak its prefix through response timing.
        return QRResult(
            verified=False,
            challenge_id=challenge.id,
            reason=FailureReason.QR_NONCE_MISMATCH,
        )

    return QRResult(verified=True, challenge_id=challenge.id)


def consume_challenge(
    session: Session,
    *,
    challenge_id: uuid.UUID,
    nonce: str,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
) -> bool:
    """Atomically mark a challenge USED. Returns whether *this* call claimed it.

    Single-use enforcement lives entirely in this one statement:

        UPDATE qr_challenges SET status='USED', used_at=now()
        WHERE id=… AND tenant_id=… AND location_id=… AND nonce=…
          AND status='ACTIVE' AND used_at IS NULL AND expires_at > now()

    Every condition is re-checked *inside* the write, so the check and the claim
    cannot be separated by another transaction. Under PostgreSQL's default READ
    COMMITTED isolation, two concurrent statements targeting the same row
    serialise: the second blocks until the first commits, then re-evaluates its
    WHERE clause against the newly committed row, sees ``status='USED'`` and
    matches zero rows. Exactly one caller can ever get ``True``.

    A read-then-write (SELECT … then UPDATE) would leave a window where both
    transactions read ACTIVE and both proceeded, which is precisely the replay
    hole this must not have.

    ``expires_at > now()`` is evaluated by PostgreSQL so expiry is part of the
    same atomic claim rather than a separate, racy pre-check.
    """
    claimed_id = session.execute(
        update(QRChallenge)
        .where(
            QRChallenge.id == challenge_id,
            QRChallenge.tenant_id == tenant_id,
            QRChallenge.location_id == location_id,
            QRChallenge.nonce == nonce,
            QRChallenge.status == QRChallengeStatus.ACTIVE.value,
            QRChallenge.used_at.is_(None),
            QRChallenge.expires_at > func.now(),
        )
        .values(status=QRChallengeStatus.USED.value, used_at=func.now())
        .returning(QRChallenge.id)
        # The ORM must not try to reconcile its identity map from this
        # statement; callers re-read with populate_existing when they need
        # post-consume state.
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()

    return claimed_id is not None


def revoke_challenge(
    session: Session,
    *,
    challenge_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> bool:
    """Revoke an as-yet-unused challenge. Returns whether a row was revoked.

    Service-level only: no public endpoint exposes revocation in this phase, so
    there is no route to abuse. It exists for an operator flow ("that code was
    photographed, kill it") and for Phase 4 to call. Tenant-scoped, so one
    tenant can never revoke another's challenge. Already-used challenges are
    left alone - they are spent, not revocable.
    """
    revoked_id = session.execute(
        update(QRChallenge)
        .where(
            QRChallenge.id == challenge_id,
            QRChallenge.tenant_id == tenant_id,
            QRChallenge.status == QRChallengeStatus.ACTIVE.value,
            QRChallenge.used_at.is_(None),
        )
        .values(status=QRChallengeStatus.REVOKED.value)
        .returning(QRChallenge.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()

    return revoked_id is not None
