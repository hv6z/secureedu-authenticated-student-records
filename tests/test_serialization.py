from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace

import pytest

from src.encryption import AES_GCM_ALGORITHM, EncryptedEnvelope
from src.integrity import (
    ENVELOPE_HASH_DOMAIN,
    calculate_envelope_hash,
    calculate_lookup_token,
    canonical_json_bytes,
    derive_lookup_key,
    make_aad,
)


def test_canonical_json_is_utf8_sorted_and_compact() -> None:
    value = {"z": 2, "name": "Nguyễn An", "a": [3, 1]}

    result = canonical_json_bytes(value)

    assert result == '{"a":[3,1],"name":"Nguyễn An","z":2}'.encode("utf-8")
    assert canonical_json_bytes({"b": 1, "a": 2}) == canonical_json_bytes(
        {"a": 2, "b": 1}
    )


def test_canonical_json_rejects_non_finite_numbers() -> None:
    with pytest.raises(ValueError):
        canonical_json_bytes({"score": float("nan")})
    with pytest.raises(ValueError):
        canonical_json_bytes({"score": float("inf")})


def test_make_aad_binds_all_context_fields() -> None:
    expected = canonical_json_bytes(
        {
            "actor_id": "user-01",
            "actor_role": "registrar",
            "operation": "CREATE",
            "record_id": "record-01",
            "schema_version": 2,
            "version": 3,
        }
    )
    assert make_aad(
        "record-01", 3, "CREATE", actor_id="user-01", actor_role="registrar"
    ) == expected
    assert make_aad(
        "record-01", 3, "CREATE", actor_id="user-01", actor_role="registrar"
    ) != make_aad(
        "record-01", 4, "CREATE", actor_id="user-01", actor_role="registrar"
    )
    assert b"actor_id" not in make_aad(
        "record-01", 3, "CREATE", schema_version=1
    )


def test_envelope_hash_covers_context_and_all_envelope_metadata() -> None:
    envelope = EncryptedEnvelope(
        schema_version=2,
        algorithm=AES_GCM_ALGORITHM,
        key_id="key-v1",
        nonce=bytes(range(12)),
        ciphertext=b"encrypted bytes" + b"t" * 16,
    )
    expected_payload = {
        "envelope": {
            "algorithm": envelope.algorithm,
            "ciphertext": base64.b64encode(envelope.ciphertext).decode("ascii"),
            "key_id": envelope.key_id,
            "nonce": base64.b64encode(envelope.nonce).decode("ascii"),
            "schema_version": envelope.schema_version,
        },
        "operation": "CREATE",
        "record_id": "record-01",
        "version": 1,
        "actor_id": "user-01",
        "actor_role": "registrar",
    }
    expected = hashlib.sha256(
        ENVELOPE_HASH_DOMAIN + b"\x00" + canonical_json_bytes(expected_payload)
    ).hexdigest()

    result = calculate_envelope_hash(
        "record-01", 1, "CREATE", envelope, "user-01", "registrar"
    )

    assert result == expected
    assert len(result) == 64
    assert result != calculate_envelope_hash(
        "record-01",
        1,
        "CREATE",
        replace(envelope, key_id="key-v2"),
        "user-01",
        "registrar",
    )
    assert result != calculate_envelope_hash(
        "record-01", 2, "UPDATE", envelope, "user-01", "registrar"
    )
    assert result != calculate_envelope_hash(
        "record-01", 1, "CREATE", envelope, "user-02", "registrar"
    )


def test_lookup_key_and_token_are_deterministic_and_normalized() -> None:
    master_key = bytes(range(32))
    lookup_key = derive_lookup_key(master_key)

    assert len(lookup_key) == 32
    assert lookup_key != master_key
    assert lookup_key == derive_lookup_key(master_key)
    assert calculate_lookup_token(" sv  001 ", lookup_key) == calculate_lookup_token(
        "SV 001", lookup_key
    )
    assert len(calculate_lookup_token("SV001", lookup_key)) == hashlib.sha256().digest_size


def test_lookup_token_changes_with_code_or_key() -> None:
    first_key = derive_lookup_key(b"a" * 32)
    second_key = derive_lookup_key(b"b" * 32)

    assert calculate_lookup_token("SV001", first_key) != calculate_lookup_token(
        "SV002", first_key
    )
    assert calculate_lookup_token("SV001", first_key) != calculate_lookup_token(
        "SV001", second_key
    )
