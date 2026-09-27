"""Kiểm thử cấu trúc khối và chuỗi được lưu trong SQLite."""

from __future__ import annotations

import pytest

from src.blockchain.block import genesis_block
from src.integrity import derive_audit_key
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


def test_genesis_is_fixed() -> None:
    audit_key = derive_audit_key(b"g" * 32)
    genesis = genesis_block(audit_key)
    assert genesis == genesis_block(audit_key)
    assert genesis.block_index == 0
    assert genesis.expected_hash() == genesis.block_hash
    assert genesis.has_valid_mac(audit_key)


def test_blocks_link_create_update_delete(tmp_path) -> None:
    service = RecordService(tmp_path / "records.db", b"k" * 32)
    service.initialize()
    created = service.create_student(_student())
    changed = _student()
    changed["gpa"] = 9
    service.update_student(created["_record_id"], changed, expected_version=1)
    service.delete_student(created["_record_id"], expected_version=2)

    blocks = service.list_blocks()
    assert [item["block_index"] for item in blocks] == [0, 1, 2, 3]
    assert [item["operation"] for item in blocks] == [
        "GENESIS",
        "CREATE",
        "UPDATE",
        "DELETE",
    ]
    assert [item["actor_role"] for item in blocks] == [
        "system",
        "system",
        "system",
        "system",
    ]
    assert [item["block_schema_version"] for item in blocks] == [3, 3, 3, 3]
    assert all(len(item["block_mac"]) == 64 for item in blocks)
    for previous, current in zip(blocks, blocks[1:]):
        assert current["previous_hash"] == previous["block_hash"]


def test_list_blocks_limit(tmp_path) -> None:
    service = RecordService(tmp_path / "records.db", b"z" * 32)
    service.initialize()
    service.create_student(_student())
    assert len(service.list_blocks(limit=1)) == 1
    assert service.list_blocks(limit=0) == []
    with pytest.raises(ValueError):
        service.list_blocks(limit=1.5)  # type: ignore[arg-type]
