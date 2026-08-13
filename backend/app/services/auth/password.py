"""Argon2id password hashing.

The only two operations the rest of the application needs are
:func:`hash_password` and :func:`verify_password`. Neither ever accepts, logs,
returns or raises a plaintext password: :func:`verify_password` returns a plain
boolean and swallows the library's exceptions so a failure cannot carry the
attempted password into a traceback.
"""

from __future__ import annotations

from functools import lru_cache

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

#: Argon2id parameters. These follow argon2-cffi's own recommended defaults
#: (roughly the OWASP "second choice" profile: 64 MiB, t=3, p=4), which target
#: a few hundred milliseconds on server hardware. Raising `memory_cost` is the
#: most effective way to harden this later; existing hashes stay verifiable
#: because the parameters are encoded in the hash string itself.
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536  # KiB, i.e. 64 MiB
ARGON2_PARALLELISM = 4
ARGON2_HASH_LENGTH = 32
ARGON2_SALT_LENGTH = 16


@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    """Return the process-wide hasher (constructing one is not free)."""
    return PasswordHasher(
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LENGTH,
        salt_len=ARGON2_SALT_LENGTH,
        type=Type.ID,  # Argon2id
    )


def hash_password(password: str) -> str:
    """Hash ``password`` with Argon2id.

    Returns a PHC-format string (``$argon2id$v=19$m=...``) that embeds the
    algorithm, parameters and a random per-password salt, so two identical
    passwords never produce the same hash.
    """
    return _hasher().hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return whether ``plain_password`` matches ``password_hash``.

    Returns ``False`` - rather than raising - for a wrong password *and* for a
    malformed or empty stored hash. The latter matters because
    ``users.password_hash`` is nullable: a user who has never had a password set
    must simply fail to authenticate.
    """
    if not password_hash:
        return False
    try:
        return _hasher().verify(password_hash, plain_password)
    except (VerificationError, InvalidHashError):
        # VerifyMismatchError (wrong password) subclasses VerificationError.
        # Deliberately no logging: the attempted password must not be recorded.
        return False


def needs_rehash(password_hash: str) -> bool:
    """Whether ``password_hash`` was made with weaker parameters than current.

    Lets a future login handler transparently upgrade stored hashes after the
    Argon2 parameters above are raised.
    """
    try:
        return _hasher().check_needs_rehash(password_hash)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache(maxsize=1)
def dummy_hash() -> str:
    """A throwaway hash used to equalise failed-login timing.

    When no user matches, the login path still performs one Argon2 verification
    against this value. Without it, "no such user" would return measurably
    faster than "wrong password", leaking account existence through timing even
    though both return the same generic 401.
    """
    return hash_password("karya-timing-equalisation-placeholder")
