"""Dịch vụ tài khoản cục bộ, password hashing và khóa đăng nhập tạm thời."""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from src.database.connection import connect_database, immediate_transaction
from src.database.schema import initialize_database


ALLOWED_ROLES = frozenset({"admin", "registrar", "auditor"})
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,63}$")
MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 256
_DUMMY_PASSWORD_HASH = generate_password_hash(
    "chuoi-gia-lap-khong-dung-de-dang-nhap",
    method="scrypt",
)


class AuthenticationServiceError(RuntimeError):
    """Lỗi cơ sở của dịch vụ xác thực."""


class DuplicateUsernameError(AuthenticationServiceError):
    """Tên đăng nhập đã tồn tại."""


@dataclass(frozen=True, slots=True)
class StoredUser:
    user_id: str
    username: str
    role: str
    is_active: bool
    failed_attempts: int
    locked_until: str | None
    last_login_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    user: StoredUser | None
    status: str

    @property
    def authenticated(self) -> bool:
        return self.user is not None and self.status == "authenticated"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_username(username: str) -> str:
    if not isinstance(username, str):
        raise TypeError("username phải là chuỗi.")
    normalized = username.strip().casefold()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Tên đăng nhập phải dài 3-64 ký tự, bắt đầu bằng chữ hoặc số và "
            "chỉ gồm a-z, 0-9, dấu chấm, gạch dưới hoặc gạch ngang."
        )
    return normalized


def validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise TypeError("Mật khẩu phải là chuỗi.")
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError(
            f"Mật khẩu phải có ít nhất {MINIMUM_PASSWORD_LENGTH} ký tự."
        )
    if len(password) > MAXIMUM_PASSWORD_LENGTH:
        raise ValueError(
            f"Mật khẩu không được vượt quá {MAXIMUM_PASSWORD_LENGTH} ký tự."
        )
    if password.isspace():
        raise ValueError("Mật khẩu không được chỉ gồm khoảng trắng.")


def validate_role(role: str) -> str:
    if not isinstance(role, str):
        raise TypeError("Vai trò phải là chuỗi.")
    normalized = role.strip().casefold()
    if normalized not in ALLOWED_ROLES:
        raise ValueError(
            "Vai trò phải là một trong: admin, registrar hoặc auditor."
        )
    return normalized


def _user_from_row(row: sqlite3.Row | None) -> StoredUser | None:
    if row is None:
        return None
    return StoredUser(
        user_id=str(row["user_id"]),
        username=str(row["username"]),
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
        failed_attempts=int(row["failed_attempts"]),
        locked_until=row["locked_until"],
        last_login_at=row["last_login_at"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class AuthenticationService:
    """Quản lý tài khoản trong cùng SQLite với ứng dụng."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        max_attempts: int = 5,
        lockout_minutes: int = 15,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts phải lớn hơn 0.")
        if lockout_minutes < 1:
            raise ValueError("lockout_minutes phải lớn hơn 0.")
        self.database_path = Path(database_path)
        self.max_attempts = max_attempts
        self.lockout_minutes = lockout_minutes

    def initialize(self) -> None:
        initialize_database(self.database_path)

    def create_user(
        self,
        username: str,
        password: str,
        role: str,
        *,
        is_active: bool = True,
    ) -> StoredUser:
        normalized_username = normalize_username(username)
        normalized_role = validate_role(role)
        validate_password(password)
        now = _timestamp(_utc_now())
        user_id = str(uuid.uuid4())
        password_hash = generate_password_hash(password, method="scrypt")

        connection = connect_database(self.database_path)
        try:
            with immediate_transaction(connection):
                connection.execute(
                    """
                    INSERT INTO users (
                        user_id, username, password_hash, role, is_active,
                        failed_attempts, locked_until, last_login_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 0, NULL, NULL, ?, ?)
                    """,
                    (
                        user_id,
                        normalized_username,
                        password_hash,
                        normalized_role,
                        int(is_active),
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateUsernameError("Tên đăng nhập đã tồn tại.") from exc
        finally:
            connection.close()

        user = self.get_user(user_id)
        if user is None:  # pragma: no cover - bảo vệ trạng thái SQLite bất thường.
            raise AuthenticationServiceError("Không thể đọc lại tài khoản vừa tạo.")
        return user

    def get_user(self, user_id: str) -> StoredUser | None:
        if not isinstance(user_id, str) or not user_id:
            return None
        connection = connect_database(self.database_path)
        try:
            row = connection.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return _user_from_row(row)
        finally:
            connection.close()

    def get_user_by_username(self, username: str) -> StoredUser | None:
        try:
            normalized = normalize_username(username)
        except (TypeError, ValueError):
            return None
        connection = connect_database(self.database_path)
        try:
            row = connection.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                (normalized,),
            ).fetchone()
            return _user_from_row(row)
        finally:
            connection.close()

    def list_users(self) -> list[StoredUser]:
        connection = connect_database(self.database_path)
        try:
            rows = connection.execute(
                "SELECT * FROM users ORDER BY username"
            ).fetchall()
            return [_user_from_row(row) for row in rows]  # type: ignore[misc]
        finally:
            connection.close()

    def authenticate(self, username: str, password: str) -> AuthenticationResult:
        if not isinstance(password, str):
            password = ""
        try:
            normalized = normalize_username(username)
        except (TypeError, ValueError):
            check_password_hash(_DUMMY_PASSWORD_HASH, password)
            return AuthenticationResult(None, "invalid_credentials")

        now = _utc_now()
        now_text = _timestamp(now)
        connection = connect_database(self.database_path)
        try:
            with immediate_transaction(connection):
                row = connection.execute(
                    "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                    (normalized,),
                ).fetchone()
                if row is None:
                    check_password_hash(_DUMMY_PASSWORD_HASH, password)
                    return AuthenticationResult(None, "invalid_credentials")

                user = _user_from_row(row)
                assert user is not None
                if not user.is_active:
                    return AuthenticationResult(None, "disabled")

                locked_until = _parse_timestamp(user.locked_until)
                if locked_until is not None and locked_until > now:
                    return AuthenticationResult(None, "locked")

                if not check_password_hash(str(row["password_hash"]), password):
                    attempts = user.failed_attempts + 1
                    new_locked_until: str | None = None
                    status = "invalid_credentials"
                    if attempts >= self.max_attempts:
                        new_locked_until = _timestamp(
                            now + timedelta(minutes=self.lockout_minutes)
                        )
                        status = "locked"
                    connection.execute(
                        """
                        UPDATE users
                        SET failed_attempts = ?, locked_until = ?, updated_at = ?
                        WHERE user_id = ?
                        """,
                        (attempts, new_locked_until, now_text, user.user_id),
                    )
                    return AuthenticationResult(None, status)

                connection.execute(
                    """
                    UPDATE users
                    SET failed_attempts = 0, locked_until = NULL,
                        last_login_at = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (now_text, now_text, user.user_id),
                )
        finally:
            connection.close()

        authenticated = self.get_user(user.user_id)
        return AuthenticationResult(authenticated, "authenticated")

    def set_password(self, user_id: str, password: str) -> None:
        validate_password(password)
        password_hash = generate_password_hash(password, method="scrypt")
        now = _timestamp(_utc_now())
        self._update_user(
            user_id,
            """
            password_hash = ?, failed_attempts = 0, locked_until = NULL,
            updated_at = ?
            """,
            (password_hash, now),
        )

    def set_role(self, user_id: str, role: str) -> None:
        normalized = validate_role(role)
        self._update_user(
            user_id,
            "role = ?, updated_at = ?",
            (normalized, _timestamp(_utc_now())),
        )

    def set_active(self, user_id: str, active: bool) -> None:
        self._update_user(
            user_id,
            """
            is_active = ?, failed_attempts = 0, locked_until = NULL,
            updated_at = ?
            """,
            (int(active), _timestamp(_utc_now())),
        )

    def _update_user(
        self,
        user_id: str,
        assignments: str,
        values: tuple[object, ...],
    ) -> None:
        connection = connect_database(self.database_path)
        try:
            with immediate_transaction(connection):
                cursor = connection.execute(
                    f"UPDATE users SET {assignments} WHERE user_id = ?",
                    (*values, user_id),
                )
                if cursor.rowcount != 1:
                    raise AuthenticationServiceError("Không tìm thấy tài khoản.")
        finally:
            connection.close()
