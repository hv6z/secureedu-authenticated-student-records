"""Kiểm thử các luồng web quan trọng và mã chống giả mạo biểu mẫu."""

from __future__ import annotations

import re

import pytest

from src.config import Settings
from src.web.app import create_app


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        database_path=tmp_path / "web.db",
        encryption_key=b"w" * 32,
        flask_secret_key="khoa-phien-kiem-thu",
        key_id="test-key",
        testing=True,
    )
    application = create_app(settings)
    authentication = application.extensions["authentication_service"]
    authentication.create_user(
        "admin",
        "Mat-khau-quan-tri-2026",
        "admin",
    )
    authentication.create_user(
        "auditor",
        "Mat-khau-kiem-toan-2026",
        "auditor",
    )
    return application


@pytest.fixture
def client(app):
    client = app.test_client()
    _login(client, "admin", "Mat-khau-quan-tri-2026")
    return client


@pytest.fixture
def anonymous_client(app):
    return app.test_client()


@pytest.fixture
def auditor_client(app):
    client = app.test_client()
    _login(client, "auditor", "Mat-khau-kiem-toan-2026")
    return client


def _token_from_response(response) -> str:
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    assert match is not None
    return match.group(1).decode("ascii")


def _login(client, username: str, password: str):
    login_page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": _token_from_response(login_page),
            "username": username,
            "password": password,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    return response


def _csrf_token(client) -> str:
    response = client.get("/students/new")
    return _token_from_response(response)


def _student_form(csrf_token: str | None = None) -> dict:
    data = {
        "student_code": "SV001",
        "full_name": "Nguyễn Văn An",
        "date_of_birth": "2004-05-20",
        "program": "An toàn thông tin",
        "course_code": "MMH101",
        "course_name": "Mật mã học",
        "score": "8.5",
        "gpa": "8.5",
    }
    if csrf_token is not None:
        data["csrf_token"] = csrf_token
    return data


@pytest.mark.parametrize(
    "path", ["/", "/students", "/students/new", "/blockchain", "/verification"]
)
def test_main_pages_are_available(client, path) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert b"SecureEdu Audit Ledger" in response.data
    assert b'data-theme-toggle' in response.data
    assert b'/static/js/theme.js' in response.data
    assert b'content="light dark"' in response.data


def test_audit_page_surfaces_hmac_and_checkpoint_status(client, app) -> None:
    response = client.get("/blockchain")
    block_mac = app.extensions["record_service"].list_blocks()[0]["block_mac"]

    assert response.status_code == 200
    assert b"Block HMAC" in response.data
    assert "Đã đối chiếu".encode("utf-8") in response.data
    assert block_mac.encode("ascii") in response.data


def test_anonymous_user_is_redirected_to_login(anonymous_client) -> None:
    response = anonymous_client.get("/students", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login?next=")


def test_invalid_login_is_rejected(anonymous_client) -> None:
    login_page = anonymous_client.get("/login")
    response = anonymous_client.post(
        "/login",
        data={
            "csrf_token": _token_from_response(login_page),
            "username": "admin",
            "password": "sai-mat-khau",
        },
    )
    assert response.status_code == 401
    assert "không đúng".encode("utf-8") in response.data


def test_login_csrf_token_does_not_depend_on_prelogin_cookie(app) -> None:
    page_client = app.test_client()
    login_page = page_client.get("/login")
    token = _token_from_response(login_page)

    fresh_client = app.test_client()
    response = fresh_client.post(
        "/login",
        data={
            "csrf_token": token,
            "username": "admin",
            "password": "Mat-khau-quan-tri-2026",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_login_without_csrf_is_rejected(anonymous_client) -> None:
    response = anonymous_client.post(
        "/login",
        data={"username": "admin", "password": "Mat-khau-quan-tri-2026"},
    )
    assert response.status_code == 400


def test_login_does_not_redirect_to_external_site(anonymous_client) -> None:
    login_page = anonymous_client.get("/login?next=https://example.com/steal")
    response = anonymous_client.post(
        "/login",
        data={
            "csrf_token": _token_from_response(login_page),
            "next": "https://example.com/steal",
            "username": "admin",
            "password": "Mat-khau-quan-tri-2026",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_post_without_csrf_is_rejected(client) -> None:
    response = client.post("/students/new", data=_student_form())
    assert response.status_code == 400
    assert "Phiên biểu mẫu không hợp lệ".encode("utf-8") in response.data


def test_create_student_then_view_detail(client) -> None:
    response = client.post(
        "/students/new",
        data=_student_form(_csrf_token(client)),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Nguyễn Văn An".encode("utf-8") in response.data
    assert "MMH101".encode("utf-8") in response.data
    assert "Dữ liệu toàn vẹn".encode("utf-8") in response.data

    listing = client.get("/students")
    assert "SV001".encode("utf-8") in listing.data


def test_web_write_records_authenticated_actor(client, app) -> None:
    response = client.post(
        "/students/new",
        data=_student_form(_csrf_token(client)),
        follow_redirects=False,
    )
    assert response.status_code == 302

    admin = app.extensions["authentication_service"].get_user_by_username("admin")
    block = app.extensions["record_service"].list_blocks()[-1]
    assert admin is not None
    assert block["actor_id"] == admin.user_id
    assert block["actor_role"] == "admin"
    assert block["block_schema_version"] == 3


def test_create_update_verify_and_delete_student(client) -> None:
    created = client.post(
        "/students/new",
        data=_student_form(_csrf_token(client)),
        follow_redirects=False,
    )
    assert created.status_code == 302
    detail_path = created.headers["Location"]
    record_id = detail_path.rstrip("/").split("/")[-1]

    changed = _student_form(_csrf_token(client))
    changed.update(
        {
            "full_name": "Nguyễn Văn An đã cập nhật",
            "gpa": "9.0",
            "expected_version": "1",
        }
    )
    updated = client.post(
        f"/students/{record_id}/edit",
        data=changed,
        follow_redirects=True,
    )
    assert updated.status_code == 200
    assert "Nguyễn Văn An đã cập nhật".encode("utf-8") in updated.data

    verified = client.post(
        "/verification",
        data={"csrf_token": _csrf_token(client), "record_id": record_id},
    )
    assert verified.status_code == 200
    assert "Dữ liệu toàn vẹn".encode("utf-8") in verified.data

    deleted = client.post(
        f"/students/{record_id}/delete",
        data={"csrf_token": _csrf_token(client), "expected_version": "2"},
        follow_redirects=True,
    )
    assert deleted.status_code == 200
    assert "SV001".encode("utf-8") not in deleted.data

    detail = client.get(detail_path)
    assert detail.status_code == 200
    assert "Đã xóa".encode("utf-8") in detail.data


def test_security_headers_are_present(client) -> None:
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


def test_auditor_can_read_but_cannot_modify(auditor_client) -> None:
    listing = auditor_client.get("/students")
    assert listing.status_code == 200
    assert "Thêm sinh viên".encode("utf-8") not in listing.data

    create_page = auditor_client.get("/students/new")
    assert create_page.status_code == 403
    assert "Không đủ quyền".encode("utf-8") in create_page.data


def test_logout_ends_session(client) -> None:
    page = client.get("/")
    response = client.post(
        "/logout",
        data={"csrf_token": _token_from_response(page)},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert client.get("/", follow_redirects=False).status_code == 302
