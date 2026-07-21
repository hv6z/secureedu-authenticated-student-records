"use strict";

const navToggle = document.querySelector(".nav-toggle");
const navigation = document.querySelector(".main-nav");
if (navToggle && navigation) {
  navToggle.addEventListener("click", () => {
    const open = navigation.classList.toggle("open");
    navToggle.setAttribute("aria-expanded", String(open));
  });
}

document.querySelectorAll(".flash-close").forEach((button) => {
  button.addEventListener("click", () => button.closest(".flash")?.remove());
});

document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm || "Bạn có chắc muốn tiếp tục?")) {
      event.preventDefault();
    }
  });
});

const courseList = document.querySelector("[data-course-list]");
const courseTemplate = document.querySelector("#course-row-template");
const addCourseButton = document.querySelector("[data-add-course]");

function renumberCourses() {
  if (!courseList) return;
  courseList.querySelectorAll(".course-row").forEach((row, index) => {
    const label = row.querySelector(".course-index");
    if (label) label.textContent = String(index + 1);
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
    } else {
      row.remove();
      renumberCourses();
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
  });
}
