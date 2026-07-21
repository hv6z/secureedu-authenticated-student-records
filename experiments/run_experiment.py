"""Đo ba cấu hình lưu trữ trên cùng tập dữ liệu và cùng kiểu thao tác."""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import platform
import random
import sqlite3
import statistics
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.generate_dataset import generate_records  # noqa: E402
from src.encryption.aes_cipher import AesGcmCipher, EncryptedEnvelope  # noqa: E402
from src.encryption.serialization import canonical_json_bytes  # noqa: E402
from src.services.record_service import RecordService  # noqa: E402


PROFILES = ("sqlite", "sqlite_aes", "sqlite_aes_chain")
METRICS = (
    "add_total_ms",
    "add_per_record_ms",
    "query_total_ms",
    "query_per_record_ms",
    "verify_total_ms",
    "encrypt_per_record_ms",
    "decrypt_per_record_ms",
    "database_size_bytes",
)


def _elapsed_ms(start_ns: int) -> float:
    return (perf_counter_ns() - start_ns) / 1_000_000


def _database_size(path: Path) -> int:
    return sum(
        candidate.stat().st_size
        for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm"))
        if candidate.exists()
    )


def _aad_for_benchmark(record_id: str) -> bytes:
    return canonical_json_bytes(
        {"domain": "benchmark-sqlite-aes-v1", "record_id": record_id}
    )


def benchmark_sqlite(records: list[dict[str, object]], database_path: Path) -> dict[str, float]:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("CREATE TABLE records (record_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    start = perf_counter_ns()
    for record in records:
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with connection:
            connection.execute(
                "INSERT INTO records(record_id, payload) VALUES (?, ?)",
                (record["student_code"], payload),
            )
    add_total_ms = _elapsed_ms(start)

    start = perf_counter_ns()
    rows = connection.execute("SELECT payload FROM records ORDER BY record_id").fetchall()
    decoded = [json.loads(row[0]) for row in rows]
    query_total_ms = _elapsed_ms(start)

    start = perf_counter_ns()
    valid = all(isinstance(item, dict) and item.get("student_code") for item in decoded)
    verify_total_ms = _elapsed_ms(start)
    connection.close()
    if not valid or len(decoded) != len(records):
        raise RuntimeError("Cấu hình SQLite trả về dữ liệu không hợp lệ.")

    size = len(records)
    return {
        "add_total_ms": add_total_ms,
        "add_per_record_ms": add_total_ms / size,
        "query_total_ms": query_total_ms,
        "query_per_record_ms": query_total_ms / size,
        "verify_total_ms": verify_total_ms,
        "encrypt_per_record_ms": 0.0,
        "decrypt_per_record_ms": 0.0,
        "database_size_bytes": float(_database_size(database_path)),
    }


def benchmark_sqlite_aes(
    records: list[dict[str, object]], database_path: Path, key: bytes
) -> dict[str, float]:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute(
        """
        CREATE TABLE records (
            record_id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            algorithm TEXT NOT NULL,
            key_id TEXT NOT NULL,
            nonce BLOB NOT NULL,
            ciphertext BLOB NOT NULL,
            UNIQUE(key_id, nonce)
        )
        """
    )
    cipher = AesGcmCipher(key, key_id="benchmark-key")
    encrypt_ms = 0.0

    start = perf_counter_ns()
    for record in records:
        record_id = str(record["student_code"])
        crypto_start = perf_counter_ns()
        envelope = cipher.encrypt(
            canonical_json_bytes(record),
            aad=_aad_for_benchmark(record_id),
        )
        encrypt_ms += _elapsed_ms(crypto_start)
        with connection:
            connection.execute(
                """
                INSERT INTO records(
                    record_id, schema_version, algorithm, key_id, nonce, ciphertext
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    envelope.schema_version,
                    envelope.algorithm,
                    envelope.key_id,
                    envelope.nonce,
                    envelope.ciphertext,
                ),
            )
    add_total_ms = _elapsed_ms(start)

    start = perf_counter_ns()
    rows = connection.execute(
        """
        SELECT record_id, schema_version, algorithm, key_id, nonce, ciphertext
        FROM records ORDER BY record_id
        """
    ).fetchall()
    decoded: list[dict[str, object]] = []
    decrypt_ms = 0.0
    for row in rows:
        envelope = EncryptedEnvelope(
            schema_version=row[1],
            algorithm=row[2],
            key_id=row[3],
            nonce=bytes(row[4]),
            ciphertext=bytes(row[5]),
        )
        crypto_start = perf_counter_ns()
        plaintext = cipher.decrypt(envelope, aad=_aad_for_benchmark(row[0]))
        decrypt_ms += _elapsed_ms(crypto_start)
        decoded.append(json.loads(plaintext.decode("utf-8")))
    query_total_ms = _elapsed_ms(start)

    start = perf_counter_ns()
    for row in rows:
        envelope = EncryptedEnvelope(
            schema_version=row[1],
            algorithm=row[2],
            key_id=row[3],
            nonce=bytes(row[4]),
            ciphertext=bytes(row[5]),
        )
        cipher.decrypt(envelope, aad=_aad_for_benchmark(row[0]))
    verify_total_ms = _elapsed_ms(start)
    connection.close()

    if len(decoded) != len(records):
        raise RuntimeError("Cấu hình SQLite và AES-GCM trả về thiếu dữ liệu.")

    size = len(records)
    return {
        "add_total_ms": add_total_ms,
        "add_per_record_ms": add_total_ms / size,
        "query_total_ms": query_total_ms,
        "query_per_record_ms": query_total_ms / size,
        "verify_total_ms": verify_total_ms,
        "encrypt_per_record_ms": encrypt_ms / size,
        "decrypt_per_record_ms": decrypt_ms / size,
        "database_size_bytes": float(_database_size(database_path)),
    }


def benchmark_full(
    records: list[dict[str, object]], database_path: Path, key: bytes
) -> dict[str, float]:
    service = RecordService(database_path, key, key_id="benchmark-key")
    service.initialize()

    start = perf_counter_ns()
    for record in records:
        service.create_student(record)
    add_total_ms = _elapsed_ms(start)

    start = perf_counter_ns()
    decoded = service.list_students()
    query_total_ms = _elapsed_ms(start)

    start = perf_counter_ns()
    report = service.verify_all()
    verify_total_ms = _elapsed_ms(start)
    if not report.valid:
        raise RuntimeError("Cấu hình đầy đủ không vượt qua xác minh: " + "; ".join(report.messages))
    if len(decoded) != len(records):
        raise RuntimeError("Cấu hình đầy đủ trả về thiếu dữ liệu.")

    size = len(records)
    return {
        "add_total_ms": add_total_ms,
        "add_per_record_ms": add_total_ms / size,
        "query_total_ms": query_total_ms,
        "query_per_record_ms": query_total_ms / size,
        "verify_total_ms": verify_total_ms,
        "encrypt_per_record_ms": float("nan"),
        "decrypt_per_record_ms": float("nan"),
        "database_size_bytes": float(_database_size(database_path)),
    }


def run_benchmarks(
    *, sizes: list[int], repeats: int, profiles: list[str], seed: int, key: bytes
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    functions = {
        "sqlite": lambda records, path: benchmark_sqlite(records, path),
        "sqlite_aes": lambda records, path: benchmark_sqlite_aes(records, path, key),
        "sqlite_aes_chain": lambda records, path: benchmark_full(records, path, key),
    }

    for size in sizes:
        records = generate_records(size, seed)
        for repeat in range(1, repeats + 1):
            execution_order = list(profiles)
            random.Random(f"{seed}:{size}:{repeat}").shuffle(execution_order)
            for order_position, profile in enumerate(execution_order, start=1):
                print(f"Quy mô {size}, lần {repeat}/{repeats}, cấu hình {profile}")
                with tempfile.TemporaryDirectory(prefix="student-record-benchmark-") as temp_dir:
                    database_path = Path(temp_dir) / f"{profile}.db"
                    metrics = functions[profile](records, database_path)
                rows.append(
                    {
                        "profile": profile,
                        "size": size,
                        "repeat": repeat,
                        "order_position": order_position,
                        "seed": seed,
                        **metrics,
                    }
                )
    return rows


def write_raw_results(rows: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["profile", "size", "repeat", "order_position", "seed", *METRICS]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, object]], output_path: Path) -> None:
    groups: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["profile"]), int(row["size"]))].append(row)

    fieldnames = ["profile", "size", "metric", "mean", "median", "minimum", "maximum", "stdev"]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for (profile, size), group in sorted(groups.items()):
            for metric in METRICS:
                values = [float(row[metric]) for row in group]
                finite_values = [value for value in values if value == value]
                if not finite_values:
                    continue
                writer.writerow(
                    {
                        "profile": profile,
                        "size": size,
                        "metric": metric,
                        "mean": statistics.fmean(finite_values),
                        "median": statistics.median(finite_values),
                        "minimum": min(finite_values),
                        "maximum": max(finite_values),
                        "stdev": statistics.stdev(finite_values) if len(finite_values) > 1 else 0.0,
                    }
                )


def write_metadata(
    output_path: Path,
    *,
    sizes: list[int],
    repeats: int,
    profiles: list[str],
    seed: int,
) -> None:
    """Ghi bối cảnh chạy để số liệu có thể được đối chiếu và tái lập."""
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
        "python": sys.version,
        "sqlite": sqlite3.sqlite_version,
        "packages": packages,
        "experiment": {
            "sizes": sizes,
            "repeats": repeats,
            "profiles": profiles,
            "seed": seed,
            "timer": "time.perf_counter_ns",
        },
    }
    output_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Chạy thực nghiệm ba cấu hình lưu trữ.")
    parser.add_argument("--sizes", nargs="+", type=int, default=[100, 1000, 10000])
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(PROFILES))
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "experiments" / "results")
    args = parser.parse_args()
    if args.repeats < 1 or any(size < 1 for size in args.sizes):
        parser.error("Mọi quy mô và số lần lặp phải lớn hơn 0.")

    from src.config import Settings

    settings = Settings.from_env()
    rows = run_benchmarks(
        sizes=args.sizes,
        repeats=args.repeats,
        profiles=args.profiles,
        seed=args.seed,
        key=settings.encryption_key,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = args.output_dir / f"raw_{timestamp}.csv"
    summary_path = args.output_dir / f"summary_{timestamp}.csv"
    metadata_path = args.output_dir / f"metadata_{timestamp}.json"
    write_raw_results(rows, raw_path)
    write_summary(rows, summary_path)
    write_metadata(
        metadata_path,
        sizes=args.sizes,
        repeats=args.repeats,
        profiles=args.profiles,
        seed=args.seed,
    )
    print(f"Kết quả thô: {raw_path}")
    print(f"Kết quả thống kê: {summary_path}")
    print(f"Môi trường và cấu hình: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
