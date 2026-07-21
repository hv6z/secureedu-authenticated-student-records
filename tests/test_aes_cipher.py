from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from cryptography.exceptions import InvalidTag

from src.encryption import (
    AES_GCM_ALGORITHM,
    AES_GCM_NONCE_SIZE,
    AES_GCM_SCHEMA_VERSION,
    AesGcmCipher,
    EncryptedEnvelope,
)
from src.integrity import make_aad


KEY = bytes(range(32))


def test_encrypt_decrypt_unicode_and_authenticated_context() -> None:
    cipher = AesGcmCipher(KEY, key_id="research-key-v1")
    plaintext = "Hồ sơ của Nguyễn Hải An".encode("utf-8")
    aad = make_aad("record-001", 1, "CREATE")

    envelope = cipher.encrypt(plaintext, aad=aad)

    assert envelope.schema_version == AES_GCM_SCHEMA_VERSION == 2
    assert envelope.algorithm == AES_GCM_ALGORITHM
    assert envelope.key_id == "research-key-v1"
    assert len(envelope.nonce) == AES_GCM_NONCE_SIZE
    assert len(envelope.ciphertext) == len(plaintext) + 16
    assert cipher.decrypt(envelope, aad=aad) == plaintext


def test_each_encryption_uses_a_fresh_nonce() -> None:
    cipher = AesGcmCipher(KEY)
    aad = make_aad("record-001", 1, "CREATE")

    first = cipher.encrypt(b"same", aad=aad)
    second = cipher.encrypt(b"same", aad=aad)

    assert first.nonce != second.nonce
    assert first.ciphertext != second.ciphertext


@pytest.mark.parametrize("changed_field", ["ciphertext", "nonce"])
def test_changed_envelope_fails_authentication(changed_field: str) -> None:
    cipher = AesGcmCipher(KEY)
    aad = make_aad("record-001", 1, "CREATE")
    envelope = cipher.encrypt(b"protected", aad=aad)
    original = getattr(envelope, changed_field)
    tampered = bytes([original[0] ^ 1]) + original[1:]
    changed = replace(envelope, **{changed_field: tampered})

    with pytest.raises(InvalidTag):
        cipher.decrypt(changed, aad=aad)


def test_wrong_aad_fails_authentication() -> None:
    cipher = AesGcmCipher(KEY)
    envelope = cipher.encrypt(
        b"protected", aad=make_aad("record-001", 1, "CREATE")
    )

    with pytest.raises(InvalidTag):
        cipher.decrypt(envelope, aad=make_aad("record-001", 2, "UPDATE"))


def test_cipher_rejects_wrong_key_size_and_key_id_mismatch() -> None:
    with pytest.raises(ValueError, match="32 byte"):
        AesGcmCipher(b"short")

    first_cipher = AesGcmCipher(KEY, "key-a")
    envelope = first_cipher.encrypt(b"protected", aad=b"context")
    second_cipher = AesGcmCipher(KEY, "key-b")
    with pytest.raises(ValueError, match="không thuộc khóa"):
        second_cipher.decrypt(envelope, aad=b"context")


def test_cipher_can_decrypt_legacy_schema_v1_envelope() -> None:
    cipher = AesGcmCipher(KEY)
    aad = make_aad("record-legacy", 1, "CREATE", schema_version=1)
    current = cipher.encrypt(b"legacy-compatible", aad=aad)
    legacy = replace(current, schema_version=1)

    assert cipher.decrypt(legacy, aad=aad) == b"legacy-compatible"


def test_envelope_is_immutable_and_validates_nonce() -> None:
    envelope = EncryptedEnvelope(1, AES_GCM_ALGORITHM, "key-v1", b"n" * 12, b"c" * 16)
    with pytest.raises(FrozenInstanceError):
        envelope.nonce = b"x" * 12  # type: ignore[misc]

    with pytest.raises(ValueError, match="12 byte"):
        EncryptedEnvelope(1, AES_GCM_ALGORITHM, "key-v1", b"short", b"c" * 16)
