"""Khởi tạo ứng dụng Flask và các lớp bảo vệ dùng chung."""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from flask import Flask, abort, g, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.auth import AuthenticationService
from src.config import Settings
from src.services.record_service import RecordService

from .access import can_manage_records


def create_app(settings: Settings | None = None) -> Flask:
    """Tạo ứng dụng và nối giao diện với dịch vụ hồ sơ duy nhất."""

    resolved = settings or Settings.from_env()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_mapping(
        SECRET_KEY=resolved.flask_secret_key,
        TESTING=resolved.testing,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=resolved.session_cookie_secure,
        SESSION_COOKIE_NAME="secure_student_record_session",
        PERMANENT_SESSION_LIFETIME=timedelta(
            minutes=resolved.session_lifetime_minutes
        ),
        SESSION_REFRESH_EACH_REQUEST=True,
        MAX_CONTENT_LENGTH=1_000_000,
    )

    service = RecordService(
        resolved.database_path,
        resolved.encryption_key,
        key_id=resolved.key_id,
        audit_anchor_path=resolved.audit_anchor_path,
    )
    service.initialize()
    app.extensions["record_service"] = service

    authentication_service = AuthenticationService(
        resolved.database_path,
        max_attempts=resolved.login_max_attempts,
        lockout_minutes=resolved.login_lockout_minutes,
    )
    authentication_service.initialize()
    app.extensions["authentication_service"] = authentication_service

    @app.context_processor
    def add_template_helpers() -> dict[str, Any]:
        return {
            "csrf_token": _csrf_token,
            "login_csrf_token": lambda: _login_csrf_token(
                resolved.flask_secret_key
            ),
            "operation_label": _operation_label,
            "current_user": getattr(g, "current_user", None),
            "can_manage_records": can_manage_records,
            "role_label": _role_label,
        }

    @app.before_request
    def load_and_require_user():
        user_id = session.get("user_id")
        user = (
            authentication_service.get_user(user_id)
            if isinstance(user_id, str)
            else None
        )
        if user is not None and not user.is_active:
            user = None
        g.current_user = user

        if request.endpoint in {"auth.login", "static"}:
            return None
        if user is None:
            session.clear()
            next_url = request.full_path.rstrip("?")
            return redirect(url_for("auth.login", next=next_url))
        return None

    @app.before_request
    def protect_post_requests() -> None:
        if request.method != "POST":
            return
        supplied = request.form.get("csrf_token", "")
        if request.endpoint == "auth.login":
            if not _is_valid_login_csrf_token(
                supplied,
                resolved.flask_secret_key,
                max_age_seconds=resolved.session_lifetime_minutes * 60,
            ):
                abort(
                    400,
                    description="Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Vui lòng tải lại trang.",
                )
            return
        expected = session.get("_csrf_token")
        if (
            not isinstance(expected, str)
            or not isinstance(supplied, str)
            or not expected
            or not secrets.compare_digest(expected, supplied)
        ):
            abort(400, description="Phiên biểu mẫu không hợp lệ hoặc đã hết hạn.")

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; form-action 'self'; frame-ancestors 'self'",
        )
        if getattr(g, "current_user", None) is not None:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    from .auth import auth
    from .routes import web

    app.register_blueprint(auth)
    app.register_blueprint(web)

    @app.errorhandler(400)
    def bad_request(error):
        return (
            render_template(
                "error.html",
                status_code=400,
                title="Yêu cầu không hợp lệ",
                message=getattr(error, "description", "Không thể xử lý yêu cầu."),
            ),
            400,
        )

    @app.errorhandler(404)
    def not_found(_error):
        return (
            render_template(
                "error.html",
                status_code=404,
                title="Không tìm thấy nội dung",
                message="Nội dung bạn yêu cầu không tồn tại hoặc đã được chuyển đi.",
            ),
            404,
        )

    @app.errorhandler(403)
    def forbidden(error):
        return (
            render_template(
                "error.html",
                status_code=403,
                title="Không đủ quyền",
                message=getattr(
                    error,
                    "description",
                    "Tài khoản không có quyền thực hiện thao tác này.",
                ),
            ),
            403,
        )

    @app.errorhandler(500)
    def internal_error(_error):
        return (
            render_template(
                "error.html",
                status_code=500,
                title="Không thể hoàn tất yêu cầu",
                message="Hệ thống gặp lỗi ngoài dự kiến. Dữ liệu chưa được thay đổi.",
            ),
            500,
        )

    return app


def _csrf_token() -> str:
    token = session.get("_csrf_token")
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _login_csrf_token(secret_key: str) -> str:
    serializer = URLSafeTimedSerializer(secret_key, salt="login-csrf-v1")
    return serializer.dumps(
        {"purpose": "login", "nonce": secrets.token_urlsafe(16)}
    )


def _is_valid_login_csrf_token(
    token: str,
    secret_key: str,
    *,
    max_age_seconds: int,
) -> bool:
    if not isinstance(token, str) or not token:
        return False
    serializer = URLSafeTimedSerializer(secret_key, salt="login-csrf-v1")
    try:
        payload = serializer.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(payload, dict) and payload.get("purpose") == "login"


def _operation_label(operation: str) -> str:
    return {
        "GENESIS": "Khởi nguyên",
        "CREATE": "Tạo hồ sơ",
        "UPDATE": "Cập nhật",
        "DELETE": "Xóa hồ sơ",
    }.get(operation, operation)


def _role_label(role: str) -> str:
    return {
        "admin": "Quản trị viên",
        "registrar": "Cán bộ học vụ",
        "auditor": "Kiểm toán viên",
        "system": "Tiến trình hệ thống",
    }.get(role, role)
