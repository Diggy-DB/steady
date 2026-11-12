import { addEvent, saveProfile } from "./data";

// Sign-up collects the profile and fixed commitments; they're saved right after the account is created
// (the account first, then preferences, as before). If Supabase asks the person to confirm their email
// first, there's no session yet, so they wait in this browser and are saved at the first log-in.

export const PRIORITY_OPTIONS = [
  "Hanging out with friends", "Sleeping", "Studying", "Exercise", "Gaming", "Reading", "Working", "Personal time",
];
export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];
const PENDING_KEY = "steady-onboarding";

const pad = (n) => String(n).padStart(2, "0");
const isoDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

// "10:00" -> "10:00 AM"
export function clockText(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return `${h % 12 || 12}:${pad(m)} ${h < 12 ? "AM" : "PM"}`;
}

export function describeCommitment(c) {
  return `${c.days.map((d) => WEEKDAYS[d]).join(", ")} · ${clockText(c.start)} – ${clockText(c.end)}`;
}

// A fixed commitment as a calendar row: a weekly repeating event the AI may never move (changeable: false),
// starting on the next day it happens (today included).
export function commitmentToEvent({ name, days, start, end }) {
  const first = new Date();
  while (!days.includes((first.getDay() + 6) % 7)) first.setDate(first.getDate() + 1);
  return {
    name: name.trim(),
    start_date: isoDay(first),
    start_time: start,
    end_date: isoDay(first),
    end_time: end,
    recurrence_rule: `FREQ=WEEKLY;BYDAY=${[...days].sort().map((d) => CODES[d]).join(",")}`,
    changeable: false,
    created_by: "USER",
  };
}

// A saved weekly fixed event back as a commitment (for the Settings list).
export function eventToCommitment(row) {
  const byday = /BYDAY=([A-Z,]+)/.exec(row.recurrence_rule ?? "")?.[1] ?? "";
  return {
    id: row.event_id,
    name: row.name,
    days: byday.split(",").map((c) => CODES.indexOf(c)).filter((d) => d >= 0),
    start: row.start_time.slice(0, 5),
    end: row.end_time.slice(0, 5),
  };
}

export async function applyOnboarding(userId, onboarding) {
  await saveProfile(userId, {
    preferred_work_time: onboarding.workTime,
    priorities: onboarding.priorities,
    additional_information: onboarding.motivation.trim().slice(0, 1000),
    timezone: onboarding.timezone,
  });
  for (const c of onboarding.commitments) await addEvent(commitmentToEvent(c));
}

export function savePending(email, onboarding) {
  try {
    localStorage.setItem(PENDING_KEY, JSON.stringify({ email: email.toLowerCase(), onboarding }));
  } catch {
    // storage blocked: they can fill these in from Settings
  }
}

// The onboarding waiting for this email, if any (and forget it).
export function takePending(email) {
  try {
    const saved = JSON.parse(localStorage.getItem(PENDING_KEY) || "null");
    if (saved && saved.email === (email || "").toLowerCase()) {
      localStorage.removeItem(PENDING_KEY);
      return saved.onboarding;
    }
  } catch {
    // nothing to apply
  }
  return null;
}
