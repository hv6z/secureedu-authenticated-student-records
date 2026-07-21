"""Tạo khóa bí mật cho môi trường phát triển cục bộ."""

from __future__ import annotations

import argparse
import base64
import secrets
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def build_env_content() -> str:
    aes_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    flask_secret = secrets.token_urlsafe(48)
    return (
        "# Tệp này chứa bí mật, không đưa lên kho mã nguồn.\n"
        f"AES_KEY={aes_key}\n"
        f"FLASK_SECRET_KEY={flask_secret}\n"
        "DATABASE_PATH=instance/student_records.db\n"
        "KEY_ID=key-v1\n"
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Tạo tệp .env chứa khóa bí mật.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ghi đè tệp .env hiện có. Dữ liệu cũ có thể không giải mã được.",
    )
    args = parser.parse_args()

    if ENV_PATH.exists() and not args.force:
        print("Tệp .env đã tồn tại. Không có thay đổi nào được thực hiện.")
        print("Chỉ dùng --force khi không cần giải mã cơ sở dữ liệu cũ.")
        return 1

    ENV_PATH.write_text(build_env_content(), encoding="utf-8")
    print(f"Đã tạo cấu hình bí mật tại: {ENV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
