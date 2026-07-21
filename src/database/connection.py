"""Tạo kết nối và điều khiển giao dịch SQLite."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def connect_database(database_path: str | Path) -> sqlite3.Connection:
    """Mở một kết nối có kiểm tra khóa ngoại và trả hàng dưới dạng ánh xạ."""

    connection = sqlite3.connect(
        str(database_path),
        timeout=30.0,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


@contextmanager
def immediate_transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Khóa quyền ghi từ đầu để mọi thay đổi nghiệp vụ là nguyên tử."""

    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
