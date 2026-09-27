"""Tuần tự hóa, băm, HMAC audit và tạo mã tra cứu."""

from .audit import (
    AUDIT_HKDF_INFO,
    AUDIT_HKDF_SALT,
    ANCHOR_MAC_DOMAIN,
    BLOCK_MAC_DOMAIN,
    AuditAnchorError,
    calculate_block_mac,
    derive_audit_key,
    verify_audit_anchor,
    write_audit_anchor,
)

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
    "AUDIT_HKDF_INFO",
    "AUDIT_HKDF_SALT",
    "ANCHOR_MAC_DOMAIN",
    "BLOCK_MAC_DOMAIN",
    "AuditAnchorError",
    "LOOKUP_HKDF_INFO",
    "LOOKUP_HKDF_SALT",
    "LOOKUP_KEY_SIZE",
    "LOOKUP_TOKEN_DOMAIN",
    "calculate_envelope_hash",
    "calculate_block_mac",
    "calculate_lookup_token",
    "canonical_json_bytes",
    "derive_lookup_key",
    "derive_audit_key",
    "make_aad",
    "verify_audit_anchor",
    "write_audit_anchor",
]
