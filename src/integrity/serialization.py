"""Biểu diễn byte xác định cho dữ liệu được xác thực."""

from __future__ import annotations

import json
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """Mã hóa ``value`` thành JSON chuẩn, không phụ thuộc thứ tự khóa.

    Cấu hình này là một phần của giao thức lưu trữ. Thay đổi bất kỳ
    tham số nào cũng sẽ làm thay đổi AAD và các giá trị băm.
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def make_aad(
    record_id: int | str,
    version: int,
    operation: str,
    schema_version: int = 2,
    actor_id: str = "system",
    actor_role: str = "system",
) -> bytes:
    """Tạo dữ liệu xác thực bổ sung gắn bản mã với ngữ cảnh.

    Dữ liệu này không cần giữ bí mật. Nó bảo đảm một bản mã không
    thể bị chuyển sang hồ sơ, phiên bản hoặc thao tác khác mà vẫn
    giải mã thành công.
    """

    if isinstance(record_id, bool) or not isinstance(record_id, (int, str)):
        raise TypeError("record_id phải là số nguyên hoặc chuỗi.")
    if isinstance(record_id, int) and record_id < 1:
        raise ValueError("record_id dạng số phải lớn hơn 0.")
    if isinstance(record_id, str) and not record_id.strip():
        raise ValueError("record_id không được rỗng.")
    if isinstance(version, bool) or not isinstance(version, int):
        raise TypeError("version phải là số nguyên.")
    if version < 1:
        raise ValueError("version phải lớn hơn 0.")
    if not isinstance(operation, str):
        raise TypeError("operation phải là chuỗi.")
    operation = operation.strip()
    if not operation:
        raise ValueError("operation không được rỗng.")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise TypeError("schema_version phải là số nguyên.")
    if schema_version < 1:
        raise ValueError("schema_version phải lớn hơn 0.")

    payload = {
        "operation": operation,
        "record_id": record_id,
        "schema_version": schema_version,
        "version": version,
    }
    if schema_version >= 2:
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ValueError("actor_id không được rỗng với schema_version >= 2.")
        if not isinstance(actor_role, str) or not actor_role.strip():
            raise ValueError("actor_role không được rỗng với schema_version >= 2.")
        payload["actor_id"] = actor_id.strip()
        payload["actor_role"] = actor_role.strip().casefold()

    return canonical_json_bytes(payload)
