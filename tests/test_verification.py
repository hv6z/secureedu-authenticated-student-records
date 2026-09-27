"""Kiểm thử phát hiện chỉnh sửa ở từng lớp bảo vệ."""

from __future__ import annotations

import sqlite3

import pytest

from src.services.record_service import RecordService
from src.blockchain.block import calculate_block_hash


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


def test_modify_and_rehash_is_rejected_by_block_mac(populated) -> None:
    path, service, _ = populated
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT * FROM audit_blocks ORDER BY block_index"
        ).fetchall()
        previous_hash = rows[0]["block_hash"]
        for row in rows[1:]:
            timestamp = (
                "2030-01-01T00:00:00.000000Z"
                if row["block_index"] == 1
                else row["timestamp"]
            )
            block_hash = calculate_block_hash(
                block_index=row["block_index"],
                timestamp=timestamp,
                previous_hash=previous_hash,
                record_id=row["record_id"],
                version=row["version"],
                operation=row["operation"],
                envelope_hash=row["envelope_hash"],
                block_schema_version=row["block_schema_version"],
                actor_id=row["actor_id"],
                actor_role=row["actor_role"],
            )
            connection.execute(
                "UPDATE audit_blocks SET timestamp = ?, previous_hash = ?, "
                "block_hash = ? WHERE block_index = ?",
                (timestamp, previous_hash, block_hash, row["block_index"]),
            )
            if row["block_index"] == 1:
                connection.execute(
                    "UPDATE record_versions SET created_at = ? "
                    "WHERE record_id = ? AND version = ?",
                    (timestamp, row["record_id"], row["version"]),
                )
            previous_hash = block_hash
        connection.commit()
    finally:
        connection.close()

    report = service.verify_all()
    assert not report.valid
    assert any("HMAC của khối" in message for message in report.messages)


def test_consistent_suffix_truncation_is_rejected_by_external_anchor(
    populated,
) -> None:
    path, service, _ = populated
    connection = sqlite3.connect(path)
    try:
        last = connection.execute(
            "SELECT record_id, version FROM audit_blocks "
            "ORDER BY block_index DESC LIMIT 1"
        ).fetchone()
        connection.execute(
            "DELETE FROM audit_blocks WHERE block_index = "
            "(SELECT MAX(block_index) FROM audit_blocks)"
        )
        connection.execute(
            "DELETE FROM record_versions WHERE record_id = ? AND version = ?",
            last,
        )
        connection.execute("DELETE FROM records WHERE record_id = ?", (last[0],))
        connection.commit()
    finally:
        connection.close()

    report = service.verify_all()
    assert not report.valid
    assert any("checkpoint audit không khớp" in message.casefold() for message in report.messages)


def test_missing_anchor_fails_closed(populated) -> None:
    _, service, _ = populated
    service.audit_anchor_path.unlink()

    report = service.verify_all()
    assert not report.valid
    assert any("Thiếu checkpoint audit" in message for message in report.messages)
