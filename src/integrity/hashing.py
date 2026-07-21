"""Giá trị băm xác định cho gói hồ sơ đã mã hóa."""

from __future__ import annotations

import base64
import hashlib

from src.encryption import EncryptedEnvelope

from .serialization import canonical_json_bytes, make_aad
from .lookup import calculate_lookup_token, derive_lookup_key


ENVELOPE_HASH_DOMAIN_V1 = b"secure-student-record/encrypted-envelope-hash/v1"
ENVELOPE_HASH_DOMAIN = b"secure-student-record/encrypted-envelope-hash/v2"


def calculate_envelope_hash(
    record_id: int | str,
    version: int,
    operation: str,
    envelope: EncryptedEnvelope,
    actor_id: str = "system",
    actor_role: str = "system",
) -> str:
    """Băm ngữ cảnh và toàn bộ trường của gói mã hóa bằng SHA-256."""

    if not isinstance(envelope, EncryptedEnvelope):
        raise TypeError("envelope phải là EncryptedEnvelope.")

    # Dùng chung phép kiểm tra ngữ cảnh với AAD để tránh hai quy
    # trình chấp nhận các giá trị khác nhau.
    make_aad(
        record_id,
        version,
        operation,
        envelope.schema_version,
        actor_id,
        actor_role,
    )
    payload = {
        "envelope": {
            "algorithm": envelope.algorithm,
            "ciphertext": base64.b64encode(envelope.ciphertext).decode("ascii"),
            "key_id": envelope.key_id,
            "nonce": base64.b64encode(envelope.nonce).decode("ascii"),
            "schema_version": envelope.schema_version,
        },
        "operation": operation.strip(),
        "record_id": record_id,
        "version": version,
    }
    if envelope.schema_version >= 2:
        payload["actor_id"] = actor_id.strip()
        payload["actor_role"] = actor_role.strip().casefold()
        domain = ENVELOPE_HASH_DOMAIN
    else:
        domain = ENVELOPE_HASH_DOMAIN_V1
    digest_input = domain + b"\x00" + canonical_json_bytes(payload)
    return hashlib.sha256(digest_input).hexdigest()


__all__ = [
    "ENVELOPE_HASH_DOMAIN",
    "calculate_envelope_hash",
    "calculate_lookup_token",
    "derive_lookup_key",
]
