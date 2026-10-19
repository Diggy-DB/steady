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
check("drafts replaced by the planned tables", tables === "activity_log, ai_suggestions, calendar_events, journals, tasks, users", tables);

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

console.log(failures ? `\n${failures} check(s) failed` : "\nAll checks passed");
process.exit(failures ? 1 : 0);
