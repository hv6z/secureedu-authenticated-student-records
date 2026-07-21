"""Đọc và nối khối trong cùng giao dịch SQLite của nghiệp vụ."""

from __future__ import annotations

import sqlite3

from .block import AuditBlock, block_from_row, genesis_block, new_block


def list_blocks(
    connection: sqlite3.Connection, limit: int | None = None
) -> list[AuditBlock]:
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit phải là số nguyên không âm hoặc None.")
        rows = connection.execute(
            "SELECT * FROM audit_blocks ORDER BY block_index LIMIT ?", (limit,)
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM audit_blocks ORDER BY block_index"
        ).fetchall()
    return [block_from_row(row) for row in rows]


def latest_block(connection: sqlite3.Connection) -> AuditBlock:
    row = connection.execute(
        "SELECT * FROM audit_blocks ORDER BY block_index DESC LIMIT 1"
    ).fetchone()
    if row is None:
        # Trường hợp này chỉ hỗ trợ phục hồi cơ sở dữ liệu vừa tạo nhưng chưa khởi tạo.
        block = genesis_block()
        connection.execute(
            """
            INSERT INTO audit_blocks (
                block_index, timestamp, previous_hash, record_id,
                version, operation, envelope_hash, block_schema_version,
                actor_id, actor_role, block_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            block.as_database_tuple(),
        )
        return block
    return block_from_row(row)


def append_block(
    connection: sqlite3.Connection,
    *,
    timestamp: str,
    record_id: str,
    version: int,
    operation: str,
    envelope_hash: str,
    actor_id: str = "system",
    actor_role: str = "system",
) -> AuditBlock:
    """Nối khối mới; hàm gọi phải đang giữ giao dịch BEGIN IMMEDIATE."""

    block = new_block(
        latest_block(connection),
        timestamp=timestamp,
        record_id=record_id,
        version=version,
        operation=operation,
        envelope_hash=envelope_hash,
        actor_id=actor_id,
        actor_role=actor_role,
    )
    connection.execute(
        """
        INSERT INTO audit_blocks (
            block_index, timestamp, previous_hash, record_id,
            version, operation, envelope_hash, block_schema_version,
            actor_id, actor_role, block_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        block.as_database_tuple(),
    )
    return block
