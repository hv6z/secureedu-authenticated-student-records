"""Các trang quản lý hồ sơ, chuỗi kiểm toán và xác minh."""

from __future__ import annotations

from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from src.domain.student import ValidationError
from src.services.record_service import RecordService, RecordServiceError

from .access import current_user, roles_required


web = Blueprint("web", __name__)


def _service() -> RecordService:
    return current_app.extensions["record_service"]


def _actor_context() -> dict[str, str]:
    user = current_user()
    if user is None:  # Bảo vệ dự phòng; route đã được chặn ở app.before_request.
        abort(401)
    return {"actor_id": user.user_id, "actor_role": user.role}


def _student_from_form() -> dict[str, Any]:
    codes = request.form.getlist("course_code")
    names = request.form.getlist("course_name")
    scores = request.form.getlist("score")
    row_count = max(len(codes), len(names), len(scores), 0)
    courses: list[dict[str, Any]] = []

    for index in range(row_count):
        code = codes[index].strip() if index < len(codes) else ""
        name = names[index].strip() if index < len(names) else ""
        score = scores[index].strip() if index < len(scores) else ""
        if not code and not name and not score:
            continue
        course: dict[str, Any] = {"course_code": code, "score": score}
        if name:
            course["course_name"] = name
        courses.append(course)

    return {
        "student_code": request.form.get("student_code", ""),
        "full_name": request.form.get("full_name", ""),
        "date_of_birth": request.form.get("date_of_birth", ""),
        "program": request.form.get("program", ""),
        "courses": courses,
        "gpa": request.form.get("gpa", ""),
    }


def _friendly_error(error: Exception) -> str:
    message = str(error) or "Dữ liệu không hợp lệ."
    replacements = {
        "student_code": "mã sinh viên",
        "full_name": "họ và tên",
        "date_of_birth": "ngày sinh",
        "program": "chương trình học",
        "courses": "học phần",
        "course_code": "mã học phần",
        "course_name": "tên học phần",
        "score": "điểm",
        "gpa": "điểm trung bình",
        "expected_version": "phiên bản dự kiến",
    }
    for source, target in replacements.items():
        message = message.replace(source, target)
    return message


def _expected_version() -> int:
    raw = request.form.get("expected_version", "")
    if not raw:
        raise ValueError("Thiếu phiên bản hồ sơ. Hãy tải lại trang và thử lại.")
    return int(raw)


@web.get("/")
def dashboard():
    service = _service()
    students = service.list_students()
    blocks = service.list_blocks()
    report = service.verify_all()
    return render_template(
        "dashboard.html",
        student_count=len(students),
        block_count=max(len(blocks) - 1, 0),
        report=report,
        recent_students=list(reversed(students[-5:])),
        recent_blocks=list(reversed(blocks[-5:])),
    )


@web.get("/students")
def students():
    return render_template("students.html", students=_service().list_students())


@web.route("/students/new", methods=["GET", "POST"])
@roles_required("admin", "registrar")
def new_student():
    if request.method == "GET":
        return render_template(
            "student_form.html",
            student={"courses": [{}]},
            form_mode="create",
        )

    student = _student_from_form()
    try:
        created = _service().create_student(student, **_actor_context())
    except (ValidationError, RecordServiceError, ValueError, KeyError) as error:
        flash(_friendly_error(error), "error")
        return (
            render_template(
                "student_form.html", student=student, form_mode="create"
            ),
            400,
        )

    flash("Đã tạo và mã hóa hồ sơ sinh viên.", "success")
    return redirect(url_for("web.student_detail", record_id=created["_record_id"]))


@web.get("/students/<record_id>")
def student_detail(record_id: str):
    student = _service().get_student(record_id, include_deleted=True)
    if student is None:
        abort(404)
    report = _service().verify_student(record_id)
    return render_template(
        "student_detail.html", student=student, report=report
    )


@web.route("/students/<record_id>/edit", methods=["GET", "POST"])
@roles_required("admin", "registrar")
def edit_student(record_id: str):
    service = _service()
    current = service.get_student(record_id, include_deleted=True)
    if current is None:
        abort(404)
    if current["_status"] == "deleted":
        flash("Hồ sơ đã xóa không thể cập nhật.", "error")
        return redirect(url_for("web.student_detail", record_id=record_id))

    if request.method == "GET":
        return render_template(
            "student_form.html", student=current, form_mode="edit"
        )

    student = _student_from_form()
    student["_record_id"] = record_id
    student["_version"] = request.form.get("expected_version", "")
    try:
        updated = service.update_student(
            record_id,
            student,
            expected_version=_expected_version(),
            **_actor_context(),
        )
    except (ValidationError, RecordServiceError, ValueError, KeyError) as error:
        flash(_friendly_error(error), "error")
        return (
            render_template(
                "student_form.html", student=student, form_mode="edit"
            ),
            400,
        )

    flash("Đã lưu phiên bản hồ sơ mới.", "success")
    return redirect(url_for("web.student_detail", record_id=updated["_record_id"]))


@web.post("/students/<record_id>/delete")
@roles_required("admin", "registrar")
def delete_student(record_id: str):
    try:
        _service().delete_student(
            record_id,
            expected_version=_expected_version(),
            **_actor_context(),
        )
    except (RecordServiceError, ValueError, KeyError) as error:
        flash(_friendly_error(error), "error")
        return redirect(url_for("web.student_detail", record_id=record_id))
    flash("Đã xóa hồ sơ và ghi lại thao tác trong chuỗi kiểm toán.", "success")
    return redirect(url_for("web.students"))


@web.get("/blockchain")
def blockchain():
    return render_template("blockchain.html", blocks=_service().list_blocks())


@web.route("/verification", methods=["GET", "POST"])
def verification():
    service = _service()
    report = None
    selected_record_id = ""
    if request.method == "POST":
        selected_record_id = request.form.get("record_id", "").strip()
        try:
            report = (
                service.verify_student(selected_record_id)
                if selected_record_id
                else service.verify_all()
            )
        except (RecordServiceError, ValueError, KeyError) as error:
            flash(_friendly_error(error), "error")
    return render_template(
        "verification.html",
        report=report,
        students=service.list_students(include_deleted=True),
        selected_record_id=selected_record_id,
    )
