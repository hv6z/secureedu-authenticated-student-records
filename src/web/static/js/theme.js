"use strict";

(() => {
  const storageKey = "secureedu-theme";
  const root = document.documentElement;
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  const themeColors = { light: "#1e3a5f", dark: "#08111f" };

  function readPreference() {
    try {
      const value = window.localStorage.getItem(storageKey);
      return value === "light" || value === "dark" ? value : null;
    } catch {
      return null;
    }
  }

  function savePreference(theme) {
    try {
      window.localStorage.setItem(storageKey, theme);
    } catch {
      // Giao diện vẫn hoạt động khi trình duyệt chặn bộ nhớ cục bộ.
    }
  }

  function updateThemeColor(theme) {
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", themeColors[theme]);
  }

  function updateControls(theme) {
    const nextTheme = theme === "dark" ? "light" : "dark";
    const label = nextTheme === "dark" ? "Chuyển sang giao diện tối" : "Chuyển sang giao diện sáng";
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
      button.setAttribute("aria-pressed", String(theme === "dark"));
      const text = button.querySelector("[data-theme-label]");
      if (text) text.textContent = label;
    });
  }

  function applyTheme(theme, animate = false) {
    if (animate) root.classList.add("theme-changing");
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    updateThemeColor(theme);
    updateControls(theme);
    if (animate) window.setTimeout(() => root.classList.remove("theme-changing"), 240);
  }

  applyTheme(readPreference() || (systemTheme.matches ? "dark" : "light"));

  document.addEventListener("DOMContentLoaded", () => {
    updateControls(root.dataset.theme);
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const nextTheme = root.dataset.theme === "dark" ? "light" : "dark";
        savePreference(nextTheme);
        applyTheme(nextTheme, true);
      });
    });
  });

  const syncSystemTheme = (event) => {
    if (!readPreference()) applyTheme(event.matches ? "dark" : "light", true);
  };
  if (systemTheme.addEventListener) systemTheme.addEventListener("change", syncSystemTheme);
  else systemTheme.addListener(syncSystemTheme);
})();
