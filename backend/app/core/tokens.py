"""Generic opaque-token hashing, shared by every "random secret, looked up by
hash" feature: refresh tokens, email verification links, display tokens.

Refresh tokens (`app.services.auth.refresh_tokens`) implement this same
SHA-256-of-a-CSPRNG-token pattern already; that module is left untouched
(working code, not touched without reason) and simply doesn't import this -
it predates it. Every *new* token kind added from here on reuses this instead
of re-deriving the same two functions a third and fourth time.

Why SHA-256 and not Argon2: these are 256 bits of CSPRNG output, not a
low-entropy human secret, so there is no dictionary to slow down - and a
deterministic digest is what makes an indexed equality lookup possible at
all. See `refresh_tokens.py`'s docstring for the full reasoning.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Final

#: Bytes of entropy per token. 32 bytes = 256 bits, url-safe encoded to
#: roughly 43 characters.
TOKEN_BYTES: Final[int] = 32


def generate_opaque_token(n_bytes: int = TOKEN_BYTES) -> str:
    """Return a new cryptographically secure, URL-safe opaque token."""
    return secrets.token_urlsafe(n_bytes)


def hash_opaque_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest used as a token's stored hash."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
