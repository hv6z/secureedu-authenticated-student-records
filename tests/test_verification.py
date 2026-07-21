"""Kiểm thử phát hiện chỉnh sửa ở từng lớp bảo vệ."""

from __future__ import annotations

import sqlite3

import pytest

from src.services.record_service import RecordService


def _student(code: str = "SV001") -> dict:
    return {
        "student_code": code,
        "full_name": "Nguyễn Văn An",
        "date_of_birth": "2004-05-20",
        "program": "An toàn thông tin",
        "courses": [{"course_code": "MMH101", "score": 8.5}],
        "gpa": 8.5,
    }


@pytest.fixture
def populated(tmp_path):
    path = tmp_path / "records.db"
    service = RecordService(path, b"v" * 32)
    service.initialize()
    first = service.create_student(_student("SV001"))
    service.update_student(first["_record_id"], _student("SV001"))
    service.create_student(_student("SV002"))
    return path, service, first["_record_id"]


def test_valid_database_and_report_shape(populated) -> None:
    _, service, record_id = populated
    report = service.verify_all()
    assert report.valid
    assert report.messages == ()
    assert report.checked_blocks == 4
    assert report.checked_versions == 3
    assert service.verify_student(record_id).valid
    assert report.to_dict()["valid"] is True


def test_tampered_ciphertext_breaks_hash_and_aes_gcm(populated) -> None:
    path, service, _ = populated
    connection = sqlite3.connect(path)
    try:
        value = connection.execute(
            "SELECT ciphertext FROM record_versions LIMIT 1"
        ).fetchone()[0]
        changed = bytes([value[0] ^ 1]) + value[1:]
        connection.execute(
            "UPDATE record_versions SET ciphertext = ? WHERE rowid = "
            "(SELECT rowid FROM record_versions LIMIT 1)",
            (changed,),
        )
        connection.commit()
    finally:
        connection.close()

    report = service.verify_all()
    assert not report.valid
    joined = " ".join(report.messages)
    assert "băm gói mã hóa" in joined
    assert "xác thực hoặc giải mã" in joined


def test_tampered_envelope_hash_is_detected(populated) -> None:
    path, service, _ = populated
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE record_versions SET envelope_hash = ? WHERE version = 1",
            ("f" * 64,),
        )
        connection.commit()
    finally:
        connection.close()
    assert not service.verify_all().valid


def test_tampered_actor_context_is_detected(populated) -> None:
    path, service, _ = populated
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE record_versions SET actor_id = 'attacker' "
            "WHERE rowid = (SELECT rowid FROM record_versions LIMIT 1)"
        )
        connection.commit()
    finally:
        connection.close()

    report = service.verify_all()
    assert not report.valid
    joined = " ".join(report.messages)
    assert "không khớp" in joined
    assert "xác thực hoặc giải mã" in joined


def test_malformed_envelope_is_reported_instead_of_crashing(populated) -> None:
    path, service, _ = populated
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE record_versions SET nonce = x'00' WHERE rowid = "
            "(SELECT rowid FROM record_versions LIMIT 1)"
        )
        connection.commit()
    finally:
        connection.close()

    report = service.verify_all()
    assert not report.valid
    assert any("Gói mã hóa không hợp lệ" in message for message in report.messages)


def test_deleted_block_is_detected(populated) -> None:
    path, service, _ = populated
    connection = sqlite3.connect(path)
    try:
        connection.execute("DELETE FROM audit_blocks WHERE block_index = 2")
        connection.commit()
    finally:
        connection.close()

    report = service.verify_all()
    assert not report.valid
    assert any("thứ tự khối" in message for message in report.messages)
    assert any("Thiếu khối" in message for message in report.messages)


def test_reordered_or_rewritten_block_is_detected(populated) -> None:
    path, service, _ = populated
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE audit_blocks SET record_id = 'doi-thu-tu' WHERE block_index = 1"
        )
        connection.commit()
    finally:
        connection.close()

    report = service.verify_all()
    assert not report.valid
    assert any("Giá trị băm của khối 1" in message for message in report.messages)
    assert any("không có phiên bản" in message for message in report.messages)
