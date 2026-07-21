"""Xác thực tài khoản cục bộ và phân quyền theo vai trò."""

from .service import (
    ALLOWED_ROLES,
    AuthenticationResult,
    AuthenticationService,
    AuthenticationServiceError,
    DuplicateUsernameError,
    StoredUser,
)

__all__ = [
    "ALLOWED_ROLES",
    "AuthenticationResult",
    "AuthenticationService",
    "AuthenticationServiceError",
    "DuplicateUsernameError",
    "StoredUser",
]
