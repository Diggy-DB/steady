import { useCallback, useEffect, useState } from "react";

// Light / dark theme: "steady-theme" in localStorage, otherwise the system setting. index.html sets
// data-theme on <html> before the first paint (no flash); this keeps it in sync after that.
const KEY = "steady-theme";

export function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

export function useTheme() {
  const [theme, setThemeState] = useState(currentTheme);

  const setTheme = useCallback((next) => {
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // storage blocked: the theme still applies for this visit
    }
    setThemeState(next);
    window.dispatchEvent(new CustomEvent("steady-theme", { detail: next }));
  }, []);

  // Several toggles (header, settings) share the one theme.
  useEffect(() => {
    const sync = (e) => setThemeState(e.detail);
    window.addEventListener("steady-theme", sync);
    return () => window.removeEventListener("steady-theme", sync);
  }, []);

  return [theme, setTheme];
}
