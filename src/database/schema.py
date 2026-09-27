"""Lược đồ dữ liệu chỉ lưu hồ sơ ở dạng mã hóa."""

from __future__ import annotations

from pathlib import Path

from src.blockchain.block import block_from_row, genesis_block
from src.integrity.audit import calculate_block_mac

from .connection import connect_database, immediate_transaction


USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'registrar', 'auditor')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    locked_until TEXT,
    last_login_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_role
    ON users(role, is_active);
"""

SCHEMA = USERS_SCHEMA + """

CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY,
    lookup_token BLOB NOT NULL UNIQUE,
    current_version INTEGER NOT NULL CHECK (current_version >= 1),
    status TEXT NOT NULL CHECK (status IN ('active', 'deleted')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS record_versions (
    record_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    algorithm TEXT NOT NULL,
    key_id TEXT NOT NULL,
    nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    envelope_hash TEXT NOT NULL CHECK (length(envelope_hash) = 64),
    operation TEXT NOT NULL CHECK (operation IN ('CREATE', 'UPDATE', 'DELETE')),
    actor_id TEXT NOT NULL DEFAULT 'system',
    actor_role TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL,
    PRIMARY KEY (record_id, version),
    UNIQUE (key_id, nonce),
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS audit_blocks (
    block_index INTEGER PRIMARY KEY CHECK (block_index >= 0),
    timestamp TEXT NOT NULL,
    previous_hash TEXT NOT NULL CHECK (length(previous_hash) = 64),
    record_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 0),
    operation TEXT NOT NULL CHECK (operation IN ('GENESIS', 'CREATE', 'UPDATE', 'DELETE')),
    envelope_hash TEXT NOT NULL CHECK (length(envelope_hash) = 64),
    block_schema_version INTEGER NOT NULL DEFAULT 1 CHECK (block_schema_version >= 1),
    actor_id TEXT NOT NULL DEFAULT 'system',
    actor_role TEXT NOT NULL DEFAULT 'system',
    block_hash TEXT NOT NULL UNIQUE CHECK (length(block_hash) = 64),
    block_mac TEXT NOT NULL CHECK (length(block_mac) = 64)
);

CREATE INDEX IF NOT EXISTS idx_record_versions_record
    ON record_versions(record_id, version);
CREATE INDEX IF NOT EXISTS idx_audit_blocks_record
    ON audit_blocks(record_id, version);
"""


def _column_names(connection, table: str) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _migrate_audit_columns(connection) -> bool:
    """Bổ sung danh tính người thao tác mà không phá dữ liệu schema v1."""

    version_columns = _column_names(connection, "record_versions")
    if "actor_id" not in version_columns:
        connection.execute(
            "ALTER TABLE record_versions "
            "ADD COLUMN actor_id TEXT NOT NULL DEFAULT 'system'"
        )
    if "actor_role" not in version_columns:
        connection.execute(
            "ALTER TABLE record_versions "
            "ADD COLUMN actor_role TEXT NOT NULL DEFAULT 'system'"
        )

    block_columns = _column_names(connection, "audit_blocks")
    if "block_schema_version" not in block_columns:
        connection.execute(
            "ALTER TABLE audit_blocks "
            "ADD COLUMN block_schema_version INTEGER NOT NULL DEFAULT 1"
        )
    if "actor_id" not in block_columns:
        connection.execute(
            "ALTER TABLE audit_blocks "
            "ADD COLUMN actor_id TEXT NOT NULL DEFAULT 'system'"
        )
    if "actor_role" not in block_columns:
        connection.execute(
            "ALTER TABLE audit_blocks "
            "ADD COLUMN actor_role TEXT NOT NULL DEFAULT 'system'"
        )
    added_block_mac = "block_mac" not in block_columns
    if added_block_mac:
        connection.execute(
            "ALTER TABLE audit_blocks "
            "ADD COLUMN block_mac TEXT NOT NULL DEFAULT ''"
        )
    return added_block_mac


def _backfill_and_validate_block_macs(connection, audit_key: bytes) -> None:
    """Tin cậy trạng thái tại thời điểm nâng cấp rồi khóa nó bằng HMAC."""

    rows = connection.execute(
        "SELECT * FROM audit_blocks ORDER BY block_index"
    ).fetchall()
    previous = None
    for position, row in enumerate(rows):
        block = block_from_row(row)
        if block.block_index != position or block.block_hash != block.expected_hash():
            raise RuntimeError(
                "Không thể nâng cấp: chuỗi audit hiện có không nhất quán."
            )
        if previous is not None and block.previous_hash != previous.block_hash:
            raise RuntimeError(
                "Không thể nâng cấp: liên kết chuỗi audit hiện có không hợp lệ."
            )
        expected_mac = calculate_block_mac(
            audit_key,
            block_index=block.block_index,
            block_hash=block.block_hash,
        )
        if block.block_mac and block.block_mac != expected_mac:
            raise RuntimeError(
                "Không thể nâng cấp: HMAC audit hiện có không hợp lệ."
            )
        connection.execute(
            "UPDATE audit_blocks SET block_mac = ? WHERE block_index = ?",
            (expected_mac, block.block_index),
        )
        previous = block


def initialize_database(database_path: str | Path, audit_key: bytes) -> bool:
    """Tạo ba bảng và khối khởi nguyên bất biến nếu cơ sở dữ liệu còn trống."""

    path = Path(database_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    connection = connect_database(path)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        with immediate_transaction(connection):
            audit_table_existed = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'audit_blocks'"
            ).fetchone() is not None
            connection.executescript(SCHEMA)
            added_block_mac = _migrate_audit_columns(connection)
            block = genesis_block(audit_key)
            connection.execute(
                """
                INSERT OR IGNORE INTO audit_blocks (
                    block_index, timestamp, previous_hash, record_id,
                    version, operation, envelope_hash, block_schema_version,
                    actor_id, actor_role, block_hash, block_mac
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                block.as_database_tuple(),
            )
            _backfill_and_validate_block_macs(connection, audit_key)
            connection.execute("PRAGMA user_version = 4")
            return (not audit_table_existed) or added_block_mac
    finally:
        connection.close()


def initialize_authentication_database(database_path: str | Path) -> None:
    """Tạo riêng bảng tài khoản khi dịch vụ xác thực được kiểm thử độc lập."""

    path = Path(database_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect_database(path)
    try:
        with immediate_transaction(connection):
            connection.executescript(USERS_SCHEMA)
    finally:
        connection.close()
