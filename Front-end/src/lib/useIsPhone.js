import { useEffect, useState } from "react";

// Phones (under 768px) get their own layout: one column and a bottom sheet for the selected day.
const QUERY = "(max-width: 767px)";

export function useIsPhone() {
  const [phone, setPhone] = useState(() => window.matchMedia(QUERY).matches);
  useEffect(() => {
    const list = window.matchMedia(QUERY);
    const update = () => setPhone(list.matches);
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, []);
  return phone;
}
