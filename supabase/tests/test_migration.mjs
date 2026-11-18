// Tests the Steady Planner migration in a throwaway Postgres (PGlite) that mimics Supabase:
// the auth schema, auth.uid(), the anon/authenticated roles and their default grants,
// plus the team's three draft tables exactly as they exist in the live project.
import { readFileSync } from "node:fs";
import { PGlite } from "@electric-sql/pglite";

// All migration files given on the command line, applied in order.
const MIGRATION = process.argv.slice(2).map((file) => readFileSync(file, "utf8")).join("\n");
let failures = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  (" + detail + ")" : ""}`);
  if (!ok) failures++;
}

const SUPABASE_LIKE = `
  create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;
  create role supabase_auth_admin nologin;  -- the role Supabase Auth uses to add users
  create schema auth;
  create table auth.users (id uuid primary key, email text, raw_user_meta_data jsonb default '{}');
  grant usage on schema auth to supabase_auth_admin; grant insert on auth.users to supabase_auth_admin;
  create function auth.uid() returns uuid language sql stable as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
  grant usage on schema public, auth to anon, authenticated, service_role;
  grant execute on function auth.uid() to anon, authenticated;
  -- Supabase grants table access to these roles by default; RLS is what restricts them.
  alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
  alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
`;

// The live project's draft tables (from information_schema, Oct 15).
const DRAFTS = `
  create type public.active_hours as enum ('Morning', 'Night');
  create table public."Users" (id bigint primary key, created_at timestamptz not null default now(),
    first_name text not null default '', last_name text not null default '',
    email_address text not null default '' unique, password text not null default '');
  create table public."Events" (id bigint primary key, created_at timestamptz not null default now(),
    created_by bigint not null references public."Users"(id), title text not null, description text);
  create table public."Personalization" (id bigint primary key references public."Users"(id),
    created_at timestamptz not null default now(), hobbies text, priorities text,
    preferred_work_time public.active_hours not null default 'Morning', additional_information text[]);
  alter table public."Users" enable row level security;
  alter table public."Events" enable row level security;
  alter table public."Personalization" enable row level security;
`;

const A = "11111111-1111-1111-1111-111111111111";
const B = "22222222-2222-2222-2222-222222222222";

async function as(db, user, sql, params = []) {
  // Run one statement as a signed-in user, like a request carrying their access token.
  await db.exec(`set role authenticated; select set_config('request.jwt.claim.sub', '${user}', false);`);
  try {
    return await db.query(sql, params);
  } finally {
    await db.exec(`reset role; select set_config('request.jwt.claim.sub', '', false);`);
  }
}
async function fails(promise) {
  try { await promise; return false; } catch { return true; }
}

// ---- 1. The safety check refuses to drop drafts that hold data ----
{
  const db = new PGlite();
  await db.exec(SUPABASE_LIKE + DRAFTS);
  await db.exec(`insert into public."Users"(id, email_address) values (1, 'x@example.com')`);
  let message = "";
  try { await db.exec(MIGRATION); } catch (e) { message = e.message; }
  const usersStillThere = (await db.query(`select count(*)::int as n from public."Users"`)).rows[0].n === 1;
  check("refuses to drop a draft table that has rows", message.includes("not dropping") && usersStillThere, message);
}

// ---- 2. The real run, on empty drafts like the live project ----
const db = new PGlite();
await db.exec(SUPABASE_LIKE + DRAFTS);
await db.exec(MIGRATION);
const tables = (await db.query(`select string_agg(tablename, ', ' order by tablename) as t from pg_tables where schemaname = 'public'`)).rows[0].t;
const planned = process.argv.length > 8  // the seventh migration adds calendar_imports
  ? "activity_log, ai_suggestions, calendar_events, calendar_feeds, calendar_imports, daily_overviews, journals, tasks, users"
  : process.argv.length > 7  // the sixth migration adds calendar_feeds
  ? "activity_log, ai_suggestions, calendar_events, calendar_feeds, daily_overviews, journals, tasks, users"
  : process.argv.length > 5  // the fourth migration adds daily_overviews
    ? "activity_log, ai_suggestions, calendar_events, daily_overviews, journals, tasks, users"
    : "activity_log, ai_suggestions, calendar_events, journals, tasks, users";
check("drafts replaced by the planned tables", tables === planned, tables);

// Sign-up creates the profile. Insert as Supabase Auth's own role, not as a superuser.
await db.exec(`set role supabase_auth_admin`);
await db.exec(`insert into auth.users (id, email, raw_user_meta_data) values
  ('${A}', 'alex@example.com', '{"first_name": "Alex", "last_name": "Kim", "timezone": "America/Chicago"}'),
  ('${B}', 'sam@example.com', '{"timezone": "Mars/Base"}')`);
await db.exec(`reset role`);
const profiles = (await db.query(`select user_id, first_name, timezone from public.users order by email`)).rows;
check("sign-up creates a profile with name and time zone", profiles[0].first_name === "Alex" && profiles[0].timezone === "America/Chicago");
check("an unknown time zone at sign-up falls back to America/Detroit", profiles[1].timezone === "America/Detroit");

// Events: own rows only.
const ev = await as(db, A, `insert into public.calendar_events (name, start_date, start_time, end_date, end_time, changeable)
  values ('CSE 232 lecture', '2026-10-19', '10:00', '2026-10-19', '12:00', false) returning event_id, user_id`);
const eventId = ev.rows[0].event_id;
check("user_id defaults to the signed-in user", ev.rows[0].user_id === A);
check("the owner sees their event", (await as(db, A, `select * from public.calendar_events`)).rows.length === 1);
check("another user sees nothing", (await as(db, B, `select * from public.calendar_events`)).rows.length === 0);
const moved = await as(db, B, `update public.calendar_events set start_time = '13:00' where event_id = $1`, [eventId]);
check("another user can't change it", moved.affectedRows === 0);
check("another user can't delete it", (await as(db, B, `delete from public.calendar_events where event_id = $1`, [eventId])).affectedRows === 0);
check("can't create an event in someone else's name",
  await fails(as(db, B, `insert into public.calendar_events (user_id, name, start_date, start_time, end_date, end_time)
    values ('${A}', 'Sneaky', '2026-10-19', '13:00', '2026-10-19', '14:00')`)));
check("an event must end after it starts",
  await fails(as(db, A, `insert into public.calendar_events (name, start_date, start_time, end_date, end_time)
    values ('Backwards', '2026-10-19', '15:00', '2026-10-19', '14:00')`)));
check("an event may run past midnight",
  !(await fails(as(db, A, `insert into public.calendar_events (name, start_date, start_time, end_date, end_time)
    values ('Late study', '2026-10-19', '22:00', '2026-10-20', '00:30')`))));

// Tasks and journal.
await as(db, A, `insert into public.tasks (name, description, date) values ('PHY 183 problem set', 'About 3 hours of work.', '2026-10-22')`);
check("tasks are private", (await as(db, B, `select * from public.tasks`)).rows.length === 0);
check("task status must be one of the three", await fails(as(db, A, `update public.tasks set status = 'DONE'`)));
await as(db, A, `insert into public.journals (date, information) values ('2026-10-19', 'Good day.')`);
check("one journal entry per day", await fails(as(db, A, `insert into public.journals (date, information) values ('2026-10-19', 'Again')`)));
check("journals are private", (await as(db, B, `select * from public.journals`)).rows.length === 0);

// Suggestions: add, answer, never delete.
const sg = await as(db, A, `insert into public.ai_suggestions (type, target_id, description, proposed_change, depends_on)
  values ('MOVE_EVENT', $1, 'Later start', '{"start": "2026-10-19T13:00:00-05:00", "end": "2026-10-19T15:00:00-05:00"}', '[]')
  returning suggestion_id, status`, [eventId]);
check("the AI can add a suggestion with the user's token", sg.rows[0].status === "PENDING");
const sid = sg.rows[0].suggestion_id;
check("the user can answer it", (await as(db, A, `update public.ai_suggestions set status = 'ACCEPTED' where suggestion_id = $1`, [sid])).affectedRows === 1);
check("suggestions can't be deleted through the API", (await as(db, A, `delete from public.ai_suggestions where suggestion_id = $1`, [sid])).affectedRows === 0);
check("another user can't see it", (await as(db, B, `select * from public.ai_suggestions`)).rows.length === 0);
check("a move needs a target event", await fails(as(db, A, `insert into public.ai_suggestions (type, proposed_change) values ('MOVE_EVENT', '{}')`)));

// Task suggestions (third migration): a deadline from a syllabus becomes a task when accepted.
if (process.argv.length > 4) {
  const task = await as(db, A, `insert into public.ai_suggestions (type, description, proposed_change)
    values ('CREATE_TASK', 'From your syllabus', '{"name": "HW 1", "due": "2027-01-22T23:59:00-05:00", "kind": "deadline"}')
    returning suggestion_id`);
  check("a task suggestion can be stored", task.rows.length === 1);
  check("a task suggestion has no target event", await fails(as(db, A, `insert into public.ai_suggestions (type, target_id, proposed_change)
    values ('CREATE_TASK', ${eventId}, '{}')`)));
  check("unknown suggestion types are still refused", await fails(as(db, A, `insert into public.ai_suggestions (type, proposed_change)
    values ('DROP_EVERYTHING', '{}')`)));
}

// Delete and journal suggestions, and daily overviews (fourth migration).
if (process.argv.length > 5) {
  for (const type of ["DELETE_EVENT", "DELETE_TASK", "DELETE_JOURNAL", "ADD_JOURNAL"]) {
    const row = await as(db, A, `insert into public.ai_suggestions (type, proposed_change) values ('${type}', '{"what": "event", "id": "1"}')
      returning suggestion_id`);
    check(`a ${type} suggestion can be stored (no target_id)`, row.rows.length === 1);
  }
  check("a delete suggestion doesn't use target_id", await fails(as(db, A, `insert into public.ai_suggestions (type, target_id, proposed_change)
    values ('DELETE_EVENT', ${eventId}, '{}')`)));
  const del = await as(db, A, `insert into public.ai_suggestions (type, proposed_change)
    values ('DELETE_EVENT', '{"what": "event", "id": "${eventId}"}') returning suggestion_id`);
  await as(db, A, `delete from public.calendar_events where event_id = ${eventId}`);
  check("an accepted delete keeps its suggestion (the record of the decision)",
    (await as(db, A, `select * from public.ai_suggestions where suggestion_id = ${del.rows[0].suggestion_id}`)).rows.length === 1);

  await as(db, A, `insert into public.daily_overviews (date, overview) values ('2026-10-06', '{"headline": "First"}')`);
  check("one overview per day: a second insert is refused", await fails(as(db, A,
    `insert into public.daily_overviews (date, overview) values ('2026-10-06', '{"headline": "Again"}')`)));
  await as(db, A, `insert into public.daily_overviews (date, overview) values ('2026-10-06', '{"headline": "Second"}')
    on conflict (user_id, date) do update set overview = excluded.overview`);
  check("a refresh replaces the day's overview (upsert)",
    (await as(db, A, `select overview->>'headline' as h from public.daily_overviews`)).rows[0].h === "Second");
  check("another user can't see someone's overview", (await as(db, B, `select * from public.daily_overviews`)).rows.length === 0);
  check("nobody can write an overview for someone else", await fails(as(db, B,
    `insert into public.daily_overviews (user_id, date, overview) values ('${A}', '2026-10-07', '{}')`)));
  await db.exec(`set role anon`);
  check("signed-out visitors can't read overviews", await fails(db.query(`select * from public.daily_overviews`)));
  await db.exec(`reset role`);
}

// Journal edits (fifth migration).
if (process.argv.length > 6) {
  const edit = await as(db, A, `insert into public.ai_suggestions (type, proposed_change)
    values ('EDIT_JOURNAL', '{"date": "2026-10-04", "text": "New", "old": "Old"}') returning suggestion_id`);
  check("an EDIT_JOURNAL suggestion can be stored", edit.rows.length === 1);
  check("unknown types are still refused after it", await fails(as(db, A, `insert into public.ai_suggestions (type, proposed_change)
    values ('REWRITE_EVERYTHING', '{}')`)));
}

// Activity log: append-only.
await as(db, A, `insert into public.activity_log (action, target_type, target_id, performed_by) values ('SUGGESTION_ACCEPTED', 'ai_suggestion', '${sid}', 'USER')`);
check("activity log entries can't be edited", (await as(db, A, `update public.activity_log set action = 'X'`)).affectedRows === 0);
check("activity log entries can't be deleted", (await as(db, A, `delete from public.activity_log`)).affectedRows === 0);

// Profiles.
check("users can't read other profiles", (await as(db, B, `select * from public.users where user_id = '${A}'`)).rows.length === 0);
check("users can edit their own profile", (await as(db, A, `update public.users set hobbies = '{reading,gym}', preferred_work_time = 'Night'`)).affectedRows === 1);
check("an unknown time zone is refused", await fails(as(db, A, `update public.users set timezone = 'Moon/Crater'`)));
const updated = (await as(db, A, `select updated_at > created_at as bumped from public.users`)).rows[0];
check("updated_at moves on edit", updated.bumped === true);

// Nobody can call the sign-up function through the API (second migration).
if (process.argv.length > 3) {
  check("signed-in users can't call handle_new_user directly", await fails(as(db, A, `select public.handle_new_user()`)));
}

// Signed-out visitors.
await db.exec(`set role anon`);
check("signed-out visitors can't read events", await fails(db.query(`select * from public.calendar_events`)));
await db.exec(`reset role`);

// Google sign-in and the calendar link (sixth migration).
if (process.argv.length > 7) {
  const C = "33333333-3333-3333-3333-333333333333";
  const D = "44444444-4444-4444-4444-444444444444";
  await db.exec(`set role supabase_auth_admin`);
  await db.exec(`insert into auth.users (id, email, raw_user_meta_data) values
    ('${C}', 'delger@gmail.com', '{"full_name": "Delger Byambasukh", "given_name": "Delger", "family_name": "Byambasukh"}'),
    ('${D}', 'chirant@gmail.com', '{"name": "Chirant Rao Patel"}')`);
  await db.exec(`reset role`);
  const names = Object.fromEntries((await db.query(`select user_id, first_name, last_name from public.users where user_id in ('${C}', '${D}')`))
    .rows.map((r) => [r.user_id, `${r.first_name}|${r.last_name}`]));
  check("a Google sign-up gets its first and last name from Google", names[C] === "Delger|Byambasukh", names[C]);
  check("only a full name: first word, then the rest", names[D] === "Chirant|Rao Patel", names[D]);

  const link = await as(db, A, `insert into public.calendar_feeds (user_id) values ('${A}') returning token`);
  const token = link.rows[0].token;
  check("a calendar link gets a 64-character random token", /^[0-9a-f]{64}$/.test(token), token);
  check("one link per user", await fails(as(db, A, `insert into public.calendar_feeds (user_id) values ('${A}')`)));
  check("a user can't choose their own token",
    await fails(as(db, B, `insert into public.calendar_feeds (user_id, token) values ('${B}', '${"0".repeat(64)}')`)));
  check("a user can't make a link for someone else", await fails(as(db, B, `insert into public.calendar_feeds (user_id) values ('${C}')`)));
  check("another user can't see the link", (await as(db, B, `select * from public.calendar_feeds`)).rows.length === 0);
  check("signed-out visitors can't read links", await fails(db.query(`set role anon; select * from public.calendar_feeds`)).then(async (r) => {
    await db.exec(`reset role`); return r; }));

  await db.exec(`set role anon`);
  const feed = (await db.query(`select public.calendar_feed($1) as f`, [token])).rows[0].f;
  const wrong = (await db.query(`select public.calendar_feed($1) as f`, ["0".repeat(64)])).rows[0].f;
  const short = (await db.query(`select public.calendar_feed($1) as f`, [token.slice(0, 10)])).rows[0].f;
  await db.exec(`reset role`);
  // (the lecture was deleted by an accepted suggestion above; "Late study" is still there)
  check("the link shows the owner's events and tasks", feed && feed.events.some((e) => e.name === "Late study")
    && feed.tasks.some((t) => t.name === "PHY 183 problem set") && feed.timezone === "America/Chicago");
  check("the link shows no journal, profile or suggestions", feed && Object.keys(feed).sort().join(",") === "events,tasks,timezone");
  check("a wrong token shows nothing", wrong === null);
  check("a cut-off token shows nothing", short === null);
  check("signed-in users can't call the link function", await fails(as(db, B, `select public.calendar_feed('${token}')`)));
  const removed = await as(db, A, `delete from public.calendar_feeds`);
  await db.exec(`set role anon`);
  const afterOff = (await db.query(`select public.calendar_feed($1) as f`, [token])).rows[0].f;
  await db.exec(`reset role`);
  check("turning the link off stops it working", removed.affectedRows === 1 && afterOff === null);
}

// Importing other calendars (seventh migration).
if (process.argv.length > 8) {
  const GOOGLE = "https://calendar.google.com/calendar/ical/alex%40gmail.com/private-abc123/basic.ics";
  const imp = await as(db, A, `insert into public.calendar_imports (name, url) values ('Google Calendar', $1) returning import_id, user_id`, [GOOGLE]);
  const importId = imp.rows[0].import_id;
  check("a user can import a calendar (their own row, by default)", imp.rows[0].user_id === A);
  check("only https addresses are stored", await fails(as(db, A, `insert into public.calendar_imports (name, url) values ('x', 'webcal://example.com/a.ics')`)));
  check("the same address can't be imported twice", await fails(as(db, A, `insert into public.calendar_imports (name, url) values ('Again', $1)`, [GOOGLE])));
  check("another user can't see the import (or its secret address)", (await as(db, B, `select * from public.calendar_imports`)).rows.length === 0);
  check("signed-out visitors can't read imports", await fails(db.query(`set role anon; select * from public.calendar_imports`)).then(async (r) => {
    await db.exec(`reset role`); return r; }));

  const imported = (name, key, day = "2026-11-19") => as(db, A, `insert into public.calendar_events
    (name, start_date, start_time, end_date, end_time, changeable, import_id, external_id)
    values ($1, $2, '09:00', $2, '10:00', false, $3, $4) on conflict (import_id, external_id) do nothing returning event_id`,
    [name, day, importId, key]);
  check("an imported event is stored with its import and id there", (await imported("Standup", "abc@google.com|2026-11-19T14:00:00Z")).rows.length === 1);
  check("the same event twice is skipped, not doubled (two syncs at once)",
    (await imported("Standup", "abc@google.com|2026-11-19T14:00:00Z")).rows.length === 0);
  await imported("Dentist", "dentist@google.com", "2026-11-20");
  check("an import needs its event id, and the other way round", await fails(as(db, A, `insert into public.calendar_events
    (name, start_date, start_time, end_date, end_time, import_id) values ('x', '2026-11-19', '09:00', '2026-11-19', '10:00', $1)`, [importId])));
  check("nobody can attach events to someone else's import", await fails(as(db, B, `insert into public.calendar_events
    (name, start_date, start_time, end_date, end_time, import_id, external_id)
    values ('x', '2026-11-19', '09:00', '2026-11-19', '10:00', $1, 'x')`, [importId])));

  const link = await as(db, A, `insert into public.calendar_feeds (user_id) values ('${A}') returning token`);
  await db.exec(`set role anon`);
  const feed = (await db.query(`select public.calendar_feed($1) as f`, [link.rows[0].token])).rows[0].f;
  await db.exec(`reset role`);
  check("the calendar link leaves imported events out (no doubles in Google)",
    feed.events.some((e) => e.name === "Late study") && !feed.events.some((e) => e.name === "Standup" || e.name === "Dentist"),
    feed.events.map((e) => e.name).join(", "));
  check("signed-in users still can't call the link function", await fails(as(db, B, `select public.calendar_feed('${link.rows[0].token}')`)));

  await as(db, A, `delete from public.calendar_imports where import_id = $1`, [importId]);
  const left = (await as(db, A, `select name from public.calendar_events order by name`)).rows.map((r) => r.name);
  check("removing an import removes its events, and only those", !left.includes("Standup") && !left.includes("Dentist") && left.includes("Late study"), left.join(", "));
}

console.log(failures ? `\n${failures} check(s) failed` : "\nAll checks passed");
process.exit(failures ? 1 : 0);
