"""Thêm một số hồ sơ minh họa để kiểm tra giao diện."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings  # noqa: E402
from src.services.record_service import RecordService  # noqa: E402


DEMO_RECORDS = [
    {
        "student_code": "SV001",
        "full_name": "Nguyễn Minh An",
        "date_of_birth": "2004-03-12",
        "program": "An toàn thông tin",
        "courses": [
            {"course_code": "ATTT01", "course_name": "Mật mã học", "score": 8.7},
            {"course_code": "CSDL01", "course_name": "Cơ sở dữ liệu", "score": 8.2},
        ],
        "gpa": 8.45,
    },
    {
        "student_code": "SV002",
        "full_name": "Trần Hoài Nam",
        "date_of_birth": "2003-11-24",
        "program": "Công nghệ thông tin",
        "courses": [
            {"course_code": "LTM01", "course_name": "Lập trình mạng", "score": 7.9}
        ],
        "gpa": 7.9,
    },
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    settings = Settings.from_env()
    service = RecordService(
        settings.database_path,
        settings.encryption_key,
        key_id=settings.key_id,
    )
    service.initialize()
    created = 0
    for record in DEMO_RECORDS:
        try:
            service.create_student(record)
            created += 1
        except ValueError as exc:
            print(f"Bỏ qua {record['student_code']}: {exc}")
    print(f"Đã thêm {created} hồ sơ minh họa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
