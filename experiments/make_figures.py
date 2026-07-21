"""Tạo biểu đồ từ tệp thống kê do run_experiment.py sinh ra."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
DEFAULT_FIGURE_DIR = PROJECT_ROOT / "docs" / "figures"

PROFILE_LABELS = {
    "sqlite": "chỉ SQLite",
    "sqlite_aes": "SQLite và AES-GCM",
    "sqlite_aes_chain": "SQLite, AES-GCM và chuỗi băm",
}

FIGURES = (
    ("add_per_record_ms", "Thời gian thêm một hồ sơ", "Thời gian trung bình (ms)", "thoi_gian_them.png"),
    ("query_per_record_ms", "Thời gian đọc một hồ sơ", "Thời gian trung bình (ms)", "thoi_gian_doc.png"),
    ("verify_total_ms", "Thời gian xác minh toàn bộ dữ liệu", "Thời gian trung bình (ms)", "thoi_gian_xac_minh.png"),
    ("database_size_bytes", "Dung lượng lưu trữ", "Dung lượng trung bình (byte)", "dung_luong_luu_tru.png"),
)


def find_latest_summary(results_dir: Path) -> Path:
    candidates = sorted(results_dir.glob("summary_*.csv"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError("Chưa có tệp summary_*.csv. Hãy chạy thực nghiệm trước.")
    return candidates[-1]


def load_means(path: Path) -> dict[str, dict[str, list[tuple[int, float]]]]:
    values: dict[str, dict[str, list[tuple[int, float]]]] = defaultdict(lambda: defaultdict(list))
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            values[row["metric"]][row["profile"]].append((int(row["size"]), float(row["mean"])))
    for profiles in values.values():
        for points in profiles.values():
            points.sort()
    return values


def create_figures(summary_path: Path, output_dir: Path) -> list[Path]:
    matplotlib_config = PROJECT_ROOT / "instance" / "matplotlib"
    matplotlib_config.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_config))
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("Thiếu matplotlib. Hãy cài requirements-dev.txt.") from exc

    means = load_means(summary_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for metric, title, ylabel, filename in FIGURES:
        if metric not in means:
            continue
        figure, axis = plt.subplots(figsize=(7.2, 4.5))
        for profile in PROFILE_LABELS:
            points = means[metric].get(profile, [])
            if not points:
                continue
            axis.plot(
                [point[0] for point in points],
                [point[1] for point in points],
                marker="o",
                linewidth=2,
                label=PROFILE_LABELS[profile],
            )
        axis.set_title(title)
        axis.set_xlabel("Số hồ sơ")
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.3)
        axis.legend()
        figure.tight_layout()
        output_path = output_dir / filename
        figure.savefig(output_path, dpi=220, bbox_inches="tight")
        plt.close(figure)
        created.append(output_path)
    return created


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Tạo biểu đồ kết quả thực nghiệm.")
    parser.add_argument("--input", type=Path, help="Tệp summary_*.csv.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_FIGURE_DIR)
    args = parser.parse_args()
    summary_path = args.input or find_latest_summary(DEFAULT_RESULTS_DIR)
    for path in create_figures(summary_path, args.output_dir):
        print(f"Đã tạo: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
