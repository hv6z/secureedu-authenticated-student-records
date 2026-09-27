"""Xác thực khối audit và checkpoint nằm ngoài SQLite."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .serialization import canonical_json_bytes


AUDIT_KEY_SIZE = 32
AUDIT_HKDF_SALT = b"secure-student-record/hkdf-salt/v1"
AUDIT_HKDF_INFO = b"secure-student-record/audit-authentication-key/v1"
BLOCK_MAC_DOMAIN = b"secure-student-record/audit-block-mac/v1"
ANCHOR_MAC_DOMAIN = b"secure-student-record/audit-anchor-mac/v1"
ANCHOR_SCHEMA_VERSION = 1


class AuditAnchorError(RuntimeError):
    """Checkpoint audit bị thiếu, sai cấu trúc hoặc không khớp cơ sở dữ liệu."""


def derive_audit_key(master_key: bytes) -> bytes:
    """Dẫn xuất khóa audit tách miền khỏi khóa AES và khóa tra cứu."""

    if not isinstance(master_key, bytes):
        raise TypeError("master_key phải là bytes.")
    if not master_key:
        raise ValueError("master_key không được rỗng.")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=AUDIT_KEY_SIZE,
        salt=AUDIT_HKDF_SALT,
        info=AUDIT_HKDF_INFO,
    ).derive(master_key)


def calculate_block_mac(
    audit_key: bytes, *, block_index: int, block_hash: str
) -> str:
    """Tạo HMAC cho digest của một khối tại đúng vị trí trong chuỗi."""

    if not isinstance(audit_key, bytes) or not audit_key:
        raise ValueError("audit_key phải là bytes không rỗng.")
    payload = canonical_json_bytes(
        {"block_hash": block_hash, "block_index": block_index}
    )
    return hmac.new(
        audit_key,
        BLOCK_MAC_DOMAIN + b"\x00" + payload,
        hashlib.sha256,
    ).hexdigest()


def _anchor_payload(
    *, block_index: int, block_hash: str, block_mac: str
) -> dict[str, Any]:
    return {
        "schema_version": ANCHOR_SCHEMA_VERSION,
        "block_index": block_index,
        "block_hash": block_hash,
        "block_mac": block_mac,
    }


def _calculate_anchor_mac(audit_key: bytes, payload: Mapping[str, Any]) -> str:
    return hmac.new(
        audit_key,
        ANCHOR_MAC_DOMAIN + b"\x00" + canonical_json_bytes(payload),
        hashlib.sha256,
    ).hexdigest()


def write_audit_anchor(
    path: str | Path,
    audit_key: bytes,
    *,
    block_index: int,
    block_hash: str,
    block_mac: str,
) -> None:
    """Ghi checkpoint bằng thay thế nguyên tử và ép dữ liệu xuống đĩa."""

    anchor_path = Path(path)
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _anchor_payload(
        block_index=block_index,
        block_hash=block_hash,
        block_mac=block_mac,
    )
    document = dict(payload)
    document["anchor_mac"] = _calculate_anchor_mac(audit_key, payload)
    encoded = (
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{anchor_path.name}.",
            suffix=".tmp",
            dir=anchor_path.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, anchor_path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def verify_audit_anchor(
    path: str | Path,
    audit_key: bytes,
    *,
    block_index: int,
    block_hash: str,
    block_mac: str,
) -> None:
    """Xác minh tính xác thực và độ mới của checkpoint so với head SQLite."""

    anchor_path = Path(path)
    if not anchor_path.is_file():
        raise AuditAnchorError(
            "Thiếu checkpoint audit nằm ngoài cơ sở dữ liệu."
        )
    try:
        value = json.loads(anchor_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditAnchorError("Không thể đọc checkpoint audit hợp lệ.") from exc
    if not isinstance(value, dict):
        raise AuditAnchorError("Checkpoint audit không phải đối tượng JSON.")

    payload = {
        "schema_version": value.get("schema_version"),
        "block_index": value.get("block_index"),
        "block_hash": value.get("block_hash"),
        "block_mac": value.get("block_mac"),
    }
    supplied_mac = value.get("anchor_mac")
    if not isinstance(supplied_mac, str) or not hmac.compare_digest(
        supplied_mac, _calculate_anchor_mac(audit_key, payload)
    ):
        raise AuditAnchorError("HMAC của checkpoint audit không hợp lệ.")
    expected = _anchor_payload(
        block_index=block_index,
        block_hash=block_hash,
        block_mac=block_mac,
    )
    if payload != expected:
        raise AuditAnchorError(
            "Checkpoint audit không khớp head hiện tại; có thể đã rollback hoặc cắt chuỗi."
        )

