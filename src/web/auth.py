"""Trang đăng nhập và kết thúc phiên."""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from src.auth import AuthenticationService


auth = Blueprint("auth", __name__)


def _authentication_service() -> AuthenticationService:
    return current_app.extensions["authentication_service"]


def _safe_next_url(value: str) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    if parsed.path.startswith("//"):
        return None
    return value


@auth.route("/login", methods=["GET", "POST"])
def login():
    if getattr(g, "current_user", None) is not None:
        return redirect(url_for("web.dashboard"))

    next_url = _safe_next_url(request.values.get("next", ""))
    if request.method == "GET":
        return render_template("login.html", next_url=next_url or "")

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    result = _authentication_service().authenticate(username, password)
    if result.authenticated:
        assert result.user is not None
        session.clear()
        session.permanent = True
        session["user_id"] = result.user.user_id
        session["username"] = result.user.username
        session["role"] = result.user.role
        flash(f"Đăng nhập thành công: {result.user.username}.", "success")
        return redirect(next_url or url_for("web.dashboard"))

    if result.status == "locked":
        message = "Tài khoản đang bị khóa tạm thời do đăng nhập sai nhiều lần."
    elif result.status == "disabled":
        message = "Tài khoản đã bị vô hiệu hóa."
    else:
        message = "Tên đăng nhập hoặc mật khẩu không đúng."
    flash(message, "error")
    return render_template(
        "login.html",
        next_url=next_url or "",
        username=username.strip(),
    ), 401


@auth.post("/logout")
def logout():
    session.clear()
    flash("Đã kết thúc phiên đăng nhập.", "success")
    return redirect(url_for("auth.login"))
