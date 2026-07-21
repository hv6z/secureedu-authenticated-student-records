"""Tuần tự hóa, băm và tạo mã tra cứu."""

from .hashing import ENVELOPE_HASH_DOMAIN, calculate_envelope_hash
from .lookup import (
    LOOKUP_HKDF_INFO,
    LOOKUP_HKDF_SALT,
    LOOKUP_KEY_SIZE,
    LOOKUP_TOKEN_DOMAIN,
    calculate_lookup_token,
    derive_lookup_key,
)
from .serialization import canonical_json_bytes, make_aad

__all__ = [
    "ENVELOPE_HASH_DOMAIN",
    "LOOKUP_HKDF_INFO",
    "LOOKUP_HKDF_SALT",
    "LOOKUP_KEY_SIZE",
    "LOOKUP_TOKEN_DOMAIN",
    "calculate_envelope_hash",
    "calculate_lookup_token",
    "canonical_json_bytes",
    "derive_lookup_key",
    "make_aad",
]
