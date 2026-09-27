"""Đo thông lượng ghi khi nhiều luồng cùng dùng một cơ sở dữ liệu."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.generate_dataset import generate_records  # noqa: E402
from experiments.system_metadata import collect_system_metadata  # noqa: E402
from src.config import Settings  # noqa: E402
from src.services.record_service import RecordService  # noqa: E402


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def run_once(
    *, writer_count: int, total_records: int, repeat: int, seed: int, key: bytes
) -> dict[str, object]:
    records = generate_records(total_records, seed + repeat)
    with tempfile.TemporaryDirectory(prefix="student-record-contention-") as temp_dir:
        database_path = Path(temp_dir) / "records.db"
        RecordService(database_path, key, key_id="contention-key").initialize()
        barrier = threading.Barrier(writer_count)

        def write_partition(writer_index: int) -> list[float]:
            service = RecordService(
                database_path, key, key_id="contention-key"
            )
            assigned = records[writer_index::writer_count]
            latencies: list[float] = []
            barrier.wait()
            for record in assigned:
                start = perf_counter_ns()
                service.create_student(
                    record,
                    actor_id=f"writer-{writer_index + 1}",
                    actor_role="registrar",
                )
                latencies.append((perf_counter_ns() - start) / 1_000_000)
            return latencies

        start = perf_counter_ns()
        with ThreadPoolExecutor(max_workers=writer_count) as executor:
            partitions = list(executor.map(write_partition, range(writer_count)))
        elapsed_seconds = (perf_counter_ns() - start) / 1_000_000_000
        latencies = [value for partition in partitions for value in partition]
        verifier = RecordService(database_path, key, key_id="contention-key")
        report = verifier.verify_all()
        if not report.valid or report.checked_versions != total_records:
            raise RuntimeError(
                "Ghi đồng thời làm mất tính toàn vẹn: " + "; ".join(report.messages)
            )

    return {
        "writers": writer_count,
        "total_records": total_records,
        "repeat": repeat,
        "seed": seed,
        "elapsed_seconds": elapsed_seconds,
        "throughput_records_per_second": total_records / elapsed_seconds,
        "latency_mean_ms": statistics.fmean(latencies),
        "latency_median_ms": statistics.median(latencies),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "latency_max_ms": max(latencies),
        "verification_valid": report.valid,
        "checked_versions": report.checked_versions,
    }


def write_summary(rows: list[dict[str, object]], path: Path) -> None:
    metrics = (
        "elapsed_seconds",
        "throughput_records_per_second",
        "latency_mean_ms",
        "latency_median_ms",
        "latency_p95_ms",
        "latency_max_ms",
    )
    fieldnames = ["writers", "metric", "mean", "median", "minimum", "maximum", "stdev"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for writer_count in sorted({int(row["writers"]) for row in rows}):
            group = [row for row in rows if int(row["writers"]) == writer_count]
            for metric in metrics:
                values = [float(row[metric]) for row in group]
                writer.writerow(
                    {
                        "writers": writer_count,
                        "metric": metric,
                        "mean": statistics.fmean(values),
                        "median": statistics.median(values),
                        "minimum": min(values),
                        "maximum": max(values),
                        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
                    }
                )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--writers", nargs="+", type=int, default=[1, 2, 4, 8])
    parser.add_argument("--records", type=int, default=120)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "results",
    )
    args = parser.parse_args()
    if args.records < 1 or args.repeats < 1 or any(value < 1 for value in args.writers):
        parser.error("Số bản ghi, lần lặp và số luồng phải lớn hơn 0.")

    key = Settings.from_env().encryption_key
    rows: list[dict[str, object]] = []
    for writer_count in args.writers:
        for repeat in range(1, args.repeats + 1):
            print(f"{writer_count} luồng, lần {repeat}/{args.repeats}")
            rows.append(
                run_once(
                    writer_count=writer_count,
                    total_records=args.records,
                    repeat=repeat,
                    seed=args.seed,
                    key=key,
                )
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = args.output_dir / f"contention_raw_{timestamp}.csv"
    summary_path = args.output_dir / f"contention_summary_{timestamp}.csv"
    metadata_path = args.output_dir / f"contention_metadata_{timestamp}.json"
    with raw_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_summary(rows, summary_path)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **collect_system_metadata(PROJECT_ROOT),
        "experiment": {
            "writers": args.writers,
            "total_records_per_run": args.records,
            "repeats": args.repeats,
            "seed": args.seed,
            "scope": (
                "threads in one Python process; writes serialized through "
                "one shared lock"
            ),
        },
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Kết quả thô: {raw_path}")
    print(f"Kết quả thống kê: {summary_path}")
    print(f"Môi trường và cấu hình: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
