// Turns the calendar_feed database function's answer into an iCalendar (.ics) file that Apple Calendar,
// Google Calendar and Outlook can subscribe to. Plain JavaScript with no imports, so the Edge Function (Deno)
// and the tests (Node) run the same code.
//
// Events keep the user's local times (TZID = their time zone), so a weekly 10 AM lecture stays at 10 AM
// across daylight-saving changes. Repeating events keep their rule (our rules are a small part of iCalendar's
// RRULE); X-SKIP (days with no class) becomes EXDATE. Tasks become all-day "Due: …" events on their due day.

const CRLF = "\r\n";
const encoder = new TextEncoder();
const SUPPORTED = new Set(["DAILY", "WEEKLY"]); // the app follows only these; other rules show the first day only

export function escapeText(text) {
  return String(text ?? "")
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\r?\n/g, "\\n");
}

// Lines longer than 75 bytes continue on the next line after a space (RFC 5545 3.1), never inside a character.
export function fold(line) {
  if (encoder.encode(line).length <= 75) return line;
  const pieces = [];
  let piece = "";
  let size = 0;
  for (const ch of line) {
    const n = encoder.encode(ch).length;
    const limit = pieces.length ? 74 : 75; // continuation lines start with a space
    if (size + n > limit) {
      pieces.push(piece);
      piece = "";
      size = 0;
    }
    piece += ch;
    size += n;
  }
  pieces.push(piece);
  return pieces.join(CRLF + " ");
}

const compactDay = (iso) => String(iso).slice(0, 10).replace(/-/g, ""); // "2026-10-05" -> "20261005"
const compactTime = (t) => String(t).slice(0, 8).replace(/:/g, "").padEnd(6, "0"); // "10:00:00" -> "100000"
const utcStamp = (date) => date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, ""); // "20261116T120000Z"

function nextDay(iso) {
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

// The UTC instant of a wall-clock time in a time zone (two passes over Intl's offset, enough for DST edges).
export function zonedToUtc(day, time, timeZone) {
  const [y, mo, d] = day.split("-").map(Number);
  const [h, mi, s] = time.split(":").map(Number);
  const wall = Date.UTC(y, mo - 1, d, h, mi, s || 0);
  const offsetAt = (instant) => {
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", {
      timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }).formatToParts(new Date(instant)).map((p) => [p.type, p.value]));
    const asUtc = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute, +parts.second);
    return asUtc - instant;
  };
  let instant = wall - offsetAt(wall);
  instant = wall - offsetAt(instant);
  return new Date(instant);
}

// Our rule -> an RRULE line's value and the skipped days. UNTIL is a date in our rules; iCalendar wants the
// last moment in UTC when the event has a time, so it becomes the end of that day in the user's time zone.
export function convertRule(rule, timeZone) {
  const parts = Object.fromEntries(
    String(rule).replace(/^RRULE:/, "").split(";").filter((p) => p.includes("=")).map((p) => p.split("=", 2)),
  );
  if (!SUPPORTED.has(parts.FREQ)) return null;
  const out = [`FREQ=${parts.FREQ}`];
  if (/^\d+$/.test(parts.INTERVAL ?? "")) out.push(`INTERVAL=${parts.INTERVAL}`);
  if (/^[A-Z0-9,+-]+$/.test(parts.BYDAY ?? "")) out.push(`BYDAY=${parts.BYDAY}`);
  if (/^\d+$/.test(parts.COUNT ?? "")) out.push(`COUNT=${parts.COUNT}`);
  if (/^\d{8}$/.test(parts.UNTIL ?? "")) {
    const day = `${parts.UNTIL.slice(0, 4)}-${parts.UNTIL.slice(4, 6)}-${parts.UNTIL.slice(6, 8)}`;
    out.push(`UNTIL=${utcStamp(zonedToUtc(day, "23:59:59", timeZone))}`);
  }
  const skip = (parts["X-SKIP"] ?? "").split(",").filter((d) => /^\d{8}$/.test(d));
  return { rrule: out.join(";"), skip };
}

function eventLines(event, timeZone, stamp) {
  const lines = [
    "BEGIN:VEVENT",
    `UID:event-${event.id}@steady-planner`,
    `DTSTAMP:${stamp}`,
    `SUMMARY:${escapeText(event.name)}`,
    `DTSTART;TZID=${timeZone}:${compactDay(event.start_date)}T${compactTime(event.start_time)}`,
    `DTEND;TZID=${timeZone}:${compactDay(event.end_date)}T${compactTime(event.end_time)}`,
  ];
  if (event.updated_at) lines.push(`LAST-MODIFIED:${utcStamp(new Date(event.updated_at))}`);
  const rule = event.recurrence_rule ? convertRule(event.recurrence_rule, timeZone) : null;
  if (rule) {
    lines.push(`RRULE:${rule.rrule}`);
    if (rule.skip.length) {
      lines.push(`EXDATE;TZID=${timeZone}:${rule.skip.map((d) => `${d}T${compactTime(event.start_time)}`).join(",")}`);
    }
  }
  if (event.changeable === false) lines.push("DESCRIPTION:Fixed in Steady: it never suggests moving this.");
  lines.push("END:VEVENT");
  return lines;
}

function taskLines(task, stamp) {
  const done = task.status === "COMPLETED";
  const lines = [
    "BEGIN:VEVENT",
    `UID:task-${task.id}@steady-planner`,
    `DTSTAMP:${stamp}`,
    `SUMMARY:${done ? "Done" : "Due"}: ${escapeText(task.name)}`,
    `DTSTART;VALUE=DATE:${compactDay(task.date)}`,
    `DTEND;VALUE=DATE:${compactDay(nextDay(task.date))}`,
    "TRANSP:TRANSPARENT", // a due date doesn't make the person busy all day
  ];
  if (task.updated_at) lines.push(`LAST-MODIFIED:${utcStamp(new Date(task.updated_at))}`);
  lines.push("END:VEVENT");
  return lines;
}

export function buildCalendar(feed, now = new Date()) {
  const timeZone = feed.timezone || "UTC";
  const stamp = utcStamp(now);
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Steady Planner//Calendar link//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "X-WR-CALNAME:Steady Planner",
    "X-WR-CALDESC:Your Steady Planner events and due dates",
    `X-WR-TIMEZONE:${timeZone}`,
    "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
    "X-PUBLISHED-TTL:PT1H",
    ...(feed.events ?? []).flatMap((e) => eventLines(e, timeZone, stamp)),
    ...(feed.tasks ?? []).flatMap((t) => taskLines(t, stamp)),
    "END:VCALENDAR",
  ];
  return lines.map(fold).join(CRLF) + CRLF;
}
