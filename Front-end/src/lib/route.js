import { useEffect, useState } from "react";

// A tiny hash router: #/login, #/signup, #/settings, and #/ for home. Hash routes work on GitHub Pages
// without any server setup, and pages link to each other with plain <a href="#/settings">.
// Anything else in the hash (for example tokens Supabase adds after an email link) counts as home.
const ROUTES = ["login", "signup", "settings"];

function read() {
  const name = window.location.hash.replace(/^#\/?/, "").split(/[?&/]/)[0];
  return ROUTES.includes(name) ? name : "home";
}

export function useRoute() {
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const update = () => {
      setRoute(read());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}

export function go(route) {
  window.location.hash = route === "home" ? "#/" : `#/${route}`;
}
