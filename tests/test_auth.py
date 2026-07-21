"""Kiểm thử password hashing, khóa đăng nhập và quản trị tài khoản."""

from __future__ import annotations

import sqlite3

import pytest

from src.auth import AuthenticationService, DuplicateUsernameError


@pytest.fixture
def service(tmp_path) -> AuthenticationService:
    value = AuthenticationService(
        tmp_path / "auth.db",
        max_attempts=3,
        lockout_minutes=10,
    )
    value.initialize()
    return value


def test_create_authenticate_and_store_only_password_hash(service) -> None:
    created = service.create_user(
        "Registrar.One",
        "Mat-khau-hoc-vu-2026",
        "registrar",
    )
    assert created.username == "registrar.one"
    assert created.role == "registrar"

    result = service.authenticate("REGISTRAR.ONE", "Mat-khau-hoc-vu-2026")
    assert result.authenticated is True
    assert result.user is not None
    assert result.user.last_login_at is not None

    connection = sqlite3.connect(service.database_path)
    try:
        password_hash = connection.execute(
            "SELECT password_hash FROM users WHERE user_id = ?",
            (created.user_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    assert password_hash != "Mat-khau-hoc-vu-2026"
    assert "Mat-khau-hoc-vu-2026" not in password_hash


def test_duplicate_username_is_case_insensitive(service) -> None:
    service.create_user("admin", "Mat-khau-admin-2026", "admin")
    with pytest.raises(DuplicateUsernameError):
        service.create_user("ADMIN", "Mat-khau-khac-2026", "admin")


def test_failed_attempts_lock_account(service) -> None:
    user = service.create_user("auditor", "Mat-khau-auditor-2026", "auditor")
    assert service.authenticate("auditor", "sai-1").status == "invalid_credentials"
    assert service.authenticate("auditor", "sai-2").status == "invalid_credentials"
    assert service.authenticate("auditor", "sai-3").status == "locked"
    assert service.authenticate("auditor", "Mat-khau-auditor-2026").status == "locked"

    stored = service.get_user(user.user_id)
    assert stored is not None
    assert stored.failed_attempts == 3
    assert stored.locked_until is not None


def test_disable_role_and_password_management(service) -> None:
    user = service.create_user("operator", "Mat-khau-operator-2026", "registrar")
    service.set_role(user.user_id, "auditor")
    service.set_password(user.user_id, "Mat-khau-moi-operator-2026")
    service.set_active(user.user_id, False)

    updated = service.get_user(user.user_id)
    assert updated is not None
    assert updated.role == "auditor"
    assert updated.is_active is False
    assert service.authenticate("operator", "Mat-khau-moi-operator-2026").status == "disabled"


@pytest.mark.parametrize(
    "username,password,role",
    [
        ("x", "Mat-khau-hop-le-2026", "admin"),
        ("valid-user", "ngan", "admin"),
        ("valid-user", "Mat-khau-hop-le-2026", "superuser"),
    ],
)
def test_invalid_user_input_is_rejected(service, username, password, role) -> None:
    with pytest.raises((TypeError, ValueError)):
        service.create_user(username, password, role)
