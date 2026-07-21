"""Xác minh độc lập ba lớp: khối, gói mã hóa và quan hệ lưu trữ."""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.blockchain.block import AuditBlock, genesis_block
from src.blockchain.chain import list_blocks
from src.database.connection import connect_database
from src.database.repository import (
    StoredRecord,
    StoredVersion,
    get_record,
    list_records,
    list_versions,
)
from src.encryption.aes_cipher import AesGcmCipher, EncryptedEnvelope
from src.encryption.serialization import make_aad
from src.integrity import calculate_envelope_hash, calculate_lookup_token


@dataclass(frozen=True, slots=True)
class VerificationReport:
    valid: bool
    messages: tuple[str, ...]
    checked_blocks: int
    checked_versions: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "messages": list(self.messages),
            "checked_blocks": self.checked_blocks,
            "checked_versions": self.checked_versions,
        }


def _envelope(version: StoredVersion) -> EncryptedEnvelope:
    return EncryptedEnvelope(
        schema_version=version.schema_version,
        algorithm=version.algorithm,
        key_id=version.key_id,
        nonce=version.nonce,
        ciphertext=version.ciphertext,
    )


def _same_text(left: str, right: str) -> bool:
    """So sánh an toàn cả khi dữ liệu SQLite bị thay bằng Unicode bất thường."""

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _verify_chain(blocks: list[AuditBlock], messages: list[str]) -> None:
    if not blocks:
        messages.append("Chuỗi kiểm toán không có khối khởi nguyên.")
        return

    expected_genesis = genesis_block()
    if blocks[0] != expected_genesis:
        messages.append("Khối khởi nguyên không còn đúng giá trị cố định.")

    seen_hashes: set[str] = set()
    for position, block in enumerate(blocks):
        if block.block_index != position:
            messages.append(
                f"Thiếu hoặc đổi thứ tự khối tại vị trí {position}; "
                f"chỉ số đọc được là {block.block_index}."
            )
        if not _same_text(block.block_hash, block.expected_hash()):
            messages.append(f"Giá trị băm của khối {block.block_index} không hợp lệ.")
        if block.block_hash in seen_hashes:
            messages.append(f"Giá trị băm khối {block.block_index} bị lặp.")
        seen_hashes.add(block.block_hash)

        if position > 0 and not _same_text(
            block.previous_hash, blocks[position - 1].block_hash
        ):
            messages.append(
                f"Liên kết tới khối trước tại khối {block.block_index} không hợp lệ."
            )


def _verify_record_shape(
    record: StoredRecord,
    versions: list[StoredVersion],
    messages: list[str],
) -> None:
    if not versions:
        messages.append(f"Hồ sơ {record.record_id} không có phiên bản mã hóa.")
        return

    for expected, version in enumerate(versions, start=1):
        if version.version != expected:
            messages.append(
                f"Hồ sơ {record.record_id} thiếu hoặc đổi thứ tự phiên bản "
                f"{expected}."
            )
        if expected == 1 and version.operation != "CREATE":
            messages.append(
                f"Phiên bản đầu của hồ sơ {record.record_id} không phải CREATE."
            )
        if expected > 1 and version.operation == "CREATE":
            messages.append(
                f"Hồ sơ {record.record_id} có thao tác CREATE lặp ở phiên bản "
                f"{version.version}."
            )
        if version.operation == "DELETE" and expected != len(versions):
            messages.append(
                f"Hồ sơ {record.record_id} còn phiên bản sau thao tác DELETE."
            )

    if record.current_version != versions[-1].version:
        messages.append(
            f"Con trỏ phiên bản hiện tại của hồ sơ {record.record_id} không khớp."
        )
    expected_status = "deleted" if versions[-1].operation == "DELETE" else "active"
    if record.status != expected_status:
        messages.append(f"Trạng thái hồ sơ {record.record_id} không khớp lịch sử.")


def verify_database(
    database_path: str | Path,
    cipher: AesGcmCipher,
    *,
    record_id: str | None = None,
    lookup_key: bytes | None = None,
) -> VerificationReport:
    """Xác minh toàn hệ thống hoặc mọi phiên bản của một hồ sơ."""

    connection = connect_database(database_path)
    messages: list[str] = []
    checked_versions = 0
    try:
        blocks = list_blocks(connection)
        _verify_chain(blocks, messages)

        if record_id is None:
            records = list_records(connection)
        else:
            selected = get_record(connection, record_id)
            records = [] if selected is None else [selected]
            if selected is None:
                messages.append(f"Không tìm thấy hồ sơ {record_id}.")

        relevant_record_ids = {record.record_id for record in records}
        block_by_version: dict[tuple[str, int], AuditBlock] = {}
        for block in blocks[1:]:
            key = (block.record_id, block.version)
            if key in block_by_version:
                messages.append(
                    f"Có nhiều khối cho hồ sơ {block.record_id}, phiên bản "
                    f"{block.version}."
                )
            block_by_version[key] = block

        version_keys: set[tuple[str, int]] = set()
        for record in records:
            versions = list_versions(connection, record.record_id)
            _verify_record_shape(record, versions, messages)
            for version in versions:
                checked_versions += 1
                key = (version.record_id, version.version)
                version_keys.add(key)

                block = block_by_version.get(key)
                if block is None:
                    messages.append(
                        f"Thiếu khối cho hồ sơ {version.record_id}, phiên bản "
                        f"{version.version}."
                    )
                elif (
                    block.operation != version.operation
                    or block.timestamp != version.created_at
                    or block.actor_id != version.actor_id
                    or block.actor_role != version.actor_role
                    or not _same_text(
                        block.envelope_hash, version.envelope_hash
                    )
                ):
                    messages.append(
                        f"Khối và phiên bản {version.version} của hồ sơ "
                        f"{version.record_id} không khớp."
                    )

                try:
                    envelope = _envelope(version)
                    expected_envelope_hash = calculate_envelope_hash(
                        version.record_id,
                        version.version,
                        version.operation,
                        envelope,
                        version.actor_id,
                        version.actor_role,
                    )
                    if not _same_text(
                        version.envelope_hash, expected_envelope_hash
                    ):
                        messages.append(
                            f"Giá trị băm gói mã hóa của hồ sơ "
                            f"{version.record_id}, phiên bản {version.version} "
                            "không hợp lệ."
                        )
                    plaintext = cipher.decrypt(
                        envelope,
                        aad=make_aad(
                            version.record_id,
                            version.version,
                            version.operation,
                            schema_version=version.schema_version,
                            actor_id=version.actor_id,
                            actor_role=version.actor_role,
                        ),
                    )
                    value = json.loads(plaintext.decode("utf-8"))
                    if not isinstance(value, dict):
                        raise ValueError("Nội dung không phải đối tượng JSON.")
                    if (
                        lookup_key is not None
                        and version.version == record.current_version
                    ):
                        expected_token = calculate_lookup_token(
                            value["student_code"], lookup_key
                        )
                        if not hmac.compare_digest(
                            record.lookup_token, expected_token
                        ):
                            messages.append(
                                f"Mã tra cứu của hồ sơ {record.record_id} "
                                "không khớp nội dung mã hóa."
                            )
                except Exception as exc:  # Mọi lỗi cấu trúc/giải mã là kết quả xác minh.
                    messages.append(
                        f"Gói mã hóa không hợp lệ, không xác thực hoặc giải mã "
                        f"được hồ sơ "
                        f"{version.record_id}, phiên bản {version.version}: "
                        f"{type(exc).__name__}."
                    )

        for block in blocks[1:]:
            if record_id is not None and block.record_id not in relevant_record_ids:
                continue
            if (block.record_id, block.version) not in version_keys:
                messages.append(
                    f"Khối {block.block_index} không có phiên bản hồ sơ tương ứng."
                )

        if record_id is None:
            for version in list_versions(connection):
                key = (version.record_id, version.version)
                if key not in version_keys:
                    messages.append(
                        f"Phiên bản {version.version} của hồ sơ "
                        f"{version.record_id} không có bản ghi đầu mục tương ứng."
                    )

        return VerificationReport(
            valid=not messages,
            messages=tuple(messages),
            checked_blocks=len(blocks),
            checked_versions=checked_versions,
        )
    finally:
        connection.close()
