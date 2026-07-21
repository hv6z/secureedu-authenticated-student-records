"""Kiểm tra và chuẩn hóa miền dữ liệu hồ sơ sinh viên."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


class ValidationError(ValueError):
    """Dữ liệu hồ sơ không thỏa quy tắc miền."""


def normalize_student_code(value: str) -> str:
    """Chuẩn hóa Unicode, khoảng trắng và viết hoa mã sinh viên."""

    normalized = _normalize_required_text(value, "student_code")
    return normalized.upper()


def normalize_student_data(value: Mapping[str, Any]) -> dict[str, Any]:
    """Trả về hồ sơ chuẩn, sẵn sàng để tuần tự hóa JSON.

    Các trường ngoài lược đồ không được sao chép sang kết quả. Nhờ
    đó dữ liệu được mã hóa có lược đồ xác định.
    """

    if not isinstance(value, Mapping):
        raise ValidationError("Hồ sơ phải là một đối tượng ánh xạ.")

    student_code = normalize_student_code(_required(value, "student_code"))
    full_name = _normalize_required_text(_required(value, "full_name"), "full_name")
    date_of_birth = _normalize_birth_date(_required(value, "date_of_birth"))
    program = _normalize_required_text(_required(value, "program"), "program")
    courses = _normalize_courses(_required(value, "courses"))
    gpa = _normalize_mark(_required(value, "gpa"), "gpa")

    return {
        "student_code": student_code,
        "full_name": full_name,
        "date_of_birth": date_of_birth,
        "program": program,
        "courses": courses,
        "gpa": gpa,
    }


def _required(value: Mapping[str, Any], field: str) -> Any:
    if field not in value:
        raise ValidationError(f"Thiếu trường bắt buộc: {field}.")
    return value[field]


def _normalize_required_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} phải là chuỗi.")
    # NFKC gom các biến thể tương đương như chữ full-width. split()
    # nhận biết cả các dạng khoảng trắng Unicode.
    normalized = unicodedata.normalize("NFKC", value)
    normalized = " ".join(normalized.split())
    if not normalized:
        raise ValidationError(f"{field} không được rỗng.")
    return normalized


def _normalize_birth_date(value: object) -> str:
    if isinstance(value, datetime):
        raise ValidationError("date_of_birth phải là ngày, không kèm giờ.")
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise ValidationError("date_of_birth phải là chuỗi ISO YYYY-MM-DD.")

    text = _normalize_required_text(value, "date_of_birth")
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(
            "date_of_birth phải là ngày ISO hợp lệ theo dạng YYYY-MM-DD."
        ) from exc
    if parsed.isoformat() != text:
        raise ValidationError("date_of_birth phải theo đúng dạng YYYY-MM-DD.")
    return parsed.isoformat()


def _normalize_courses(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValidationError("courses phải là danh sách.")
    if not value:
        raise ValidationError("courses không được rỗng.")

    normalized_courses: list[dict[str, Any]] = []
    for index, course in enumerate(value):
        path = f"courses[{index}]"
        if not isinstance(course, Mapping):
            raise ValidationError(f"{path} phải là một đối tượng ánh xạ.")
        if "course_code" not in course:
            raise ValidationError(f"Thiếu trường bắt buộc: {path}.course_code.")
        if "score" not in course:
            raise ValidationError(f"Thiếu trường bắt buộc: {path}.score.")

        normalized_course: dict[str, Any] = {
            "course_code": _normalize_required_text(
                course["course_code"], f"{path}.course_code"
            ).upper(),
        }
        if "course_name" in course:
            normalized_course["course_name"] = _normalize_required_text(
                course["course_name"], f"{path}.course_name"
            )
        normalized_course["score"] = _normalize_mark(
            course["score"], f"{path}.score"
        )
        normalized_courses.append(normalized_course)
    return normalized_courses


def _normalize_mark(value: object, field: str) -> int | float:
    if isinstance(value, bool) or value is None:
        raise ValidationError(f"{field} phải là số từ 0 đến 10.")
    if isinstance(value, str):
        value = unicodedata.normalize("NFKC", value).strip()
        if not value:
            raise ValidationError(f"{field} không được rỗng.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"{field} phải là số từ 0 đến 10.") from exc
    if not number.is_finite() or number < 0 or number > 10:
        raise ValidationError(f"{field} phải là số từ 0 đến 10.")

    if number == number.to_integral_value():
        return int(number)
    result = float(number)
    if not math.isfinite(result):
        raise ValidationError(f"{field} phải là số hữu hạn.")
    return result
