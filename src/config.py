"""Đọc và kiểm tra cấu hình chạy ứng dụng."""

from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigurationError(ValueError):
    """Cấu hình thiếu hoặc không hợp lệ."""


def _positive_integer_from_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} phải là số nguyên dương.") from exc
    if value < 1:
        raise ConfigurationError(f"{name} phải là số nguyên dương.")
    return value


def _boolean_from_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        f"{name} phải là một trong: true/false, 1/0, yes/no hoặc on/off."
    )


def load_env_file(path: Path | None = None) -> None:
    """Đọc tệp .env đơn giản mà không ghi đè biến môi trường hiện có."""

    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            os.environ.setdefault(name, value)


def decode_aes_key(encoded_key: str) -> bytes:
    """Giải mã khóa base64 và bắt buộc khóa AES-256 dài 32 byte."""

    try:
        key = base64.b64decode(encoded_key, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ConfigurationError("AES_KEY không phải chuỗi base64 hợp lệ.") from exc
    if len(key) != 32:
        raise ConfigurationError("AES_KEY phải biểu diễn đúng 32 byte.")
    return key


@dataclass(frozen=True, slots=True)
class Settings:
    """Cấu hình đã được kiểm tra."""

    database_path: Path
    encryption_key: bytes
    flask_secret_key: str
    audit_anchor_path: Path | None = None
    key_id: str = "key-v1"
    testing: bool = False
    session_lifetime_minutes: int = 30
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    session_cookie_secure: bool = False

    @classmethod
    def from_env(cls, *, testing: bool = False) -> "Settings":
        load_env_file()
        encoded_key = os.getenv("AES_KEY", "").strip()
        if not encoded_key:
            raise ConfigurationError(
                "Thiếu AES_KEY. Hãy chạy: python scripts/generate_key.py"
            )

        secret_key = os.getenv("FLASK_SECRET_KEY", "").strip()
        if not secret_key:
            raise ConfigurationError(
                "Thiếu FLASK_SECRET_KEY. Hãy chạy: python scripts/generate_key.py"
            )

        configured_path = Path(
            os.getenv("DATABASE_PATH", "instance/student_records.db")
        )
        database_path = (
            configured_path
            if configured_path.is_absolute()
            else PROJECT_ROOT / configured_path
        )
        configured_anchor = os.getenv("AUDIT_ANCHOR_PATH", "").strip()
        audit_anchor_path = None
        if configured_anchor:
            anchor_path = Path(configured_anchor)
            audit_anchor_path = (
                anchor_path
                if anchor_path.is_absolute()
                else PROJECT_ROOT / anchor_path
            )
        return cls(
            database_path=database_path,
            encryption_key=decode_aes_key(encoded_key),
            flask_secret_key=secret_key,
            audit_anchor_path=audit_anchor_path,
            key_id=os.getenv("KEY_ID", "key-v1").strip() or "key-v1",
            testing=testing,
            session_lifetime_minutes=_positive_integer_from_env(
                "SESSION_LIFETIME_MINUTES", 30
            ),
            login_max_attempts=_positive_integer_from_env(
                "LOGIN_MAX_ATTEMPTS", 5
            ),
            login_lockout_minutes=_positive_integer_from_env(
                "LOGIN_LOCKOUT_MINUTES", 15
            ),
            session_cookie_secure=_boolean_from_env(
                "SESSION_COOKIE_SECURE", False
            ),
        )

