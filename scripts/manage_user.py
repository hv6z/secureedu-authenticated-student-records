"""Tạo và quản lý tài khoản cục bộ mà không ghi mật khẩu vào lịch sử lệnh."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import ALLOWED_ROLES, AuthenticationService  # noqa: E402
from src.config import Settings  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quản lý tài khoản ứng dụng.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Tạo tài khoản mới.")
    create.add_argument("--username")
    create.add_argument("--role", choices=sorted(ALLOWED_ROLES), default="admin")

    subparsers.add_parser("list", help="Liệt kê tài khoản, không hiện password hash.")

    password = subparsers.add_parser("password", help="Đặt lại mật khẩu.")
    password.add_argument("username")

    role = subparsers.add_parser("role", help="Đổi vai trò.")
    role.add_argument("username")
    role.add_argument("role", choices=sorted(ALLOWED_ROLES))

    enable = subparsers.add_parser("enable", help="Kích hoạt tài khoản.")
    enable.add_argument("username")

    disable = subparsers.add_parser("disable", help="Vô hiệu hóa tài khoản.")
    disable.add_argument("username")
    return parser


def _read_password() -> str:
    password = getpass.getpass("Mật khẩu mới: ")
    confirmation = getpass.getpass("Nhập lại mật khẩu: ")
    if password != confirmation:
        raise ValueError("Hai lần nhập mật khẩu không khớp.")
    return password


def _require_user(service: AuthenticationService, username: str):
    user = service.get_user_by_username(username)
    if user is None:
        raise ValueError(f"Không tìm thấy tài khoản: {username}.")
    return user


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    settings = Settings.from_env()
    service = AuthenticationService(
        settings.database_path,
        max_attempts=settings.login_max_attempts,
        lockout_minutes=settings.login_lockout_minutes,
    )
    service.initialize()

    if args.command == "create":
        username = args.username or input("Tên đăng nhập: ").strip()
        user = service.create_user(username, _read_password(), args.role)
        print(f"Đã tạo {user.username} với vai trò {user.role}.")
        return 0

    if args.command == "list":
        users = service.list_users()
        if not users:
            print("Chưa có tài khoản.")
            return 0
        print(f"{'USERNAME':<24} {'ROLE':<12} {'ACTIVE':<8} LAST LOGIN")
        for user in users:
            print(
                f"{user.username:<24} {user.role:<12} "
                f"{('yes' if user.is_active else 'no'):<8} "
                f"{user.last_login_at or '-'}"
            )
        return 0

    user = _require_user(service, args.username)
    if args.command == "password":
        service.set_password(user.user_id, _read_password())
        print(f"Đã đổi mật khẩu cho {user.username}.")
    elif args.command == "role":
        service.set_role(user.user_id, args.role)
        print(f"Đã đổi vai trò {user.username} thành {args.role}.")
    elif args.command == "enable":
        service.set_active(user.user_id, True)
        print(f"Đã kích hoạt {user.username}.")
    elif args.command == "disable":
        service.set_active(user.user_id, False)
        print(f"Đã vô hiệu hóa {user.username}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
