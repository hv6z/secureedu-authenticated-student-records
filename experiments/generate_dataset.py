"""Sinh tập hồ sơ mô phỏng có thể tái lập."""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "experiments" / "datasets"

FAMILY_NAMES = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi"]
MIDDLE_NAMES = ["Văn", "Thị", "Minh", "Hoài", "Quốc", "Thanh", "Hải", "Ngọc"]
GIVEN_NAMES = ["An", "Bình", "Chi", "Dũng", "Hà", "Khánh", "Linh", "Nam", "Phương", "Trang"]
PROGRAMS = [
    "An toàn thông tin",
    "Công nghệ thông tin",
    "Khoa học máy tính",
    "Hệ thống thông tin",
]
COURSES = [
    ("MMH01", "Mật mã học"),
    ("ATDL01", "An toàn dữ liệu"),
    ("CSDL01", "Cơ sở dữ liệu"),
    ("LTM01", "Lập trình mạng"),
    ("CTDL01", "Cấu trúc dữ liệu"),
]


def generate_records(size: int, seed: int = 2026) -> list[dict[str, object]]:
    if size < 1:
        raise ValueError("Kích thước phải lớn hơn 0.")

    generator = random.Random(seed)
    first_birth_date = date(2001, 1, 1)
    records: list[dict[str, object]] = []
    for index in range(1, size + 1):
        course_count = generator.randint(1, 4)
        selected_courses = generator.sample(COURSES, k=course_count)
        courses = []
        for course_code, course_name in selected_courses:
            score = round(generator.uniform(5.0, 10.0), 2)
            courses.append(
                {
                    "course_code": course_code,
                    "course_name": course_name,
                    "score": score,
                }
            )
        gpa = round(sum(item["score"] for item in courses) / len(courses), 2)
        birth_date = first_birth_date + timedelta(days=generator.randint(0, 2200))
        records.append(
            {
                "student_code": f"SV{index:07d}",
                "full_name": " ".join(
                    [
                        generator.choice(FAMILY_NAMES),
                        generator.choice(MIDDLE_NAMES),
                        generator.choice(GIVEN_NAMES),
                    ]
                ),
                "date_of_birth": birth_date.isoformat(),
                "program": generator.choice(PROGRAMS),
                "courses": courses,
                "gpa": gpa,
            }
        )
    return records


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Sinh dữ liệu hồ sơ sinh viên mô phỏng.")
    parser.add_argument("--size", type=int, required=True, help="Số hồ sơ cần sinh.")
    parser.add_argument("--seed", type=int, default=2026, help="Giá trị hạt giống.")
    parser.add_argument("--output", type=Path, help="Đường dẫn tệp JSON đầu ra.")
    args = parser.parse_args()

    records = generate_records(args.size, args.seed)
    output_path = args.output or DEFAULT_OUTPUT_DIR / f"students_{args.size}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Đã tạo {len(records)} hồ sơ tại: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
