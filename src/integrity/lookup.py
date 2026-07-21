"""Mã tra cứu không làm lộ mã sinh viên trong cơ sở dữ liệu."""

from __future__ import annotations

import hashlib
import hmac

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.domain import normalize_student_code


LOOKUP_KEY_SIZE = 32
LOOKUP_HKDF_SALT = b"secure-student-record/hkdf-salt/v1"
LOOKUP_HKDF_INFO = b"secure-student-record/student-code-lookup-key/v1"
LOOKUP_TOKEN_DOMAIN = b"secure-student-record/student-code-lookup-token/v1"


def derive_lookup_key(master_key: bytes) -> bytes:
    """Dẫn xuất khóa HMAC riêng bằng HKDF-SHA256.

    Khóa dẫn xuất không được dùng để mã hóa. Giá trị ``info`` cố
    định tách miền sử dụng của nó khỏi các khóa khác dẫn xuất từ
    cùng khóa chủ.
    """

    if not isinstance(master_key, bytes):
        raise TypeError("master_key phải là bytes.")
    if not master_key:
        raise ValueError("master_key không được rỗng.")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=LOOKUP_KEY_SIZE,
        salt=LOOKUP_HKDF_SALT,
        info=LOOKUP_HKDF_INFO,
    ).derive(master_key)


def calculate_lookup_token(student_code: str, lookup_key: bytes) -> bytes:
    """Tạo HMAC-SHA256 xác định sau khi chuẩn hóa mã sinh viên."""

    if not isinstance(lookup_key, bytes):
        raise TypeError("lookup_key phải là bytes.")
    if not lookup_key:
        raise ValueError("lookup_key không được rỗng.")
    normalized_code = normalize_student_code(student_code).encode("utf-8")
    message = LOOKUP_TOKEN_DOMAIN + b"\x00" + normalized_code
    return hmac.new(lookup_key, message, hashlib.sha256).digest()
