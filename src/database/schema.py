"""Lược đồ dữ liệu chỉ lưu hồ sơ ở dạng mã hóa."""

from __future__ import annotations

from pathlib import Path

from src.blockchain.block import genesis_block

from .connection import connect_database, immediate_transaction


SCHEMA = """
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
    block_hash TEXT NOT NULL UNIQUE CHECK (length(block_hash) = 64)
);

CREATE INDEX IF NOT EXISTS idx_record_versions_record
    ON record_versions(record_id, version);
CREATE INDEX IF NOT EXISTS idx_audit_blocks_record
    ON audit_blocks(record_id, version);
CREATE INDEX IF NOT EXISTS idx_users_role
    ON users(role, is_active);
"""


def _column_names(connection, table: str) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _migrate_audit_actor_columns(connection) -> None:
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


def initialize_database(database_path: str | Path) -> None:
    """Tạo ba bảng và khối khởi nguyên bất biến nếu cơ sở dữ liệu còn trống."""

    path = Path(database_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    connection = connect_database(path)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        with immediate_transaction(connection):
            connection.executescript(SCHEMA)
            _migrate_audit_actor_columns(connection)
            block = genesis_block()
            connection.execute(
                """
                INSERT OR IGNORE INTO audit_blocks (
                    block_index, timestamp, previous_hash, record_id,
                    version, operation, envelope_hash, block_schema_version,
                    actor_id, actor_role, block_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                block.as_database_tuple(),
            )
            connection.execute("PRAGMA user_version = 3")
    finally:
        connection.close()
