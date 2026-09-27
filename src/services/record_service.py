"""Luồng thống nhất: chuẩn hóa, mã hóa, lưu phiên bản và nối khối."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.blockchain.chain import (
    append_block,
    latest_block,
    list_blocks as read_blocks,
)
from src.database.connection import connect_database, immediate_transaction
from src.database.repository import (
    StoredRecord,
    StoredVersion,
    get_record,
    get_record_by_token,
    get_version,
    insert_record,
    insert_version,
    list_records,
    update_record_head,
)
from src.database.schema import initialize_database
from src.domain.student import normalize_student_code, normalize_student_data
from src.encryption.aes_cipher import (
    AES_GCM_SCHEMA_VERSION,
    AesGcmCipher,
    EncryptedEnvelope,
)
from src.encryption.serialization import canonical_json_bytes, make_aad
from src.integrity import (
    calculate_envelope_hash,
    calculate_lookup_token,
    derive_audit_key,
    derive_lookup_key,
    verify_audit_anchor,
    write_audit_anchor,
)
from src.verification.verifier import VerificationReport, verify_database


_WRITE_LOCKS: dict[Path, threading.RLock] = {}
_WRITE_LOCKS_GUARD = threading.Lock()


def _shared_write_lock(database_path: Path) -> threading.RLock:
    """Trả về khóa ghi dùng chung cho mọi service trỏ tới cùng tệp DB."""

    lock_key = database_path.resolve()
    with _WRITE_LOCKS_GUARD:
        return _WRITE_LOCKS.setdefault(lock_key, threading.RLock())


class RecordServiceError(RuntimeError):
    """Lỗi nghiệp vụ cơ sở của dịch vụ hồ sơ."""


class RecordNotFoundError(RecordServiceError):
    """Không tìm thấy mã nội bộ của hồ sơ."""


class RecordDeletedError(RecordServiceError):
    """Hồ sơ đã bị xóa logic nên không thể tiếp tục sửa hoặc xóa."""


class VersionConflictError(RecordServiceError):
    """Phiên bản người gọi biết đã cũ hơn phiên bản trong cơ sở dữ liệu."""


class DuplicateStudentError(RecordServiceError):
    """Mã sinh viên đã tồn tại dưới dạng mã tra cứu HMAC."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _validate_expected_version(expected_version: int | None) -> None:
    if expected_version is None:
        return
    if isinstance(expected_version, bool) or not isinstance(expected_version, int):
        raise TypeError("expected_version phải là số nguyên hoặc None.")
    if expected_version < 1:
        raise ValueError("expected_version phải lớn hơn hoặc bằng 1.")


def _validate_actor(actor_id: str, actor_role: str) -> tuple[str, str]:
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ValueError("actor_id không được rỗng.")
    if not isinstance(actor_role, str):
        raise TypeError("actor_role phải là chuỗi.")
    normalized_role = actor_role.strip().casefold()
    if normalized_role not in {"system", "admin", "registrar", "auditor"}:
        raise ValueError("actor_role không hợp lệ.")
    return actor_id.strip(), normalized_role


class RecordService:
    """Giao diện duy nhất để ứng dụng thao tác với hồ sơ sinh viên."""

    def __init__(
        self,
        database_path: str | Path,
        key: bytes,
        key_id: str = "key-v1",
        audit_anchor_path: str | Path | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self._write_lock = _shared_write_lock(self.database_path)
        self.key_id = key_id
        self._cipher = AesGcmCipher(key, key_id=key_id)
        self._lookup_key = derive_lookup_key(key)
        self._audit_key = derive_audit_key(key)
        self.audit_anchor_path = (
            Path(audit_anchor_path)
            if audit_anchor_path is not None
            else self.database_path.with_suffix(
                self.database_path.suffix + ".audit-anchor.json"
            )
        )

    def initialize(self) -> None:
        with self._write_lock:
            anchor_bootstrap_allowed = initialize_database(
                self.database_path, self._audit_key
            )
            connection = connect_database(self.database_path)
            try:
                head = latest_block(connection)
                if self.audit_anchor_path.exists():
                    self._verify_anchor(head)
                elif anchor_bootstrap_allowed:
                    self._write_anchor(head)
                else:
                    raise RecordServiceError(
                        "Thiếu checkpoint audit của cơ sở dữ liệu đã tồn tại; "
                        "không tự động tạo lại để tránh che giấu rollback."
                    )
            finally:
                connection.close()

    def _verify_anchor(self, head) -> None:
        verify_audit_anchor(
            self.audit_anchor_path,
            self._audit_key,
            block_index=head.block_index,
            block_hash=head.block_hash,
            block_mac=head.block_mac,
        )

    def _write_anchor(self, head) -> None:
        write_audit_anchor(
            self.audit_anchor_path,
            self._audit_key,
            block_index=head.block_index,
            block_hash=head.block_hash,
            block_mac=head.block_mac,
        )

    def _verify_anchor_in_transaction(
        self, connection: sqlite3.Connection
    ) -> None:
        self._verify_anchor(latest_block(connection))

    def _refresh_anchor(self) -> None:
        connection = connect_database(self.database_path)
        try:
            self._write_anchor(latest_block(connection))
        finally:
            connection.close()

    @staticmethod
    def _envelope_from_version(version: StoredVersion) -> EncryptedEnvelope:
        return EncryptedEnvelope(
            schema_version=version.schema_version,
            algorithm=version.algorithm,
            key_id=version.key_id,
            nonce=version.nonce,
            ciphertext=version.ciphertext,
        )

    def _decrypt_version(self, version: StoredVersion) -> dict[str, Any]:
        envelope = self._envelope_from_version(version)
        plaintext = self._cipher.decrypt(
            envelope,
            aad=make_aad(
                version.record_id,
                version.version,
                version.operation,
                schema_version=version.schema_version,
                actor_id=version.actor_id,
                actor_role=version.actor_role,
            ),
        )
        value = json.loads(plaintext.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Nội dung hồ sơ giải mã không phải đối tượng JSON.")
        return value

    @staticmethod
    def _with_metadata(
        data: Mapping[str, Any], record: StoredRecord
    ) -> dict[str, Any]:
        result = dict(data)
        result.update(
            {
                "_record_id": record.record_id,
                "_version": record.current_version,
                "_status": record.status,
                "_created_at": record.created_at,
                "_updated_at": record.updated_at,
            }
        )
        return result

    def _write_version(
        self,
        connection: sqlite3.Connection,
        *,
        record_id: str,
        version: int,
        operation: str,
        data: Mapping[str, Any],
        timestamp: str,
        actor_id: str,
        actor_role: str,
    ) -> EncryptedEnvelope:
        aad = make_aad(
            record_id,
            version,
            operation,
            schema_version=AES_GCM_SCHEMA_VERSION,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        envelope = self._cipher.encrypt(canonical_json_bytes(data), aad=aad)
        envelope_hash = calculate_envelope_hash(
            record_id,
            version,
            operation,
            envelope,
            actor_id,
            actor_role,
        )
        insert_version(
            connection,
            record_id=record_id,
            version=version,
            schema_version=envelope.schema_version,
            algorithm=envelope.algorithm,
            key_id=envelope.key_id,
            nonce=envelope.nonce,
            ciphertext=envelope.ciphertext,
            envelope_hash=envelope_hash,
            operation=operation,
            actor_id=actor_id,
            actor_role=actor_role,
            timestamp=timestamp,
        )
        append_block(
            connection,
            timestamp=timestamp,
            record_id=record_id,
            version=version,
            operation=operation,
            envelope_hash=envelope_hash,
            audit_key=self._audit_key,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        return envelope

    def create_student(
        self,
        data: Mapping[str, Any],
        *,
        actor_id: str = "system",
        actor_role: str = "system",
    ) -> dict[str, Any]:
        actor_id, actor_role = _validate_actor(actor_id, actor_role)
        normalized = normalize_student_data(data)
        lookup_token = calculate_lookup_token(
            normalized["student_code"], self._lookup_key
        )
        record_id = str(uuid.uuid4())
        timestamp = _utc_now()

        with self._write_lock:
            connection = connect_database(self.database_path)
            try:
                with immediate_transaction(connection):
                    self._verify_anchor_in_transaction(connection)
                    if get_record_by_token(connection, lookup_token) is not None:
                        raise DuplicateStudentError("Mã sinh viên đã tồn tại.")
                    insert_record(
                        connection,
                        record_id=record_id,
                        lookup_token=lookup_token,
                        timestamp=timestamp,
                    )
                    self._write_version(
                        connection,
                        record_id=record_id,
                        version=1,
                        operation="CREATE",
                        data=normalized,
                        timestamp=timestamp,
                        actor_id=actor_id,
                        actor_role=actor_role,
                    )
            except sqlite3.IntegrityError as exc:
                raise RecordServiceError(
                    "Không thể ghi hồ sơ do ràng buộc toàn vẹn hoặc nonce bị trùng."
                ) from exc
            finally:
                connection.close()
            self._refresh_anchor()

        record = StoredRecord(
            record_id=record_id,
            lookup_token=lookup_token,
            current_version=1,
            status="active",
            created_at=timestamp,
            updated_at=timestamp,
        )
        return self._with_metadata(normalized, record)

    def update_student(
        self,
        record_id: str,
        data: Mapping[str, Any],
        expected_version: int | None = None,
        *,
        actor_id: str = "system",
        actor_role: str = "system",
    ) -> dict[str, Any]:
        _validate_expected_version(expected_version)
        actor_id, actor_role = _validate_actor(actor_id, actor_role)
        normalized = normalize_student_data(data)
        lookup_token = calculate_lookup_token(
            normalized["student_code"], self._lookup_key
        )
        timestamp = _utc_now()

        with self._write_lock:
            connection = connect_database(self.database_path)
            try:
                with immediate_transaction(connection):
                    self._verify_anchor_in_transaction(connection)
                    record = self._require_writable_record(connection, record_id)
                    self._check_version(record, expected_version)
                    owner = get_record_by_token(connection, lookup_token)
                    if owner is not None and owner.record_id != record_id:
                        raise DuplicateStudentError("Mã sinh viên đã tồn tại.")

                    next_version = record.current_version + 1
                    self._write_version(
                        connection,
                        record_id=record_id,
                        version=next_version,
                        operation="UPDATE",
                        data=normalized,
                        timestamp=timestamp,
                        actor_id=actor_id,
                        actor_role=actor_role,
                    )
                    update_record_head(
                        connection,
                        record_id=record_id,
                        version=next_version,
                        lookup_token=lookup_token,
                        status="active",
                        timestamp=timestamp,
                    )
            except sqlite3.IntegrityError as exc:
                raise RecordServiceError(
                    "Không thể ghi phiên bản do ràng buộc toàn vẹn hoặc nonce bị trùng."
                ) from exc
            finally:
                connection.close()
            self._refresh_anchor()

        updated = StoredRecord(
            record_id=record.record_id,
            lookup_token=lookup_token,
            current_version=next_version,
            status="active",
            created_at=record.created_at,
            updated_at=timestamp,
        )
        return self._with_metadata(normalized, updated)

    def delete_student(
        self,
        record_id: str,
        expected_version: int | None = None,
        *,
        actor_id: str = "system",
        actor_role: str = "system",
    ) -> dict[str, Any]:
        _validate_expected_version(expected_version)
        actor_id, actor_role = _validate_actor(actor_id, actor_role)
        timestamp = _utc_now()

        with self._write_lock:
            connection = connect_database(self.database_path)
            try:
                with immediate_transaction(connection):
                    self._verify_anchor_in_transaction(connection)
                    record = self._require_writable_record(connection, record_id)
                    self._check_version(record, expected_version)
                    current = get_version(connection, record_id, record.current_version)
                    if current is None:
                        raise RecordServiceError(
                            "Thiếu phiên bản hiện tại của hồ sơ."
                        )
                    snapshot = self._decrypt_version(current)
                    next_version = record.current_version + 1
                    self._write_version(
                        connection,
                        record_id=record_id,
                        version=next_version,
                        operation="DELETE",
                        data=snapshot,
                        timestamp=timestamp,
                        actor_id=actor_id,
                        actor_role=actor_role,
                    )
                    update_record_head(
                        connection,
                        record_id=record_id,
                        version=next_version,
                        lookup_token=record.lookup_token,
                        status="deleted",
                        timestamp=timestamp,
                    )
            except sqlite3.IntegrityError as exc:
                raise RecordServiceError(
                    "Không thể ghi phiên bản xóa do nonce bị trùng."
                ) from exc
            finally:
                connection.close()
            self._refresh_anchor()

        deleted = StoredRecord(
            record_id=record.record_id,
            lookup_token=record.lookup_token,
            current_version=next_version,
            status="deleted",
            created_at=record.created_at,
            updated_at=timestamp,
        )
        return self._with_metadata(snapshot, deleted)

    @staticmethod
    def _check_version(record: StoredRecord, expected_version: int | None) -> None:
        if expected_version is not None and expected_version != record.current_version:
            raise VersionConflictError(
                f"Phiên bản hiện tại là {record.current_version}, không phải "
                f"{expected_version}."
            )

    @staticmethod
    def _require_writable_record(
        connection: sqlite3.Connection, record_id: str
    ) -> StoredRecord:
        record = get_record(connection, record_id)
        if record is None:
            raise RecordNotFoundError("Không tìm thấy hồ sơ.")
        if record.status == "deleted":
            raise RecordDeletedError("Hồ sơ đã được xóa logic.")
        return record

    def _read_record(
        self,
        connection: sqlite3.Connection,
        record: StoredRecord,
        *,
        include_deleted: bool,
    ) -> dict[str, Any] | None:
        if record.status == "deleted" and not include_deleted:
            return None
        version = get_version(connection, record.record_id, record.current_version)
        if version is None:
            raise RecordServiceError("Thiếu phiên bản hiện tại của hồ sơ.")
        return self._with_metadata(self._decrypt_version(version), record)

    def get_student(
        self, record_id: str, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        connection = connect_database(self.database_path)
        try:
            record = get_record(connection, record_id)
            if record is None:
                return None
            return self._read_record(
                connection, record, include_deleted=include_deleted
            )
        finally:
            connection.close()

    def find_by_student_code(
        self, code: str, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        normalized_code = normalize_student_code(code)
        token = calculate_lookup_token(normalized_code, self._lookup_key)
        connection = connect_database(self.database_path)
        try:
            record = get_record_by_token(connection, token)
            if record is None:
                return None
            return self._read_record(
                connection, record, include_deleted=include_deleted
            )
        finally:
            connection.close()

    def list_students(self, include_deleted: bool = False) -> list[dict[str, Any]]:
        connection = connect_database(self.database_path)
        try:
            result: list[dict[str, Any]] = []
            for record in list_records(connection):
                value = self._read_record(
                    connection, record, include_deleted=include_deleted
                )
                if value is not None:
                    result.append(value)
            return result
        finally:
            connection.close()

    def list_blocks(self, limit: int | None = None) -> list[dict[str, Any]]:
        connection = connect_database(self.database_path)
        try:
            return [block.to_dict() for block in read_blocks(connection, limit)]
        finally:
            connection.close()

    def verify_all(self) -> VerificationReport:
        return verify_database(
            self.database_path,
            self._cipher,
            audit_key=self._audit_key,
            audit_anchor_path=self.audit_anchor_path,
            lookup_key=self._lookup_key,
        )

    def verify_student(self, record_id: str) -> VerificationReport:
        return verify_database(
            self.database_path,
            self._cipher,
            audit_key=self._audit_key,
            audit_anchor_path=self.audit_anchor_path,
            record_id=record_id,
            lookup_key=self._lookup_key,
        )
