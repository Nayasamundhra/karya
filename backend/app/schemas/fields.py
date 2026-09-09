"""Reusable field types shared across request schemas.

These exist so the email and password rules are defined **once**. Before Phase 6
the password bounds lived only in ``LoginRequest``; repeating them in the user
schemas would have let login and user-creation drift apart, which is exactly the
kind of divergence that produces an account nobody can log into.
"""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import BeforeValidator, EmailStr, Field, SecretStr

#: Password bounds. Length is the only requirement, deliberately: NIST SP 800-63B
#: advises against composition rules (an upper case letter, a digit, a symbol),
#: which push users towards predictable substitutions without adding real entropy.
#: The upper bound exists so a caller cannot force expensive Argon2 hashing with a
#: megabyte-long "password".
PASSWORD_MIN_LENGTH: Final[int] = 8
PASSWORD_MAX_LENGTH: Final[int] = 128

#: Matches `users.employee_code VARCHAR(100)` / `users.name VARCHAR(255)`.
EMPLOYEE_CODE_MAX_LENGTH: Final[int] = 100
NAME_MAX_LENGTH: Final[int] = 255
#: Matches `tenants.slug VARCHAR(100)` / `tenants.name VARCHAR(255)`.
SLUG_MAX_LENGTH: Final[int] = 100
TENANT_NAME_MAX_LENGTH: Final[int] = 255
#: Matches `attendance_locations.description VARCHAR(500)` - a free-text
#: address/description, not a name, so it gets more room than `NAME_MAX_LENGTH`.
LOCATION_DESCRIPTION_MAX_LENGTH: Final[int] = 500


def trim_or_none(value: object) -> object:
    """`trim`, plus: an empty (post-trim) string becomes ``None``.

    For an *optional* free-text field, lets a client clear it by submitting
    ``""`` rather than needing to omit the key entirely.
    """
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def normalize_email(value: object) -> object:
    """Trim and lower-case an email before validation.

    ``users`` enforces ``UNIQUE(tenant_id, email)`` on the **stored** value, which
    is case-sensitive in PostgreSQL. Without normalising, ``Rahul@acme.com`` and
    ``rahul@acme.com`` would be two separate accounts in one tenant, and whichever
    casing a person typed at login would decide whether they got in.

    Normalising every email on the way in makes that constraint effectively
    case-insensitive without a functional index or a `citext` migration: if every
    write is lower-case, uniqueness of the stored value *is* uniqueness of the
    address. Applied to login as well as to user management, so the two agree.

    Only the whole address is lower-cased. The local part of an email is
    technically case-sensitive per RFC 5321, but no mail provider in practice
    treats it that way, and treating it as significant here would recreate the
    duplicate-account problem.
    """
    if isinstance(value, str):
        return value.strip().lower()
    return value


def trim(value: object) -> object:
    """Strip surrounding whitespace from a free-text field."""
    if isinstance(value, str):
        return value.strip()
    return value


#: An email address, normalised to lower-case and trimmed.
NormalizedEmail = Annotated[EmailStr, BeforeValidator(normalize_email)]

#: A plaintext password. ``SecretStr`` so it cannot surface in a validation error,
#: a log line or a ``repr()``.
PlainPassword = Annotated[
    SecretStr, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
]

#: A person's display name.
PersonName = Annotated[
    str, BeforeValidator(trim), Field(min_length=1, max_length=NAME_MAX_LENGTH)
]

#: A tenant-assigned employee code.
EmployeeCode = Annotated[
    str,
    BeforeValidator(trim),
    Field(min_length=1, max_length=EMPLOYEE_CODE_MAX_LENGTH),
]
