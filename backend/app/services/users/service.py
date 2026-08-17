"""User lifecycle and account management.

Every function here is tenant-scoped by construction: ``tenant_id`` is a required
argument that callers must take from ``current_user.tenant_id``, and no query
omits it. There is no code path through which a request body could redirect an
operation at another tenant.

Two invariants get special care because both are concurrency-sensitive and both
are the kind of rule that a naive check-then-act would silently break:

* **A tenant never loses its last active TENANT_ADMIN.** Enforced by locking the
  tenant's admin rows before counting them, so two simultaneous demotions cannot
  both observe "there are two admins" and both proceed.
* **An email is unique within a tenant.** Enforced by the database constraint and
  the ``IntegrityError`` it raises - never by a preceding SELECT, which two
  concurrent creations would both pass.

Nothing is deleted. Karya is an attendance and audit system, so identities move
between ACTIVE and INACTIVE and their history stays intact.

Callers own the commit; each mutation writes its audit row inside the same
transaction as the change itself.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Final

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User, UserRole, UserStatus
from app.services.auth import refresh_tokens
from app.services.auth.password import hash_password, verify_password
from app.services.users.errors import (
    EmailAlreadyExistsError,
    EmployeeCodeAlreadyExistsError,
    InvalidCurrentPasswordError,
    LastAdminError,
    PasswordTooSimilarError,
    PasswordUnchangedError,
    SelfDeactivationError,
    SelfRoleChangeError,
    UserNotFoundError,
)

#: Audit actions written by this module.
ACTION_USER_CREATED: Final = "USER_CREATED"
ACTION_USER_UPDATED: Final = "USER_UPDATED"
ACTION_USER_ROLE_CHANGED: Final = "USER_ROLE_CHANGED"
ACTION_USER_ACTIVATED: Final = "USER_ACTIVATED"
ACTION_USER_DEACTIVATED: Final = "USER_DEACTIVATED"
ACTION_PASSWORD_CHANGED: Final = "PASSWORD_CHANGED"

#: Bounds on the user list. Unbounded listing of a large tenant is a denial of
#: service against our own database.
DEFAULT_PAGE_SIZE: Final[int] = 25
MAX_PAGE_SIZE: Final[int] = 100

#: Roles a tenant administrator may assign. ``SUPER_ADMIN`` is deliberately
#: absent: it is a platform-level role, and letting tenant administration mint it
#: would turn tenant admin into a route to platform access.
ASSIGNABLE_ROLES: Final[tuple[UserRole, ...]] = (
    UserRole.TENANT_ADMIN,
    UserRole.MANAGER,
    UserRole.STAFF,
)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _audit(
    session: Session,
    *,
    action: str,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    target_user_id: uuid.UUID,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append an audit row for an administrative mutation.

    Added to the same session as the change it describes, so the two commit
    together or not at all. Never receives a password, hash or token - callers
    pass only identifiers and before/after values.
    """
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=User.__name__,
            target_id=target_user_id,
            log_metadata={"target_user_id": str(target_user_id), **(metadata or {})},
        )
    )


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def get_user(
    session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> User:
    """Fetch a user inside the caller's tenant.

    Raises:
        UserNotFoundError: if absent *or* in another tenant - indistinguishable
            on purpose.
    """
    user = session.scalar(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    if user is None:
        raise UserNotFoundError
    return user


#: Characters that mean something to ``LIKE`` and must be escaped in a search
#: term. The backslash goes first, or it would escape the escapes.
_LIKE_METACHARACTERS: Final[tuple[str, ...]] = ("\\", "%", "_")


def _like_pattern(term: str) -> str:
    """Turn a user-supplied term into a literal ``LIKE`` containment pattern.

    The value is always a bound parameter, so this is not about SQL injection -
    it is about *matching*. Unescaped, a search for ``%`` becomes the pattern
    ``%%%`` and matches every row, and ``_`` silently becomes "any single
    character". Escaping makes the term mean what the person typed.
    """
    escaped = term.strip().lower()
    for character in _LIKE_METACHARACTERS:
        escaped = escaped.replace(character, f"\\{character}")
    return f"%{escaped}%"


def _list_query(
    *,
    tenant_id: uuid.UUID,
    search: str | None = None,
    role: UserRole | None = None,
    status: UserStatus | None = None,
) -> Select[tuple[User]]:
    """Build the filtered user query.

    Filtering happens in SQL, never by loading the tenant and sifting in Python.
    The search term is bound as a parameter and its ``LIKE`` metacharacters are
    escaped, so it matches literally instead of turning into a wildcard.
    """
    query = select(User).where(User.tenant_id == tenant_id)

    if search:
        pattern = _like_pattern(search)
        query = query.where(
            or_(
                func.lower(User.name).like(pattern, escape="\\"),
                func.lower(User.email).like(pattern, escape="\\"),
                func.lower(User.employee_code).like(pattern, escape="\\"),
            )
        )
    if role is not None:
        query = query.where(User.role == role.value)
    if status is not None:
        query = query.where(User.status == status.value)
    return query


def list_users(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    search: str | None = None,
    role: UserRole | None = None,
    status: UserStatus | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[Sequence[User], int]:
    """Return one page of tenant users plus the total match count.

    Ordered by name then employee code - deterministic even when two people share
    a name, which keeps pagination stable.
    """
    query = _list_query(
        tenant_id=tenant_id, search=search, role=role, status=status
    )
    total = session.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0
    rows = session.scalars(
        query.order_by(User.name, User.employee_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return rows, total


# ---------------------------------------------------------------------------
# The last-admin invariant
# ---------------------------------------------------------------------------


def _lock_admins_and_target(
    session: Session, *, tenant_id: uuid.UUID, target_id: uuid.UUID
) -> list[User]:
    """Lock the tenant's active admins **and** the target row, returning the admins.

    This is what makes the last-admin rule safe under concurrency. A plain
    ``SELECT COUNT(*)`` followed by an update lets two simultaneous requests both
    see two admins and both remove one, leaving zero.

    Both row sets are locked by a single statement ordered by ``id``, so every
    transaction acquires them in the same order and none can deadlock against
    another. Under READ COMMITTED the second transaction blocks here, then
    re-evaluates the predicate against committed state - so it sees the admin the
    first transaction just removed as no longer matching, and refuses.
    """
    rows = list(
        session.scalars(
            select(User)
            .where(
                User.tenant_id == tenant_id,
                or_(
                    User.id == target_id,
                    (User.role == UserRole.TENANT_ADMIN.value)
                    & (User.status == UserStatus.ACTIVE.value),
                ),
            )
            .order_by(User.id)
            .with_for_update()
        )
    )
    return [
        row
        for row in rows
        if row.role == UserRole.TENANT_ADMIN and row.status == UserStatus.ACTIVE
    ]


def _require_another_active_admin(
    active_admins: Sequence[User], *, target: User
) -> None:
    """Refuse if ``target`` is the only active admin left.

    Raises:
        LastAdminError: when removing this user's admin access would leave none.
    """
    if target.role != UserRole.TENANT_ADMIN or target.status != UserStatus.ACTIVE:
        # Not currently an active admin, so the invariant is unaffected.
        return
    if not any(admin.id != target.id for admin in active_admins):
        raise LastAdminError


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def create_user(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor: User,
    email: str,
    password: str,
    name: str,
    employee_code: str,
    role: UserRole = UserRole.STAFF,
) -> User:
    """Create a user in the actor's own tenant.

    ``tenant_id`` comes from the authenticated actor; there is no parameter a
    client could use to place the user elsewhere.

    Uniqueness is left to the database. A ``SELECT`` first would still let two
    concurrent requests with the same email both pass, so the
    ``UNIQUE(tenant_id, email)`` violation is caught and translated instead. The
    savepoint keeps that failure from poisoning the caller's transaction.

    Raises:
        EmailAlreadyExistsError | EmployeeCodeAlreadyExistsError: on conflict.
    """
    user = User(
        tenant_id=tenant_id,
        email=email,
        name=name,
        employee_code=employee_code,
        role=role.value,
        status=UserStatus.ACTIVE.value,
        password_hash=hash_password(password),
    )
    session.add(user)

    # A nested transaction (SAVEPOINT) so a constraint violation rolls back only
    # this insert. Without it the whole transaction would be aborted and the
    # caller could not return a clean 409.
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise _translate_conflict(exc) from exc

    _audit(
        session,
        action=ACTION_USER_CREATED,
        tenant_id=tenant_id,
        actor_user_id=actor.id,
        target_user_id=user.id,
        metadata={
            "email": email,
            "employee_code": employee_code,
            "role": role.value,
            # No password and no hash: the audit trail records that an account was
            # created, not the credential it was created with.
        },
    )
    return user


def _translate_conflict(exc: IntegrityError) -> Exception:
    """Map a unique-constraint violation to a domain error.

    Matches on the constraint name so the client never sees a database message,
    a table name or a SQL fragment.
    """
    detail = str(getattr(exc.orig, "diag", None) and exc.orig.diag.constraint_name or exc.orig)
    if "employee_code" in detail:
        return EmployeeCodeAlreadyExistsError()
    if "email" in detail:
        return EmailAlreadyExistsError()
    return exc


# ---------------------------------------------------------------------------
# Profile updates
# ---------------------------------------------------------------------------


def update_user_profile(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor: User,
    user_id: uuid.UUID,
    changes: dict[str, Any],
) -> User:
    """Apply an explicit, allowlisted set of profile changes.

    ``changes`` must already contain only fields the caller is permitted to set -
    the schema layer decides that. Nothing here reads attributes generically off a
    request body, so ``role``, ``status``, ``tenant_id``, ``password_hash`` and
    the timestamps cannot be reached however they are spelled.

    Only supplied keys are written, which is what makes this a PATCH: absent
    fields keep their current values.
    """
    user = get_user(session, tenant_id=tenant_id, user_id=user_id)

    applied: dict[str, Any] = {}
    for field, value in changes.items():
        if getattr(user, field) != value:
            applied[field] = {"from": getattr(user, field), "to": value}
            setattr(user, field, value)

    if not applied:
        # Nothing changed, so there is nothing worth auditing.
        return user

    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise _translate_conflict(exc) from exc

    _audit(
        session,
        action=ACTION_USER_UPDATED,
        tenant_id=tenant_id,
        actor_user_id=actor.id,
        target_user_id=user.id,
        metadata={"changes": applied},
    )
    return user


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------


def change_user_role(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor: User,
    user_id: uuid.UUID,
    new_role: UserRole,
) -> User:
    """Change a user's role, preserving the last-admin invariant.

    Raises:
        SelfRoleChangeError: if the actor is the target. Nobody edits their own
            role, which closes the most direct escalation path.
        LastAdminError: if this would demote the tenant's only active admin.
        UserNotFoundError: if the target is absent or in another tenant.
    """
    if actor.id == user_id:
        raise SelfRoleChangeError

    user = get_user(session, tenant_id=tenant_id, user_id=user_id)
    active_admins = _lock_admins_and_target(
        session, tenant_id=tenant_id, target_id=user.id
    )

    previous_role = user.role
    if previous_role == new_role.value:
        return user

    if new_role != UserRole.TENANT_ADMIN:
        _require_another_active_admin(active_admins, target=user)

    user.role = new_role.value
    session.flush()

    _audit(
        session,
        action=ACTION_USER_ROLE_CHANGED,
        tenant_id=tenant_id,
        actor_user_id=actor.id,
        target_user_id=user.id,
        metadata={"old_role": previous_role, "new_role": new_role.value},
    )
    return user


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def set_user_status(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor: User,
    user_id: uuid.UUID,
    status: UserStatus,
) -> User:
    """Activate or deactivate a user.

    Deactivation is a lifecycle change, never a delete: attendance events and
    audit rows are untouched, so history stays complete and the identity behind it
    stays resolvable. Authentication, refresh and attendance recording all consult
    ``users.status`` on every request, so the effect is immediate.

    Raises:
        SelfDeactivationError: an actor may not deactivate themselves.
        LastAdminError: if this would deactivate the only active admin.
        UserNotFoundError: if the target is absent or in another tenant.
    """
    if status == UserStatus.INACTIVE and actor.id == user_id:
        raise SelfDeactivationError

    user = get_user(session, tenant_id=tenant_id, user_id=user_id)
    active_admins = _lock_admins_and_target(
        session, tenant_id=tenant_id, target_id=user.id
    )

    if user.status == status.value:
        return user

    if status == UserStatus.INACTIVE:
        _require_another_active_admin(active_admins, target=user)
        # Deactivation ends the account's sessions; an unexpired refresh token
        # must not outlive the access it represents.
        refresh_tokens.revoke_all_for_user(session, user=user)

    user.status = status.value
    session.flush()

    _audit(
        session,
        action=(
            ACTION_USER_ACTIVATED
            if status == UserStatus.ACTIVE
            else ACTION_USER_DEACTIVATED
        ),
        tenant_id=tenant_id,
        actor_user_id=actor.id,
        target_user_id=user.id,
        metadata={"status": status.value},
    )
    return user


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------


def change_own_password(
    session: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
) -> int:
    """Change the authenticated user's own password.

    The target is always ``user`` - the caller resolved from the bearer token.
    There is no user id parameter, so an admin cannot set somebody else's password
    through this path and no request field can redirect it.

    Returns the number of refresh sessions revoked. Every existing session is
    ended: a password change usually means the old one is suspect, and leaving
    30-day refresh tokens alive would leave whoever knew it still logged in.

    Raises:
        InvalidCurrentPasswordError: current password does not match.
        PasswordUnchangedError: new password equals the current one.
        PasswordTooSimilarError: new password is the account's own email or code.
    """
    if not verify_password(current_password, user.password_hash or ""):
        # Checked first, and nothing about the *new* password is validated before
        # this passes - otherwise the endpoint would answer questions for someone
        # who has not proven they own the account.
        raise InvalidCurrentPasswordError

    if current_password == new_password:
        raise PasswordUnchangedError

    lowered = new_password.strip().lower()
    identifiers = {user.email.lower(), user.email.split("@")[0].lower(),
                   user.employee_code.lower()}
    if lowered in identifiers:
        raise PasswordTooSimilarError

    user.password_hash = hash_password(new_password)
    revoked = refresh_tokens.revoke_all_for_user(session, user=user)
    session.flush()

    _audit(
        session,
        action=ACTION_PASSWORD_CHANGED,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        target_user_id=user.id,
        # Neither password appears here, nor the resulting hash - only the fact of
        # the change and how many sessions it ended.
        metadata={"sessions_revoked": revoked, "self_service": True},
    )
    return revoked


# ---------------------------------------------------------------------------
# Audit history
# ---------------------------------------------------------------------------


def list_user_audit(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[Sequence[AuditLog], int]:
    """Lifecycle audit rows for one user, newest first.

    Scoped to ``tenant_id`` *and* ``target_type='User'`` *and* this user, so it
    cannot become a window onto the tenant's whole audit log - attendance and QR
    rows are not exposed here.
    """
    query = select(AuditLog).where(
        AuditLog.tenant_id == tenant_id,
        AuditLog.target_type == User.__name__,
        AuditLog.target_id == user_id,
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return rows, total
