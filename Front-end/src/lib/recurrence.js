// Repeating events: the calendar_events.recurrence_rule column, read the same way as the AI does
// (ai/src/ai/recurrence.py). A rule is a small part of iCalendar's RRULE, e.g.
// "FREQ=WEEKLY;BYDAY=TU,TH;UNTIL=20270430;X-SKIP=20270309,20270311" (X-SKIP: days with no class).

const WEEKDAYS = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"]; // JavaScript's getDay() order
const LIMIT = 1000;

const toDate = (text) => new Date(Number(text.slice(0, 4)), Number(text.slice(4, 6)) - 1, Number(text.slice(6, 8)));
const pad = (n) => String(n).padStart(2, "0");
export const isoDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const fromIso = (text) => new Date(Number(text.slice(0, 4)), Number(text.slice(5, 7)) - 1, Number(text.slice(8, 10)));

export function parseRule(rule) {
  const parts = Object.fromEntries(
    rule.replace(/^RRULE:/, "").split(";").filter((p) => p.includes("=")).map((p) => p.split("=", 2)),
  );
  if (!["DAILY", "WEEKLY"].includes(parts.FREQ)) return null; // a rule we can't follow: show the first day only
  return {
    freq: parts.FREQ,
    interval: Math.max(1, Number(parts.INTERVAL ?? 1)),
    days: parts.BYDAY ? parts.BYDAY.split(",").map((d) => WEEKDAYS.indexOf(d.slice(-2))) : [],
    until: parts.UNTIL ? toDate(parts.UNTIL) : null,
    count: parts.COUNT ? Number(parts.COUNT) : null,
    skip: new Set((parts["X-SKIP"] ?? "").split(",").filter(Boolean).map((d) => isoDay(toDate(d)))),
  };
}

// Every day ("YYYY-MM-DD") the event happens, from its first day through `last` ("YYYY-MM-DD").
export function repeatDays(firstDay, rule, last) {
  const r = parseRule(rule);
  if (!r) return [firstDay];
  const first = fromIso(firstDay);
  const weekdays = r.days.length ? r.days : [first.getDay()];
  const lastDate = r.until && r.until < fromIso(last) ? r.until : fromIso(last);
  const mondayOffset = (first.getDay() + 6) % 7;
  const weekStart = new Date(first.getFullYear(), first.getMonth(), first.getDate() - mondayOffset);
  const found = [];
  let counted = 0;
  for (let d = new Date(first); d <= lastDate && counted < LIMIT; d.setDate(d.getDate() + 1)) {
    if (r.count !== null && counted >= r.count) break;
    const daysIn = Math.round((d - first) / 86400000);
    const weeksIn = Math.floor(Math.round((d - weekStart) / 86400000) / 7);
    const happens = r.freq === "DAILY" ? daysIn % r.interval === 0 : weekdays.includes(d.getDay()) && weeksIn % r.interval === 0;
    if (happens) {
      counted += 1;
      if (!r.skip.has(isoDay(d))) found.push(isoDay(d));
    }
  }
  return found;
}

// A repeating event's copies for each day it happens between two days (inclusive), as rows like the
// database's. Each copy keeps the series' event_id, so deleting one deletes the series.
export function expandEvent(row, firstDay, lastDay) {
  if (!row.recurrence_rule) return [row];
  return repeatDays(row.start_date, row.recurrence_rule, lastDay)
    .filter((day) => day >= firstDay)
    .map((day) => ({ ...row, start_date: day, end_date: day, repeats: true }));
}

// "Tue/Thu until Apr 30" for a rule, for cards and the day view.
export function describeRule(rule) {
  const r = parseRule(rule);
  if (!r) return "Repeats";
  const names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const days = r.freq === "DAILY" ? "Every day" : r.days.length ? r.days.map((d) => names[d]).join("/") : "Weekly";
  const until = r.until ? ` until ${r.until.toLocaleDateString([], { month: "short", day: "numeric" })}` : "";
  const skips = r.skip.size ? `, except ${[...r.skip].map((d) => fromIso(d).toLocaleDateString([], { month: "short", day: "numeric" })).join(", ")}` : "";
  return `${days}${until}${skips}`;
}
