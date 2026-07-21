"""Các thao tác dữ liệu nhỏ, luôn được gọi bên trong giao dịch dịch vụ."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class StoredRecord:
    record_id: str
    lookup_token: bytes
    current_version: int
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class StoredVersion:
    record_id: str
    version: int
    schema_version: int
    algorithm: str
    key_id: str
    nonce: bytes
    ciphertext: bytes
    envelope_hash: str
    operation: str
    actor_id: str
    actor_role: str
    created_at: str


def _record_from_row(row: sqlite3.Row | None) -> StoredRecord | None:
    if row is None:
        return None
    return StoredRecord(
        record_id=row["record_id"],
        lookup_token=bytes(row["lookup_token"]),
        current_version=int(row["current_version"]),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _version_from_row(row: sqlite3.Row | None) -> StoredVersion | None:
    if row is None:
        return None
    return StoredVersion(
        record_id=row["record_id"],
        version=int(row["version"]),
        schema_version=int(row["schema_version"]),
        algorithm=row["algorithm"],
        key_id=row["key_id"],
        nonce=bytes(row["nonce"]),
        ciphertext=bytes(row["ciphertext"]),
        envelope_hash=row["envelope_hash"],
        operation=row["operation"],
        actor_id=row["actor_id"],
        actor_role=row["actor_role"],
        created_at=row["created_at"],
    )


def get_record(connection: sqlite3.Connection, record_id: str) -> StoredRecord | None:
    row = connection.execute(
        "SELECT * FROM records WHERE record_id = ?", (record_id,)
    ).fetchone()
    return _record_from_row(row)


def get_record_by_token(
    connection: sqlite3.Connection, lookup_token: bytes
) -> StoredRecord | None:
    row = connection.execute(
        "SELECT * FROM records WHERE lookup_token = ?", (lookup_token,)
    ).fetchone()
    return _record_from_row(row)


def list_records(connection: sqlite3.Connection) -> list[StoredRecord]:
    rows = connection.execute(
        "SELECT * FROM records ORDER BY created_at, record_id"
    ).fetchall()
    return [_record_from_row(row) for row in rows]  # type: ignore[misc]


def get_version(
    connection: sqlite3.Connection, record_id: str, version: int
) -> StoredVersion | None:
    row = connection.execute(
        """
        SELECT * FROM record_versions
        WHERE record_id = ? AND version = ?
        """,
        (record_id, version),
    ).fetchone()
    return _version_from_row(row)


def list_versions(
    connection: sqlite3.Connection, record_id: str | None = None
) -> list[StoredVersion]:
    if record_id is None:
        rows = connection.execute(
            "SELECT * FROM record_versions ORDER BY record_id, version"
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT * FROM record_versions
            WHERE record_id = ? ORDER BY version
            """,
            (record_id,),
        ).fetchall()
    return [_version_from_row(row) for row in rows]  # type: ignore[misc]


def insert_record(
    connection: sqlite3.Connection,
    *,
    record_id: str,
    lookup_token: bytes,
    timestamp: str,
) -> None:
    connection.execute(
        """
        INSERT INTO records (
            record_id, lookup_token, current_version, status, created_at, updated_at
        ) VALUES (?, ?, 1, 'active', ?, ?)
        """,
        (record_id, lookup_token, timestamp, timestamp),
    )


def insert_version(
    connection: sqlite3.Connection,
    *,
    record_id: str,
    version: int,
    schema_version: int,
    algorithm: str,
    key_id: str,
    nonce: bytes,
    ciphertext: bytes,
    envelope_hash: str,
    operation: str,
    actor_id: str,
    actor_role: str,
    timestamp: str,
) -> None:
    connection.execute(
        """
        INSERT INTO record_versions (
            record_id, version, schema_version, algorithm, key_id, nonce, ciphertext,
            envelope_hash, operation, actor_id, actor_role, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record_id,
            version,
            schema_version,
            algorithm,
            key_id,
            nonce,
            ciphertext,
            envelope_hash,
            operation,
            actor_id,
            actor_role,
            timestamp,
        ),
    )


def update_record_head(
    connection: sqlite3.Connection,
    *,
    record_id: str,
    version: int,
    lookup_token: bytes,
    status: str,
    timestamp: str,
) -> None:
    connection.execute(
        """
        UPDATE records
        SET lookup_token = ?, current_version = ?, status = ?, updated_at = ?
        WHERE record_id = ?
        """,
        (lookup_token, version, status, timestamp, record_id),
    )
