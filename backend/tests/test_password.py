"""Argon2id password hashing (spec checks 1-4)."""

from __future__ import annotations

from app.services.auth.password import (
    hash_password,
    needs_rehash,
    verify_password,
)

PASSWORD = "correct-horse-battery-staple"


def test_password_hashing_works() -> None:
    hashed = hash_password(PASSWORD)

    assert isinstance(hashed, str)
    assert hashed
    # PHC string identifying Argon2id specifically, not argon2i/argon2d.
    assert hashed.startswith("$argon2id$")


def test_correct_password_verifies() -> None:
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_incorrect_password_fails() -> None:
    hashed = hash_password(PASSWORD)

    assert verify_password("wrong-password", hashed) is False
    assert verify_password(PASSWORD.upper(), hashed) is False
    assert verify_password("", hashed) is False


def test_password_hash_is_not_plaintext() -> None:
    hashed = hash_password(PASSWORD)

    assert PASSWORD not in hashed
    # A hash must not be reversible to, or contain, the password in any casing.
    assert PASSWORD.lower() not in hashed.lower()


def test_hashes_are_salted_and_therefore_unique() -> None:
    """The same password hashed twice must not produce the same digest."""
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)

    assert first != second
    # Both still verify - the salt is embedded in the hash.
    assert verify_password(PASSWORD, first)
    assert verify_password(PASSWORD, second)


def test_verify_rejects_malformed_or_missing_hash() -> None:
    """A user with no password set must fail closed, not raise."""
    assert verify_password(PASSWORD, "") is False
    assert verify_password(PASSWORD, "not-a-hash") is False
    assert verify_password(PASSWORD, "$argon2id$garbage") is False


def test_current_parameters_do_not_need_rehash() -> None:
    assert needs_rehash(hash_password(PASSWORD)) is False
