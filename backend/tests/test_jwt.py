"""JWT access tokens (spec checks 13-20)."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.services.auth.jwt import (
    ACCESS_TOKEN_TYPE,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
)

SECRET = "unit-test-secret-key-that-is-long-enough-32"


def make_settings(**overrides: object) -> Settings:
    """Settings built in isolation from the developer's .env file."""
    defaults: dict[str, object] = {
        "environment": "test",
        "jwt_secret_key": SECRET,
        "jwt_algorithm": "HS256",
        "access_token_expire_minutes": 15,
        "refresh_token_expire_days": 30,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[arg-type]


@pytest.fixture
def config() -> Settings:
    return make_settings()


def base64_bytes(segment: str) -> bytes:
    """Decode a base64url JWT segment, restoring the stripped padding."""
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def raw_claims(token: str, *, config: Settings) -> dict:
    """Decode without our wrapper, to inspect the payload directly."""
    return jwt.decode(
        token, config.jwt_secret, algorithms=[config.jwt_algorithm]
    )


# ---------------------------------------------------------------------------
# 13-17. Generation and payload
# ---------------------------------------------------------------------------


def test_access_token_is_generated(config: Settings) -> None:
    token = create_access_token(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="STAFF", config=config
    )

    assert isinstance(token, str)
    # header.payload.signature
    assert token.count(".") == 2


def test_token_contains_user_tenant_role_and_type(config: Settings) -> None:
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()

    token = create_access_token(
        user_id=user_id, tenant_id=tenant_id, role="MANAGER", config=config
    )
    payload = raw_claims(token, config=config)

    assert payload["sub"] == str(user_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["role"] == "MANAGER"
    assert payload["type"] == ACCESS_TOKEN_TYPE == "access"
    assert "iat" in payload
    assert "exp" in payload
    assert uuid.UUID(payload["jti"])  # unique token id, parseable


def test_decoded_claims_round_trip(config: Settings) -> None:
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()

    token = create_access_token(
        user_id=user_id, tenant_id=tenant_id, role="TENANT_ADMIN", config=config
    )
    claims = decode_access_token(token, config=config)

    assert claims.user_id == user_id
    assert claims.tenant_id == tenant_id
    assert claims.role == "TENANT_ADMIN"
    assert claims.issued_at.tzinfo is not None
    assert claims.expires_at.tzinfo is not None
    assert claims.expires_at > claims.issued_at


def test_each_token_has_a_unique_jti(config: Settings) -> None:
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    jtis = {
        decode_access_token(
            create_access_token(
                user_id=user_id, tenant_id=tenant_id, role="STAFF", config=config
            ),
            config=config,
        ).jti
        for _ in range(5)
    }

    assert len(jtis) == 5


def test_token_carries_no_sensitive_claims(config: Settings) -> None:
    """The payload must not leak credentials or configuration."""
    token = create_access_token(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="STAFF", config=config
    )
    payload = raw_claims(token, config=config)

    assert set(payload) == {"sub", "tenant_id", "role", "type", "iat", "exp", "jti"}
    for forbidden in ("password", "password_hash", "email", "secret"):
        assert forbidden not in payload
    assert SECRET not in token


def test_expected_lifetime_matches_configuration() -> None:
    config = make_settings(access_token_expire_minutes=15)
    claims = decode_access_token(
        create_access_token(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            role="STAFF",
            config=config,
        ),
        config=config,
    )

    lifetime = claims.expires_at - claims.issued_at
    assert lifetime == timedelta(minutes=15)
    assert config.access_token_expire_seconds == 900


# ---------------------------------------------------------------------------
# 18-20. Rejection paths
# ---------------------------------------------------------------------------


def test_expired_token_fails(config: Settings) -> None:
    past = datetime.now(UTC) - timedelta(hours=2)
    expired = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "role": "STAFF",
            "type": "access",
            "iat": past,
            "exp": past + timedelta(minutes=15),
            "jti": str(uuid.uuid4()),
        },
        config.jwt_secret,
        algorithm=config.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(expired, config=config)


def flip(character: str) -> str:
    """Return a different base64url character."""
    return "A" if character != "A" else "B"


def test_tampered_token_fails(config: Settings) -> None:
    token = create_access_token(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="STAFF", config=config
    )
    header, payload, signature = token.split(".")

    # 1. Re-sign the payload with a different key.
    forged = jwt.encode(
        raw_claims(token, config=config), "an-attackers-own-secret-key-32chars"
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged, config=config)

    # 2. Swap in another token's payload, keeping this token's signature - the
    #    classic cut-and-paste attack.
    other = create_access_token(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="SUPER_ADMIN", config=config
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(
            f"{header}.{other.split('.')[1]}.{signature}", config=config
        )

    # 3. Corrupt the signature.
    #
    #    The FIRST character is flipped, not the last. A 43-character base64url
    #    signature carries 258 bits but HMAC-SHA256 produces only 256, so the
    #    final character has two unused bits and roughly 7% of last-character
    #    flips decode to byte-identical signatures - leaving the token genuinely
    #    valid and this assertion failing at random. The first character always
    #    maps onto real bits.
    broken_sig = flip(signature[0]) + signature[1:]
    assert base64_bytes(broken_sig) != base64_bytes(signature)
    with pytest.raises(InvalidTokenError):
        decode_access_token(f"{header}.{payload}.{broken_sig}", config=config)


def test_last_signature_character_may_be_cosmetic(config: Settings) -> None:
    """Documents the base64 padding quirk that made the check above flaky.

    Not a defect: a flip that leaves the decoded bytes unchanged has not
    tampered with anything, so accepting the token is correct. Pinned here so
    the reason is discoverable rather than rediscovered.
    """
    token = create_access_token(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="STAFF", config=config
    )
    signature = token.split(".")[2]

    assert len(signature) == 43
    assert len(base64_bytes(signature)) == 32  # 43 chars carry 258 bits, not 256

    variant = signature[:-1] + flip(signature[-1])
    if base64_bytes(variant) == base64_bytes(signature):
        # Byte-identical, so still a valid token - verification must accept it.
        decode_access_token(f"{token.rsplit('.', 1)[0]}.{variant}", config=config)
    else:
        with pytest.raises(InvalidTokenError):
            decode_access_token(f"{token.rsplit('.', 1)[0]}.{variant}", config=config)


def test_role_escalation_by_editing_the_payload_fails(config: Settings) -> None:
    """Re-encoding with an elevated role without the secret must not verify."""
    token = create_access_token(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="STAFF", config=config
    )
    claims = raw_claims(token, config=config)
    claims["role"] = "SUPER_ADMIN"
    forged = jwt.encode(claims, "wrong-secret-key-wrong-secret-key-32")

    with pytest.raises(InvalidTokenError):
        decode_access_token(forged, config=config)


def test_wrong_token_type_fails(config: Settings) -> None:
    """A validly signed token that is not type=access must be rejected."""
    for token_type in ("refresh", "reset", "", None):
        token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "tenant_id": str(uuid.uuid4()),
                "role": "STAFF",
                "type": token_type,
                "iat": datetime.now(UTC),
                "exp": datetime.now(UTC) + timedelta(minutes=15),
                "jti": str(uuid.uuid4()),
            },
            config.jwt_secret,
            algorithm=config.jwt_algorithm,
        )
        with pytest.raises(InvalidTokenError):
            decode_access_token(token, config=config)


def test_token_missing_required_claims_fails(config: Settings) -> None:
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access"},  # no exp/iat/jti
        config.jwt_secret,
        algorithm=config.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, config=config)


def test_unsigned_token_is_rejected(config: Settings) -> None:
    """An `alg: none` token must never be accepted."""
    unsigned = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "role": "SUPER_ADMIN",
            "type": "access",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=15),
            "jti": str(uuid.uuid4()),
        },
        key="",
        algorithm="none",
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned, config=config)


def test_decoding_fails_closed_without_a_configured_secret() -> None:
    config = make_settings(jwt_secret_key=None)

    assert config.is_auth_configured is False
    with pytest.raises(InvalidTokenError):
        decode_access_token("anything", config=config)
