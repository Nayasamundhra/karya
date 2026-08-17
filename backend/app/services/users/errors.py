"""Domain errors for user management.

Exceptions rather than result objects: these operations either succeed or hit one
specific, nameable rule, and raising keeps the happy path in ``service.py``
readable. The API layer maps each to a status code in one place, so no route
invents its own wording and no database error ever reaches a client.
"""

from __future__ import annotations


class UserManagementError(Exception):
    """Base class for every user-management failure."""


class UserNotFoundError(UserManagementError):
    """No such user **within the caller's tenant**.

    Raised identically for "does not exist" and "belongs to another tenant" - the
    API turns both into a plain 404, so the response cannot be used to discover
    whether an id is real somewhere else.
    """


class EmailAlreadyExistsError(UserManagementError):
    """That email is already taken inside this tenant.

    Raised from the database's ``UNIQUE(tenant_id, email)`` violation rather than
    from a prior SELECT, so two concurrent creations cannot both pass a check and
    then both insert.
    """


class EmployeeCodeAlreadyExistsError(UserManagementError):
    """That employee code is already taken inside this tenant."""


class LastAdminError(UserManagementError):
    """The operation would leave the tenant with no active TENANT_ADMIN.

    A tenant that loses its final administrator cannot manage its own users
    again without operator intervention, so this is refused rather than merely
    warned about.
    """


class SelfRoleChangeError(UserManagementError):
    """A user may not change their own role.

    Blocks privilege escalation at its most direct: without this, the very role
    permitted to edit roles could edit its own.
    """


class SelfDeactivationError(UserManagementError):
    """A user may not deactivate their own account.

    Refused outright rather than only when it would strand the tenant: an admin
    locking themselves out is never the intended outcome, and another admin can
    always do it for them.
    """


class InvalidCurrentPasswordError(UserManagementError):
    """The supplied current password does not match."""


class PasswordUnchangedError(UserManagementError):
    """The new password is the same as the current one."""


class PasswordTooSimilarError(UserManagementError):
    """The new password is derived from the account's own identifiers."""
