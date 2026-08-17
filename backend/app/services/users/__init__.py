"""User lifecycle and account management.

* :mod:`errors`  - domain errors, mapped to status codes in one place by the API
* :mod:`service` - creation, listing, profile, role, lifecycle, password

Tenant scoping is a required argument on every function, never inferred from a
request. Nothing here deletes: identities move between ACTIVE and INACTIVE so
attendance history and audit trails stay intact.
"""

from app.services.users.errors import (
    EmailAlreadyExistsError,
    EmployeeCodeAlreadyExistsError,
    InvalidCurrentPasswordError,
    LastAdminError,
    PasswordTooSimilarError,
    PasswordUnchangedError,
    SelfDeactivationError,
    SelfRoleChangeError,
    UserManagementError,
    UserNotFoundError,
)
from app.services.users.service import (
    ASSIGNABLE_ROLES,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    change_own_password,
    change_user_role,
    create_user,
    get_user,
    list_user_audit,
    list_users,
    set_user_status,
    update_user_profile,
)

__all__ = [
    # errors
    "EmailAlreadyExistsError",
    "EmployeeCodeAlreadyExistsError",
    "InvalidCurrentPasswordError",
    "LastAdminError",
    "PasswordTooSimilarError",
    "PasswordUnchangedError",
    "SelfDeactivationError",
    "SelfRoleChangeError",
    "UserManagementError",
    "UserNotFoundError",
    # service
    "ASSIGNABLE_ROLES",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "change_own_password",
    "change_user_role",
    "create_user",
    "get_user",
    "list_user_audit",
    "list_users",
    "set_user_status",
    "update_user_profile",
]
