// Tests the calendar link's .ics file (supabase/functions/calendar-feed/ics.js): the format rules calendar apps
// rely on, and that an independent iCalendar parser (ical.js) reads back the same events and repeating days the
// app itself shows (Front-end/src/lib/recurrence.js).
import { test } from "node:test";
import assert from "node:assert/strict";
import ICAL from "ical.js";
import { buildCalendar, convertRule, escapeText, fold, zonedToUtc } from "../functions/calendar-feed/ics.js";
import { repeatDays } from "../../Front-end/src/lib/recurrence.js";

const NOW = new Date("2026-11-16T15:00:00Z");
const FEED = {
  timezone: "America/Detroit",
  events: [
    { id: 1, name: "CSE 232 lecture", start_date: "2026-10-05", start_time: "10:00:00", end_date: "2026-10-05",
      end_time: "11:20:00", recurrence_rule: "FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=20261204;X-SKIP=20261125,20261127",
      changeable: false, updated_at: "2026-11-10T12:00:00-05:00" },
    { id: 2, name: "Study, review; notes\nwith Sam", start_date: "2026-11-18", start_time: "19:00:00",
      end_date: "2026-11-18", end_time: "21:00:00", recurrence_rule: null, changeable: true },
    { id: 3, name: "Late shift", start_date: "2026-11-20", start_time: "22:00:00", end_date: "2026-11-21",
      end_time: "01:00:00", recurrence_rule: null, changeable: true },
    { id: 4, name: "Monthly meeting", start_date: "2026-11-03", start_time: "15:00:00", end_date: "2026-11-03",
      end_time: "16:00:00", recurrence_rule: "FREQ=MONTHLY;BYMONTHDAY=3", changeable: true },
  ],
  tasks: [
    { id: 7, name: "PHY 183 problem set", date: "2026-11-19", status: "IN_PROGRESS" },
    { id: 8, name: "Reading quiz", date: "2026-11-17", status: "COMPLETED" },
  ],
};
const ICS = buildCalendar(FEED, NOW);
const parsed = new ICAL.Component(ICAL.parse(ICS));
const events = parsed.getAllSubcomponents("vevent").map((v) => new ICAL.Event(v));
const byUid = Object.fromEntries(events.map((e) => [e.uid, e]));

test("every line ends with CRLF and is at most 75 bytes", () => {
  assert.ok(ICS.endsWith("\r\n"));
  for (const line of ICS.split("\r\n").slice(0, -1)) {
    assert.ok(new TextEncoder().encode(line).length <= 75, line);
  }
  assert.ok(!/[^\r]\n/.test(ICS), "a bare LF");
});

test("folding keeps every character, including ones that take several bytes", () => {
  const long = "SUMMARY:" + "Café ☕ study ".repeat(12);
  assert.equal(fold(long).replace(/\r\n /g, ""), long);
  for (const line of fold(long).split("\r\n")) assert.ok(new TextEncoder().encode(line).length <= 75);
});

test("text is escaped and reads back unchanged", () => {
  assert.equal(escapeText("a,b;c\\d\ne"), "a\\,b\\;c\\\\d\\ne");
  assert.equal(byUid["event-2@steady-planner"].summary, "Study, review; notes\nwith Sam");
});

test("events keep their local times in the user's time zone", () => {
  assert.match(ICS, /DTSTART;TZID=America\/Detroit:20261118T190000/);
  assert.match(ICS, /DTEND;TZID=America\/Detroit:20261121T010000/); // past midnight: ends the next day
  assert.match(ICS, /X-WR-TIMEZONE:America\/Detroit/);
});

test("a weekly class repeats on the same days as in the app, skipping days with no class", () => {
  const lecture = byUid["event-1@steady-planner"];
  assert.ok(lecture.isRecurring());
  const it = lecture.iterator();
  const fromIcs = [];
  for (let next = it.next(); next && fromIcs.length < 100; next = it.next()) fromIcs.push(next.toString().slice(0, 10));
  const fromApp = repeatDays("2026-10-05", FEED.events[0].recurrence_rule, "2026-12-31");
  assert.deepEqual(fromIcs, fromApp);
  assert.ok(!fromIcs.includes("2026-11-25") && !fromIcs.includes("2026-11-27"));
  assert.equal(fromIcs.at(-1), "2026-12-04"); // UNTIL: the last day still has its class
});

test("UNTIL becomes the end of that day in the user's time zone, in UTC", () => {
  assert.equal(convertRule("FREQ=WEEKLY;BYDAY=MO;UNTIL=20261204", "America/Detroit").rrule,
    "FREQ=WEEKLY;BYDAY=MO;UNTIL=20261205T045959Z"); // 11:59:59 PM EST = 04:59:59 UTC the next day
  assert.equal(convertRule("FREQ=WEEKLY;UNTIL=20260701", "America/Los_Angeles").rrule,
    "FREQ=WEEKLY;UNTIL=20260702T065959Z"); // PDT in summer
});

test("skipped days become EXDATE at the class's start time", () => {
  assert.match(ICS, /EXDATE;TZID=America\/Detroit:20261125T100000,20261127T100000/);
});

test("a rule the app can't follow is left out, so the event shows once, as in the app", () => {
  assert.equal(convertRule("FREQ=MONTHLY;BYMONTHDAY=3", "UTC"), null);
  assert.ok(!byUid["event-4@steady-planner"].isRecurring());
});

test("tasks are all-day entries on their due day, marked Due or Done, and don't make you busy", () => {
  const due = byUid["task-7@steady-planner"];
  assert.equal(due.summary, "Due: PHY 183 problem set");
  assert.ok(due.startDate.isDate);
  assert.equal(due.startDate.toString(), "2026-11-19");
  assert.equal(due.endDate.toString(), "2026-11-20");
  assert.equal(byUid["task-8@steady-planner"].summary, "Done: Reading quiz");
  assert.match(ICS, /TRANSP:TRANSPARENT/);
});

test("fixed events say so", () => {
  assert.match(byUid["event-1@steady-planner"].description, /never suggests moving/);
  assert.equal(byUid["event-2@steady-planner"].description, null);
});

test("local time to UTC across daylight saving time", () => {
  assert.equal(zonedToUtc("2026-07-01", "12:00:00", "America/Detroit").toISOString(), "2026-07-01T16:00:00.000Z");
  assert.equal(zonedToUtc("2026-12-01", "12:00:00", "America/Detroit").toISOString(), "2026-12-01T17:00:00.000Z");
  assert.equal(zonedToUtc("2026-11-16", "09:30:00", "Asia/Kolkata").toISOString(), "2026-11-16T04:00:00.000Z");
});

test("an empty calendar is still a valid calendar", () => {
  const empty = new ICAL.Component(ICAL.parse(buildCalendar({ timezone: "UTC", events: [], tasks: [] }, NOW)));
  assert.equal(empty.getAllSubcomponents("vevent").length, 0);
  assert.equal(empty.getFirstPropertyValue("x-wr-calname"), "Steady Planner");
});
