"""Cấu trúc và phép băm khối kiểm toán."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Mapping


BLOCK_HASH_DOMAIN_V1 = b"secure-student-record/audit-block/v1\x00"
from src.integrity.audit import calculate_block_mac


BLOCK_HASH_DOMAIN_V2 = b"secure-student-record/audit-block/v2\x00"
BLOCK_HASH_DOMAIN = b"secure-student-record/audit-block/v3\x00"
CURRENT_BLOCK_SCHEMA_VERSION = 3
ZERO_HASH = "0" * 64
GENESIS_TIMESTAMP = "1970-01-01T00:00:00.000000Z"


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def calculate_block_hash(
    *,
    block_index: int,
    timestamp: str,
    previous_hash: str,
    record_id: str,
    version: int,
    operation: str,
    envelope_hash: str,
    block_schema_version: int = CURRENT_BLOCK_SCHEMA_VERSION,
    actor_id: str = "system",
    actor_role: str = "system",
) -> str:
    """Băm JSON chuẩn, có tiền tố miền để tránh dùng nhầm ngữ cảnh."""

    payload = {
        "block_index": block_index,
        "envelope_hash": envelope_hash,
        "operation": operation,
        "previous_hash": previous_hash,
        "record_id": record_id,
        "timestamp": timestamp,
        "version": version,
    }
    if block_schema_version >= 2:
        payload["block_schema_version"] = block_schema_version
        payload["actor_id"] = actor_id
        payload["actor_role"] = actor_role
        domain = (
            BLOCK_HASH_DOMAIN
            if block_schema_version >= 3
            else BLOCK_HASH_DOMAIN_V2
        )
    else:
        domain = BLOCK_HASH_DOMAIN_V1
    return hashlib.sha256(domain + _canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class AuditBlock:
    block_index: int
    timestamp: str
    previous_hash: str
    record_id: str
    version: int
    operation: str
    envelope_hash: str
    block_schema_version: int
    actor_id: str
    actor_role: str
    block_hash: str
    block_mac: str

    def expected_hash(self) -> str:
        return calculate_block_hash(
            block_index=self.block_index,
            timestamp=self.timestamp,
            previous_hash=self.previous_hash,
            record_id=self.record_id,
            version=self.version,
            operation=self.operation,
            envelope_hash=self.envelope_hash,
            block_schema_version=self.block_schema_version,
            actor_id=self.actor_id,
            actor_role=self.actor_role,
        )

    def expected_mac(self, audit_key: bytes) -> str:
        return calculate_block_mac(
            audit_key,
            block_index=self.block_index,
            block_hash=self.block_hash,
        )

    def has_valid_mac(self, audit_key: bytes) -> bool:
        return hmac.compare_digest(self.block_mac, self.expected_mac(audit_key))

    def as_database_tuple(self) -> tuple[Any, ...]:
        return (
            self.block_index,
            self.timestamp,
            self.previous_hash,
            self.record_id,
            self.version,
            self.operation,
            self.envelope_hash,
            self.block_schema_version,
            self.actor_id,
            self.actor_role,
            self.block_hash,
            self.block_mac,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_index": self.block_index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "record_id": self.record_id,
            "version": self.version,
            "operation": self.operation,
            "envelope_hash": self.envelope_hash,
            "block_schema_version": self.block_schema_version,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "block_hash": self.block_hash,
            "block_mac": self.block_mac,
        }


def genesis_block(
    audit_key: bytes,
    *,
    block_schema_version: int = CURRENT_BLOCK_SCHEMA_VERSION,
) -> AuditBlock:
    """Trả về khối khởi nguyên cố định, giống nhau ở mọi lần chạy."""

    block_hash = calculate_block_hash(
        block_index=0,
        timestamp=GENESIS_TIMESTAMP,
        previous_hash=ZERO_HASH,
        record_id="",
        version=0,
        operation="GENESIS",
        envelope_hash=ZERO_HASH,
        block_schema_version=block_schema_version,
    )
    block_mac = calculate_block_mac(
        audit_key, block_index=0, block_hash=block_hash
    )
    return AuditBlock(
        block_index=0,
        timestamp=GENESIS_TIMESTAMP,
        previous_hash=ZERO_HASH,
        record_id="",
        version=0,
        operation="GENESIS",
        envelope_hash=ZERO_HASH,
        block_schema_version=block_schema_version,
        actor_id="system",
        actor_role="system",
        block_hash=block_hash,
        block_mac=block_mac,
    )


def new_block(
    previous: AuditBlock,
    audit_key: bytes,
    *,
    timestamp: str,
    record_id: str,
    version: int,
    operation: str,
    envelope_hash: str,
    actor_id: str = "system",
    actor_role: str = "system",
) -> AuditBlock:
    block_index = previous.block_index + 1
    block_hash = calculate_block_hash(
        block_index=block_index,
        timestamp=timestamp,
        previous_hash=previous.block_hash,
        record_id=record_id,
        version=version,
        operation=operation,
        envelope_hash=envelope_hash,
        block_schema_version=CURRENT_BLOCK_SCHEMA_VERSION,
        actor_id=actor_id,
        actor_role=actor_role,
    )
    block_mac = calculate_block_mac(
        audit_key, block_index=block_index, block_hash=block_hash
    )
    return AuditBlock(
        block_index=block_index,
        timestamp=timestamp,
        previous_hash=previous.block_hash,
        record_id=record_id,
        version=version,
        operation=operation,
        envelope_hash=envelope_hash,
        block_schema_version=CURRENT_BLOCK_SCHEMA_VERSION,
        actor_id=actor_id,
        actor_role=actor_role,
        block_hash=block_hash,
        block_mac=block_mac,
    )


def block_from_row(row: Mapping[str, Any]) -> AuditBlock:
    return AuditBlock(
        block_index=int(row["block_index"]),
        timestamp=str(row["timestamp"]),
        previous_hash=str(row["previous_hash"]),
        record_id=str(row["record_id"]),
        version=int(row["version"]),
        operation=str(row["operation"]),
        envelope_hash=str(row["envelope_hash"]),
        block_schema_version=int(row["block_schema_version"]),
        actor_id=str(row["actor_id"]),
        actor_role=str(row["actor_role"]),
        block_hash=str(row["block_hash"]),
        block_mac=str(row["block_mac"]),
    )
