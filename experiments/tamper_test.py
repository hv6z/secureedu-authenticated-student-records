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


MUTATIONS: dict[str, Mutation] = {
    "thay_doi_ban_ma": mutate_ciphertext,
    "thay_doi_the_xac_thuc": mutate_authentication_tag,
    "thay_doi_nonce": mutate_nonce,
    "thay_doi_bam_phong_bi": mutate_envelope_hash,
    "thay_doi_lien_ket_khoi": mutate_previous_hash,
    "xoa_khoi_giua": delete_middle_block,
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
    for case_name, mutation in MUTATIONS.items():
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
            fieldnames=["case", "trial", "detected", "message_count", "messages"],
        )
        writer.writeheader()
        writer.writerows(rows)

    with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["case", "trials", "detected", "detection_rate"],
        )
        writer.writeheader()
        for case_name in MUTATIONS:
            selected = [row for row in rows if row["case"] == case_name]
            detected = sum(int(row["detected"]) for row in selected)
            writer.writerow(
                {
                    "case": case_name,
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
