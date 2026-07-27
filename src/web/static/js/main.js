"use strict";

const navToggle = document.querySelector(".nav-toggle");
const navigation = document.querySelector(".main-nav");

function setNavigationOpen(open) {
  if (!navToggle || !navigation) return;
  navigation.classList.toggle("open", open);
  navToggle.setAttribute("aria-expanded", String(open));
}

if (navToggle && navigation) {
  navToggle.addEventListener("click", () => {
    setNavigationOpen(!navigation.classList.contains("open"));
  });
  navigation.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => setNavigationOpen(false));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setNavigationOpen(false);
      navToggle.focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (!navigation.contains(event.target) && !navToggle.contains(event.target)) {
      setNavigationOpen(false);
    }
  });
}

document.querySelectorAll(".flash").forEach((flash) => {
  flash.querySelector(".flash-close")?.addEventListener("click", () => flash.remove());
  window.setTimeout(() => flash.remove(), 5000);
});

const errorFlash = document.querySelector(".flash-error");
if (errorFlash) {
  errorFlash.setAttribute("tabindex", "-1");
  errorFlash.focus();
}

document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm || "Bạn có chắc muốn tiếp tục?")) {
      event.preventDefault();
    }
  });
});

document.querySelectorAll("[data-loading-form]").forEach((form) => {
  form.addEventListener("submit", () => {
    if (!form.checkValidity()) return;
    const button = form.querySelector('button[type="submit"]');
    if (!button) return;
    const label = button.querySelector("span") || button;
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
    label.textContent = button.dataset.submitLabel || "Đang xử lý…";
  });
});

const passwordToggle = document.querySelector(".password-toggle");
if (passwordToggle) {
  const passwordInput = document.getElementById(passwordToggle.getAttribute("aria-controls"));
  passwordToggle.addEventListener("click", () => {
    if (!passwordInput) return;
    const showing = passwordInput.type === "text";
    passwordInput.type = showing ? "password" : "text";
    passwordToggle.setAttribute("aria-label", showing ? "Hiện mật khẩu" : "Ẩn mật khẩu");
  });
}

const courseList = document.querySelector("[data-course-list]");
const courseTemplate = document.querySelector("#course-row-template");
const addCourseButton = document.querySelector("[data-add-course]");

function renumberCourses() {
  if (!courseList) return;
  courseList.querySelectorAll(".course-row").forEach((row, index) => {
    const label = row.querySelector(".course-index");
    if (label) {
      label.textContent = String(index + 1);
      label.setAttribute("aria-label", `Học phần số ${index + 1}`);
    }
  });
}

if (courseList) {
  courseList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-course]");
    if (!button) return;
    const rows = courseList.querySelectorAll(".course-row");
    const row = button.closest(".course-row");
    if (!row) return;
    if (rows.length === 1) {
      row.querySelectorAll("input").forEach((input) => { input.value = ""; });
      row.querySelector("input")?.focus();
    } else {
      const nextFocus = row.previousElementSibling?.querySelector("input") || addCourseButton;
      row.remove();
      renumberCourses();
      nextFocus?.focus();
    }
  });
}

if (addCourseButton && courseList && courseTemplate) {
  addCourseButton.addEventListener("click", () => {
    const fragment = courseTemplate.content.cloneNode(true);
    courseList.appendChild(fragment);
    renumberCourses();
    courseList.lastElementChild?.querySelector("input")?.focus();
  });
}

const searchInput = document.querySelector("[data-table-search]");
const searchTable = document.querySelector("[data-search-table]");
const noResults = document.querySelector(".no-search-results");
const resultCount = document.querySelector("[data-result-count]");

if (searchInput && searchTable) {
  searchInput.addEventListener("input", () => {
    const query = searchInput.value.trim().toLocaleLowerCase("vi");
    let visible = 0;
    searchTable.querySelectorAll("tbody tr").forEach((row) => {
      const match = row.textContent.toLocaleLowerCase("vi").includes(query);
      row.hidden = !match;
      if (match) visible += 1;
    });
    if (noResults) noResults.hidden = visible !== 0;
    if (resultCount) resultCount.textContent = String(visible);
  });
}
