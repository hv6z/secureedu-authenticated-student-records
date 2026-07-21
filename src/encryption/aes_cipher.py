"""Mã hóa xác thực AES-256-GCM cho hồ sơ sinh viên."""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


AES_GCM_ALGORITHM = "AES-256-GCM"
AES_GCM_SCHEMA_VERSION = 2
SUPPORTED_AES_GCM_SCHEMA_VERSIONS = frozenset({1, AES_GCM_SCHEMA_VERSION})
AES_GCM_NONCE_SIZE = 12
AES_GCM_TAG_SIZE = 16


@dataclass(frozen=True, slots=True)
class EncryptedEnvelope:
    """Gói bản mã bất biến cùng siêu dữ liệu cần để giải mã.

    ``ciphertext`` lưu trực tiếp kết quả của ``AESGCM.encrypt`` nên 16
    byte thẻ xác thực đã nằm ở cuối bản mã.
    """

    schema_version: int
    algorithm: str
    key_id: str
    nonce: bytes
    ciphertext: bytes

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(
            self.schema_version, int
        ):
            raise TypeError("schema_version phải là số nguyên.")
        if self.schema_version < 1:
            raise ValueError("schema_version phải lớn hơn 0.")
        if not isinstance(self.algorithm, str):
            raise TypeError("algorithm phải là chuỗi.")
        if not self.algorithm.strip():
            raise ValueError("algorithm không được rỗng.")
        if not isinstance(self.key_id, str):
            raise TypeError("key_id phải là chuỗi.")
        if not self.key_id.strip():
            raise ValueError("key_id không được rỗng.")
        if not isinstance(self.nonce, bytes):
            raise TypeError("nonce phải là bytes.")
        if len(self.nonce) != AES_GCM_NONCE_SIZE:
            raise ValueError("nonce AES-GCM phải dài đúng 12 byte.")
        if not isinstance(self.ciphertext, bytes):
            raise TypeError("ciphertext phải là bytes.")
        if len(self.ciphertext) < AES_GCM_TAG_SIZE:
            raise ValueError("ciphertext phải chứa thẻ xác thực 16 byte.")


class AesGcmCipher:
    """Mã hóa và giải mã bằng AES-GCM với khóa 256 bit."""

    def __init__(self, key: bytes, key_id: str = "key-v1") -> None:
        if not isinstance(key, bytes):
            raise TypeError("Khóa AES phải là bytes.")
        if len(key) != 32:
            raise ValueError("Khóa AES-256 phải dài đúng 32 byte.")
        if not isinstance(key_id, str):
            raise TypeError("key_id phải là chuỗi.")
        key_id = key_id.strip()
        if not key_id:
            raise ValueError("key_id không được rỗng.")

        self._cipher = AESGCM(key)
        self._key_id = key_id

    @property
    def key_id(self) -> str:
        """Mã định danh khóa, không phải nội dung khóa."""

        return self._key_id

    def encrypt(self, plaintext: bytes, *, aad: bytes) -> EncryptedEnvelope:
        """Mã hóa ``plaintext`` và sinh nonce 12 byte mới."""

        _require_bytes(plaintext, "plaintext")
        _require_bytes(aad, "aad")
        nonce = os.urandom(AES_GCM_NONCE_SIZE)
        ciphertext = self._cipher.encrypt(nonce, plaintext, aad)
        return EncryptedEnvelope(
            schema_version=AES_GCM_SCHEMA_VERSION,
            algorithm=AES_GCM_ALGORITHM,
            key_id=self._key_id,
            nonce=nonce,
            ciphertext=ciphertext,
        )

    def decrypt(self, envelope: EncryptedEnvelope, *, aad: bytes) -> bytes:
        """Giải mã gói dữ liệu và kiểm tra thẻ xác thực."""

        if not isinstance(envelope, EncryptedEnvelope):
            raise TypeError("envelope phải là EncryptedEnvelope.")
        _require_bytes(aad, "aad")
        if envelope.schema_version not in SUPPORTED_AES_GCM_SCHEMA_VERSIONS:
            raise ValueError("Phiên bản gói mã hóa không được hỗ trợ.")
        if envelope.algorithm != AES_GCM_ALGORITHM:
            raise ValueError("Thuật toán trong gói mã hóa không được hỗ trợ.")
        if envelope.key_id != self._key_id:
            raise ValueError("Gói dữ liệu không thuộc khóa đang được sử dụng.")
        return self._cipher.decrypt(envelope.nonce, envelope.ciphertext, aad)


def _require_bytes(value: object, name: str) -> None:
    if not isinstance(value, bytes):
        raise TypeError(f"{name} phải là bytes.")
