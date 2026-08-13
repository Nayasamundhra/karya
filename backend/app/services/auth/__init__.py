"""Authentication services: password hashing, JWT, refresh tokens, login flow.

The submodules are kept separate on purpose:

* :mod:`password`        - Argon2id hashing, nothing else
* :mod:`jwt`             - access-token minting/verification, nothing else
* :mod:`refresh_tokens`  - the refresh-token store, no user validation
* :mod:`service`         - the flows that combine them (login/refresh/logout)
"""

from app.services.auth.jwt import (
    ACCESS_TOKEN_TYPE,
    AccessTokenClaims,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
)
from app.services.auth.password import hash_password, needs_rehash, verify_password
from app.services.auth.service import (
    AuthenticationError,
    TokenPair,
    authenticate_user,
    login,
    logout,
    refresh,
)

__all__ = [
    # password
    "hash_password",
    "verify_password",
    "needs_rehash",
    # jwt
    "ACCESS_TOKEN_TYPE",
    "AccessTokenClaims",
    "InvalidTokenError",
    "create_access_token",
    "decode_access_token",
    # flows
    "AuthenticationError",
    "TokenPair",
    "authenticate_user",
    "login",
    "logout",
    "refresh",
]
