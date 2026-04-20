"""6자리 Crockford base32 short ID."""
from __future__ import annotations

import secrets

# Crockford base32 (I, L, O, U 제외) 소문자 버전.
_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def generate_short_id(length: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
