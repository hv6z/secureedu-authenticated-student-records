from __future__ import annotations

from datetime import date

import pytest

from src.domain import ValidationError, normalize_student_code, normalize_student_data


def valid_record() -> dict:
    return {
        "student_code": " sv  001 ",
        "full_name": "  Nguyễn   Hải  An ",
        "date_of_birth": "2005-06-12",
        "program": "  An toàn   thông tin ",
        "courses": [
            {
                "course_code": " attt  01 ",
                "course_name": " Nhập môn   mật mã ",
                "score": "8.5",
            },
            {"course_code": "cs02", "score": 10},
        ],
        "gpa": 9.25,
    }


def test_normalize_student_code_handles_unicode_spaces_and_case() -> None:
    assert normalize_student_code("  sv\u00a0\u00a0001 ") == "SV 001"
    assert normalize_student_code("ｓｖ００２") == "SV002"


def test_normalize_full_record() -> None:
    source = valid_record()
    source["ignored_form_field"] = "not encrypted"

    result = normalize_student_data(source)

    assert result == {
        "student_code": "SV 001",
        "full_name": "Nguyễn Hải An",
        "date_of_birth": "2005-06-12",
        "program": "An toàn thông tin",
        "courses": [
            {
                "course_code": "ATTT 01",
                "course_name": "Nhập môn mật mã",
                "score": 8.5,
            },
            {"course_code": "CS02", "score": 10},
        ],
        "gpa": 9.25,
    }
    assert "ignored_form_field" not in result


def test_date_object_is_normalized_to_iso() -> None:
    record = valid_record()
    record["date_of_birth"] = date(2004, 2, 29)
    assert normalize_student_data(record)["date_of_birth"] == "2004-02-29"


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("student_code", " \t "),
        ("full_name", ""),
        ("date_of_birth", "2005-02-29"),
        ("date_of_birth", "20050612"),
        ("program", None),
        ("courses", []),
        ("courses", "not-a-list"),
        ("gpa", -0.1),
        ("gpa", 10.1),
        ("gpa", float("nan")),
        ("gpa", True),
    ],
)
def test_invalid_top_level_fields_raise_validation_error(
    field: str, bad_value: object
) -> None:
    record = valid_record()
    record[field] = bad_value

    with pytest.raises(ValidationError):
        normalize_student_data(record)


def test_missing_required_field_raises_validation_error() -> None:
    record = valid_record()
    del record["program"]

    with pytest.raises(ValidationError, match="program"):
        normalize_student_data(record)


@pytest.mark.parametrize(
    "course",
    [
        {},
        {"course_code": "CS01", "score": -1},
        {"course_code": "CS01", "score": 11},
        {"course_code": "", "score": 8},
        {"course_code": "CS01", "course_name": " ", "score": 8},
        {"course_code": "CS01", "score": False},
    ],
)
def test_invalid_course_raises_validation_error(course: dict) -> None:
    record = valid_record()
    record["courses"] = [course]

    with pytest.raises(ValidationError, match=r"courses\[0\]"):
        normalize_student_data(record)
