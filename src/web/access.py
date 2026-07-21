"""Các kiểm tra phân quyền dùng chung cho route và template."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar, cast

from flask import abort, g

from src.auth import StoredUser


MANAGE_RECORD_ROLES = frozenset({"admin", "registrar"})
ALL_APPLICATION_ROLES = frozenset({"admin", "registrar", "auditor"})

F = TypeVar("F", bound=Callable[..., Any])


def current_user() -> StoredUser | None:
    user = getattr(g, "current_user", None)
    return user if isinstance(user, StoredUser) else None


def can_manage_records(user: StoredUser | None = None) -> bool:
    selected = user or current_user()
    return selected is not None and selected.role in MANAGE_RECORD_ROLES


def roles_required(*roles: str) -> Callable[[F], F]:
    allowed = frozenset(roles)
    if not allowed or not allowed.issubset(ALL_APPLICATION_ROLES):
        raise ValueError("Danh sách vai trò phân quyền không hợp lệ.")

    def decorator(view: F) -> F:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            user = current_user()
            if user is None:
                abort(401)
            if user.role not in allowed:
                abort(403, description="Tài khoản không có quyền thực hiện thao tác này.")
            return view(*args, **kwargs)

        return cast(F, wrapped)

    return decorator
