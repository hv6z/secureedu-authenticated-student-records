"""Khởi tạo lược đồ cơ sở dữ liệu và khối đầu tiên."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings  # noqa: E402
from src.services.record_service import RecordService  # noqa: E402


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
    print(f"Đã khởi tạo cơ sở dữ liệu: {settings.database_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
