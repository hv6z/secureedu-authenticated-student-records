"""Bảo đảm cơ sở dữ liệu schema v1 vẫn đọc được sau khi thêm actor/RBAC."""

from __future__ import annotations

import sqlite3

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.blockchain.block import calculate_block_hash, genesis_block
from src.encryption import AES_GCM_ALGORITHM, EncryptedEnvelope
from src.integrity import (
    calculate_envelope_hash,
    calculate_lookup_token,
    canonical_json_bytes,
    derive_lookup_key,
    make_aad,
)
from src.services.record_service import RecordService


LEGACY_SCHEMA = """
CREATE TABLE records (
    record_id TEXT PRIMARY KEY,
    lookup_token BLOB NOT NULL UNIQUE,
    current_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE record_versions (
    record_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    algorithm TEXT NOT NULL,
    key_id TEXT NOT NULL,
    nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    envelope_hash TEXT NOT NULL,
    operation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (record_id, version)
);
CREATE TABLE audit_blocks (
    block_index INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    record_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    operation TEXT NOT NULL,
    envelope_hash TEXT NOT NULL,
    block_hash TEXT NOT NULL UNIQUE
);
"""


def test_schema_v1_is_migrated_and_remains_verifiable(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    key = b"l" * 32
    record_id = "legacy-record"
    timestamp = "2026-07-01T00:00:00.000000Z"
    data = {
        "student_code": "SVLEGACY",
        "full_name": "Hồ Sơ Cũ",
        "date_of_birth": "2004-01-02",
        "program": "An toàn thông tin",
        "courses": [{"course_code": "AT01", "score": 8.0}],
        "gpa": 8.0,
    }
    aad = make_aad(record_id, 1, "CREATE", schema_version=1)
    nonce = b"n" * 12
    envelope = EncryptedEnvelope(
        schema_version=1,
        algorithm=AES_GCM_ALGORITHM,
        key_id="key-v1",
        nonce=nonce,
        ciphertext=AESGCM(key).encrypt(nonce, canonical_json_bytes(data), aad),
    )
    envelope_hash = calculate_envelope_hash(
        record_id, 1, "CREATE", envelope
    )
    genesis = genesis_block()
    create_hash = calculate_block_hash(
        block_index=1,
        timestamp=timestamp,
        previous_hash=genesis.block_hash,
        record_id=record_id,
        version=1,
        operation="CREATE",
        envelope_hash=envelope_hash,
        block_schema_version=1,
    )

    connection = sqlite3.connect(path)
    try:
        connection.executescript(LEGACY_SCHEMA)
        connection.execute(
            "INSERT INTO records VALUES (?, ?, 1, 'active', ?, ?)",
            (
                record_id,
                calculate_lookup_token("SVLEGACY", derive_lookup_key(key)),
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            "INSERT INTO record_versions VALUES (?, 1, 1, ?, 'key-v1', ?, ?, ?, 'CREATE', ?)",
            (
                record_id,
                AES_GCM_ALGORITHM,
                nonce,
                envelope.ciphertext,
                envelope_hash,
                timestamp,
            ),
        )
        connection.execute(
            "INSERT INTO audit_blocks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            genesis.as_database_tuple()[:7] + (genesis.block_hash,),
        )
        connection.execute(
            "INSERT INTO audit_blocks VALUES (1, ?, ?, ?, 1, 'CREATE', ?, ?)",
            (timestamp, genesis.block_hash, record_id, envelope_hash, create_hash),
        )
        connection.commit()
    finally:
        connection.close()

    service = RecordService(path, key)
    service.initialize()
    student = service.get_student(record_id)
    report = service.verify_all()

    assert student is not None
    assert student["student_code"] == "SVLEGACY"
    assert report.valid is True
    assert service.list_blocks()[1]["block_schema_version"] == 1
    assert service.list_blocks()[1]["actor_id"] == "system"
