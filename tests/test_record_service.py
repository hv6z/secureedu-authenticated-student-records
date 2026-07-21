"""Kiểm thử dịch vụ hồ sơ và tính nguyên tử của mỗi thao tác."""

from __future__ import annotations

import sqlite3

import pytest

from src.services.record_service import (
    DuplicateStudentError,
    RecordDeletedError,
    RecordService,
    VersionConflictError,
)


def _student(code: str = "SV001", name: str = "Nguyễn Văn An") -> dict:
    return {
        "student_code": code,
        "full_name": name,
        "date_of_birth": "2004-05-20",
        "program": "An toàn thông tin",
        "courses": [
            {"course_code": "MMH101", "course_name": "Mật mã học", "score": 8.5}
        ],
        "gpa": 8.5,
    }


def test_create_read_update_find_and_logical_delete(tmp_path) -> None:
    service = RecordService(tmp_path / "records.db", b"a" * 32)
    service.initialize()

    created = service.create_student(_student(" sv001 "))
    assert created["student_code"] == "SV001"
    assert created["_version"] == 1
    assert created["_status"] == "active"
    assert service.find_by_student_code("sv001") == created

    changed = _student("SV001", "Nguyễn Văn Bình")
    changed["gpa"] = 9.2
    updated = service.update_student(
        created["_record_id"], changed, expected_version=1
    )
    assert updated["_version"] == 2
    assert service.get_student(created["_record_id"])["full_name"] == "Nguyễn Văn Bình"

    deleted = service.delete_student(created["_record_id"], expected_version=2)
    assert deleted["_version"] == 3
    assert deleted["_status"] == "deleted"
    assert service.get_student(created["_record_id"]) is None
    assert service.find_by_student_code("SV001") is None
    assert service.get_student(created["_record_id"], include_deleted=True) == deleted
    assert service.list_students() == []
    assert service.list_students(include_deleted=True) == [deleted]
    with pytest.raises(RecordDeletedError):
        service.update_student(created["_record_id"], changed)


def test_duplicate_code_and_optimistic_version(tmp_path) -> None:
    service = RecordService(tmp_path / "records.db", b"b" * 32)
    service.initialize()
    created = service.create_student(_student("SV001"))
    with pytest.raises(DuplicateStudentError):
        service.create_student(_student("sv001", "Người Khác"))
    with pytest.raises(VersionConflictError):
        service.update_student(created["_record_id"], _student(), expected_version=7)


def test_database_contains_no_plain_student_code_or_name(tmp_path) -> None:
    path = tmp_path / "records.db"
    service = RecordService(path, b"c" * 32)
    service.initialize()
    service.create_student(_student("SV-MAT-001", "Tên Không Được Lộ"))

    raw = path.read_bytes()
    assert b"SV-MAT-001" not in raw
    assert "Tên Không Được Lộ".encode("utf-8") not in raw

    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT lookup_token, current_version, status FROM records"
        ).fetchone()
        assert isinstance(row[0], bytes)
        assert len(row[0]) == 32
        assert row[1:] == (1, "active")
    finally:
        connection.close()


def test_nonce_is_unique_and_versions_have_composite_primary_key(tmp_path) -> None:
    path = tmp_path / "records.db"
    service = RecordService(path, b"d" * 32)
    service.initialize()
    first = service.create_student(_student("SV001"))
    service.update_student(first["_record_id"], _student("SV001"))
    service.create_student(_student("SV002"))

    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT key_id, nonce FROM record_versions"
        ).fetchall()
        assert len(rows) == len(set(rows))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO record_versions (
                    record_id, version, schema_version, algorithm, key_id,
                    nonce, ciphertext, envelope_hash, operation, created_at
                ) SELECT record_id, 99, schema_version, algorithm, key_id,
                    nonce, ciphertext, envelope_hash, 'UPDATE', created_at
                  FROM record_versions LIMIT 1
                """
            )
    finally:
        connection.close()


def test_create_rolls_back_when_block_append_fails(tmp_path, monkeypatch) -> None:
    path = tmp_path / "records.db"
    service = RecordService(path, b"e" * 32)
    service.initialize()

    def fail_append(*args, **kwargs):
        raise RuntimeError("lỗi mô phỏng")

    monkeypatch.setattr("src.services.record_service.append_block", fail_append)
    with pytest.raises(RuntimeError, match="lỗi mô phỏng"):
        service.create_student(_student())

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 0
        assert (
            connection.execute("SELECT count(*) FROM record_versions").fetchone()[0]
            == 0
        )
        assert connection.execute("SELECT count(*) FROM audit_blocks").fetchone()[0] == 1
    finally:
        connection.close()
