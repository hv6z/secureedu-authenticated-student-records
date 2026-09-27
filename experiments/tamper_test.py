"""Đo khả năng phát hiện các thay đổi trái phép trên bản sao cơ sở dữ liệu."""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import platform
import sqlite3
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.blockchain.block import calculate_block_hash  # noqa: E402
from src.config import Settings  # noqa: E402
from src.services.record_service import RecordService  # noqa: E402
from experiments.system_metadata import collect_system_metadata  # noqa: E402


Mutation = Callable[[sqlite3.Connection], None]


def _flip_blob(value: bytes, *, last: bool = False) -> bytes:
    changed = bytearray(value)
    index = -1 if last else 0
    changed[index] ^= 1
    return bytes(changed)


def _change_hex(value: str) -> str:
    replacement = "1" if value[0] != "1" else "0"
    return replacement + value[1:]


def mutate_ciphertext(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT record_id, version, ciphertext FROM record_versions ORDER BY record_id, version LIMIT 1"
    ).fetchone()
    connection.execute(
        "UPDATE record_versions SET ciphertext = ? WHERE record_id = ? AND version = ?",
        (_flip_blob(bytes(row[2])), row[0], row[1]),
    )


def mutate_authentication_tag(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT record_id, version, ciphertext FROM record_versions ORDER BY record_id, version LIMIT 1"
    ).fetchone()
    connection.execute(
        "UPDATE record_versions SET ciphertext = ? WHERE record_id = ? AND version = ?",
        (_flip_blob(bytes(row[2]), last=True), row[0], row[1]),
    )


def mutate_nonce(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT record_id, version, nonce FROM record_versions ORDER BY record_id, version LIMIT 1"
    ).fetchone()
    connection.execute(
        "UPDATE record_versions SET nonce = ? WHERE record_id = ? AND version = ?",
        (_flip_blob(bytes(row[2])), row[0], row[1]),
    )


def mutate_envelope_hash(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT record_id, version, envelope_hash FROM record_versions ORDER BY record_id, version LIMIT 1"
    ).fetchone()
    connection.execute(
        "UPDATE record_versions SET envelope_hash = ? WHERE record_id = ? AND version = ?",
        (_change_hex(str(row[2])), row[0], row[1]),
    )


def mutate_previous_hash(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT block_index, previous_hash FROM audit_blocks WHERE block_index > 1 ORDER BY block_index LIMIT 1"
    ).fetchone()
    connection.execute(
        "UPDATE audit_blocks SET previous_hash = ? WHERE block_index = ?",
        (_change_hex(str(row[1])), row[0]),
    )


def delete_middle_block(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT block_index FROM audit_blocks WHERE block_index > 0 ORDER BY block_index LIMIT 1 OFFSET 1"
    ).fetchone()
    connection.execute("DELETE FROM audit_blocks WHERE block_index = ?", (row[0],))


def _business_blocks(connection: sqlite3.Connection) -> list[dict[str, object]]:
    connection.row_factory = sqlite3.Row
    return [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM audit_blocks WHERE block_index > 0 "
            "ORDER BY block_index"
        ).fetchall()
    ]


def _rewrite_business_chain(
    connection: sqlite3.Connection, rows: list[dict[str, object]]
) -> None:
    """Mô phỏng DB writer biết thuật toán hash nhưng không có audit key."""

    genesis_hash = str(
        connection.execute(
            "SELECT block_hash FROM audit_blocks WHERE block_index = 0"
        ).fetchone()[0]
    )
    connection.execute("DELETE FROM audit_blocks WHERE block_index > 0")
    previous_hash = genesis_hash
    for block_index, row in enumerate(rows, start=1):
        block_hash = calculate_block_hash(
            block_index=block_index,
            timestamp=str(row["timestamp"]),
            previous_hash=previous_hash,
            record_id=str(row["record_id"]),
            version=int(row["version"]),
            operation=str(row["operation"]),
            envelope_hash=str(row["envelope_hash"]),
            block_schema_version=int(row["block_schema_version"]),
            actor_id=str(row["actor_id"]),
            actor_role=str(row["actor_role"]),
        )
        connection.execute(
            """
            INSERT INTO audit_blocks (
                block_index, timestamp, previous_hash, record_id, version,
                operation, envelope_hash, block_schema_version, actor_id,
                actor_role, block_hash, block_mac
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                block_index,
                row["timestamp"],
                previous_hash,
                row["record_id"],
                row["version"],
                row["operation"],
                row["envelope_hash"],
                row["block_schema_version"],
                row["actor_id"],
                row["actor_role"],
                block_hash,
                row["block_mac"],
            ),
        )
        previous_hash = block_hash


def modify_and_rehash(connection: sqlite3.Connection) -> None:
    rows = _business_blocks(connection)
    rows[0]["block_schema_version"] = 2
    _rewrite_business_chain(connection, rows)


def change_timestamp_and_rehash(connection: sqlite3.Connection) -> None:
    rows = _business_blocks(connection)
    changed_timestamp = "2030-01-01T00:00:00.000000Z"
    rows[0]["timestamp"] = changed_timestamp
    connection.execute(
        "UPDATE record_versions SET created_at = ? "
        "WHERE record_id = ? AND version = ?",
        (changed_timestamp, rows[0]["record_id"], rows[0]["version"]),
    )
    _rewrite_business_chain(connection, rows)


def delete_record_and_rechain(connection: sqlite3.Connection) -> None:
    rows = _business_blocks(connection)
    target = str(rows[1]["record_id"])
    connection.execute("DELETE FROM record_versions WHERE record_id = ?", (target,))
    connection.execute("DELETE FROM records WHERE record_id = ?", (target,))
    _rewrite_business_chain(
        connection,
        [row for row in rows if str(row["record_id"]) != target],
    )


def truncate_suffix_and_repair_head(connection: sqlite3.Connection) -> None:
    rows = _business_blocks(connection)
    removed = rows.pop()
    record_id = str(removed["record_id"])
    version = int(removed["version"])
    connection.execute(
        "DELETE FROM record_versions WHERE record_id = ? AND version = ?",
        (record_id, version),
    )
    previous = connection.execute(
        "SELECT version, operation, created_at FROM record_versions "
        "WHERE record_id = ? ORDER BY version DESC LIMIT 1",
        (record_id,),
    ).fetchone()
    connection.execute(
        "UPDATE records SET current_version = ?, status = ?, updated_at = ? "
        "WHERE record_id = ?",
        (
            previous[0],
            "deleted" if previous[1] == "DELETE" else "active",
            previous[2],
            record_id,
        ),
    )
    _rewrite_business_chain(connection, rows)


def splice_valid_histories(connection: sqlite3.Connection) -> None:
    rows = _business_blocks(connection)
    rows[0], rows[1] = rows[1], rows[0]
    _rewrite_business_chain(connection, rows)


def reorder_and_reindex(connection: sqlite3.Connection) -> None:
    rows = _business_blocks(connection)
    rows.reverse()
    _rewrite_business_chain(connection, rows)


def partial_record_rollback(connection: sqlite3.Connection) -> None:
    rows = _business_blocks(connection)
    updated = next(row for row in rows if int(row["version"]) > 1)
    target = str(updated["record_id"])
    connection.execute(
        "DELETE FROM record_versions WHERE record_id = ? AND version > 1",
        (target,),
    )
    prior = connection.execute(
        "SELECT created_at FROM record_versions "
        "WHERE record_id = ? AND version = 1",
        (target,),
    ).fetchone()
    connection.execute(
        "UPDATE records SET current_version = 1, status = 'active', "
        "updated_at = ? WHERE record_id = ?",
        (prior[0], target),
    )
    _rewrite_business_chain(
        connection,
        [
            row
            for row in rows
            if not (str(row["record_id"]) == target and int(row["version"]) > 1)
        ],
    )


MUTATIONS: dict[str, tuple[str, Mutation]] = {
    "thay_doi_ban_ma": ("inconsistent_mutation", mutate_ciphertext),
    "thay_doi_the_xac_thuc": ("inconsistent_mutation", mutate_authentication_tag),
    "thay_doi_nonce": ("inconsistent_mutation", mutate_nonce),
    "thay_doi_bam_phong_bi": ("inconsistent_mutation", mutate_envelope_hash),
    "thay_doi_lien_ket_khoi": ("inconsistent_mutation", mutate_previous_hash),
    "xoa_khoi_giua": ("inconsistent_mutation", delete_middle_block),
    "sua_va_bam_lai": ("adaptive_db_writer", modify_and_rehash),
    "sua_timestamp_va_bam_lai": ("adaptive_db_writer", change_timestamp_and_rehash),
    "xoa_ho_so_va_noi_lai_chuoi": ("adaptive_db_writer", delete_record_and_rechain),
    "cat_duoi_va_sua_head": ("adaptive_db_writer", truncate_suffix_and_repair_head),
    "ghep_lich_su_hop_le": ("adaptive_db_writer", splice_valid_histories),
    "sap_xep_va_danh_chi_muc_lai": ("adaptive_db_writer", reorder_and_reindex),
    "rollback_rieng_mot_ho_so": ("adaptive_db_writer", partial_record_rollback),
}


def _sample_records() -> tuple[dict[str, object], dict[str, object]]:
    first = {
        "student_code": "TAMPER001",
        "full_name": "Nguyễn Minh An",
        "date_of_birth": "2004-03-12",
        "program": "An toàn thông tin",
        "courses": [{"course_code": "MMH01", "course_name": "Mật mã học", "score": 8.5}],
        "gpa": 8.5,
    }
    second = {
        "student_code": "TAMPER002",
        "full_name": "Trần Hoài Nam",
        "date_of_birth": "2003-11-24",
        "program": "Công nghệ thông tin",
        "courses": [{"course_code": "CSDL01", "course_name": "Cơ sở dữ liệu", "score": 7.9}],
        "gpa": 7.9,
    }
    return first, second


def _prepare_database(path: Path, key: bytes, key_id: str) -> RecordService:
    service = RecordService(path, key, key_id=key_id)
    service.initialize()
    first, second = _sample_records()
    created = service.create_student(first)
    service.create_student(second)
    changed = dict(first)
    changed["gpa"] = 8.8
    service.update_student(
        str(created["_record_id"]),
        changed,
        expected_version=int(created["_version"]),
    )
    report = service.verify_all()
    if not report.valid:
        raise RuntimeError("Cơ sở dữ liệu gốc không hợp lệ: " + "; ".join(report.messages))
    return service


def run_trials(
    *, trials: int, key: bytes, key_id: str
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for case_name, (attacker_model, mutation) in MUTATIONS.items():
        for trial in range(1, trials + 1):
            print(f"Trường hợp {case_name}, lần {trial}/{trials}")
            with tempfile.TemporaryDirectory(prefix="student-record-tamper-") as temp_dir:
                database_path = Path(temp_dir) / "tampered.db"
                service = _prepare_database(database_path, key, key_id)
                connection = sqlite3.connect(database_path)
                try:
                    with connection:
                        mutation(connection)
                finally:
                    connection.close()
                report = service.verify_all()
                rows.append(
                    {
                        "case": case_name,
                        "attacker_model": attacker_model,
                        "trial": trial,
                        "detected": int(not report.valid),
                        "message_count": len(report.messages),
                        "messages": " | ".join(report.messages),
                    }
                )
    return rows


def write_results(rows: list[dict[str, object]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = output_dir / f"tamper_raw_{timestamp}.csv"
    summary_path = output_dir / f"tamper_summary_{timestamp}.csv"
    with raw_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case",
                "attacker_model",
                "trial",
                "detected",
                "message_count",
                "messages",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case",
                "attacker_model",
                "trials",
                "detected",
                "detection_rate",
            ],
        )
        writer.writeheader()
        for case_name, (attacker_model, _mutation) in MUTATIONS.items():
            selected = [row for row in rows if row["case"] == case_name]
            detected = sum(int(row["detected"]) for row in selected)
            writer.writerow(
                {
                    "case": case_name,
                    "attacker_model": attacker_model,
                    "trials": len(selected),
                    "detected": detected,
                    "detection_rate": detected / len(selected),
                }
            )
    return raw_path, summary_path


def write_metadata(output_path: Path, *, trials: int) -> None:
    """Ghi môi trường và phạm vi thử sửa đổi, không ghi khóa bí mật."""
    packages: dict[str, str] = {}
    for package in ("Flask", "cryptography"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = "not-installed"
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        **collect_system_metadata(PROJECT_ROOT),
        "python": sys.version,
        "sqlite": sqlite3.sqlite_version,
        "packages": packages,
        "tamper_experiment": {
            "trials_per_case": trials,
            "cases": list(MUTATIONS),
        },
    }
    output_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Thử thay đổi trái phép trên bản sao SQLite.")
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "results",
    )
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("Số lần thử phải lớn hơn 0.")

    settings = Settings.from_env()
    rows = run_trials(
        trials=args.trials,
        key=settings.encryption_key,
        key_id=settings.key_id,
    )
    raw_path, summary_path = write_results(rows, args.output_dir)
    metadata_path = args.output_dir / (
        raw_path.stem.replace("tamper_raw_", "tamper_metadata_") + ".json"
    )
    write_metadata(metadata_path, trials=args.trials)
    print(f"Kết quả thô: {raw_path}")
    print(f"Tỷ lệ phát hiện: {summary_path}")
    print(f"Môi trường và cấu hình: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
