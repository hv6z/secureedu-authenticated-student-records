"""Kiểm thử đọc khóa và cấu hình môi trường."""

from __future__ import annotations

import base64

import pytest

from src.config import ConfigurationError, Settings, decode_aes_key, load_env_file


def test_decode_aes_key_accepts_exactly_32_bytes() -> None:
    key = b"k" * 32
    assert decode_aes_key(base64.b64encode(key).decode("ascii")) == key


@pytest.mark.parametrize("value", ["khong-phai-base64", base64.b64encode(b"short").decode("ascii")])
def test_decode_aes_key_rejects_invalid_value(value: str) -> None:
    with pytest.raises(ConfigurationError):
        decode_aes_key(value)


def test_load_env_file_does_not_override_existing_variable(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("EXISTING=from-file\nNEW_VALUE=from-file\n", encoding="utf-8")
    monkeypatch.setenv("EXISTING", "from-process")
    monkeypatch.delenv("NEW_VALUE", raising=False)

    load_env_file(env_path)

    assert __import__("os").environ["EXISTING"] == "from-process"
    assert __import__("os").environ["NEW_VALUE"] == "from-file"


def test_settings_from_env_resolves_relative_database(monkeypatch) -> None:
    monkeypatch.setenv("AES_KEY", base64.b64encode(b"z" * 32).decode("ascii"))
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_PATH", "instance/test.db")
    monkeypatch.setenv("KEY_ID", "test-key")
    monkeypatch.setenv("SESSION_LIFETIME_MINUTES", "45")
    monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("LOGIN_LOCKOUT_MINUTES", "20")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")

    settings = Settings.from_env(testing=True)

    assert settings.database_path.is_absolute()
    assert settings.database_path.name == "test.db"
    assert settings.encryption_key == b"z" * 32
    assert settings.flask_secret_key == "test-secret"
    assert settings.key_id == "test-key"
    assert settings.testing is True
    assert settings.session_lifetime_minutes == 45
    assert settings.login_max_attempts == 4
    assert settings.login_lockout_minutes == 20
    assert settings.session_cookie_secure is True


def test_settings_reject_invalid_session_configuration(monkeypatch) -> None:
    monkeypatch.setenv("AES_KEY", base64.b64encode(b"z" * 32).decode("ascii"))
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "0")

    with pytest.raises(ConfigurationError, match="LOGIN_MAX_ATTEMPTS"):
        Settings.from_env(testing=True)

