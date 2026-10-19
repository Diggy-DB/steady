-- Steady Planner database, following the team's plan (meeting notes, Sept 24, 2026)
-- and the shape the frontend's mock data (Front-end/src/data/mockData.js) already uses.
--
-- It replaces the three EMPTY draft tables ("Users", "Events", "Personalization"):
-- events had no times, and "Users" stored passwords, which Supabase Auth must handle.
-- The migration stops without changing anything if any of those tables has rows.
--
-- Security: every table has Row Level Security. A signed-in user can only see and
-- change rows whose user_id is their own auth.uid(). The AI service talks to the
-- database with the user's own access token, so the same rules apply to it.
--
-- Times in calendar_events are local to the user's time zone (users.timezone).


-- 0. Safety check: refuse to drop draft tables that hold data.
do $$
declare
  draft text;
  row_count bigint;
begin
  foreach draft in array array['Events', 'Personalization', 'Users'] loop
    if to_regclass(format('public.%I', draft)) is not null then
      execute format('select count(*) from public.%I', draft) into row_count;
      if row_count > 0 then
        raise exception 'public."%" has % rows; not dropping it. Move the data first.', draft, row_count;
      end if;
    end if;
  end loop;
end $$;

drop table if exists public."Events";
drop table if exists public."Personalization";
drop table if exists public."Users";

-- Keep the team's morning/night type from the draft.
do $$
begin
  if to_regtype('public.active_hours') is null then
    create type public.active_hours as enum ('Morning', 'Night');
  end if;
end $$;


-- 1. Helpers

create function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

create function public.check_timezone() returns trigger
language plpgsql as $$
begin
  if not exists (select 1 from pg_catalog.pg_timezone_names where name = new.timezone) then
    raise exception 'unknown time zone: %', new.timezone;
  end if;
  return new;
end $$;


-- 2. users: one profile per Supabase Auth user (Auth itself stores email and password).
--    Includes the fields from the draft "Personalization" table.

create table public.users (
  user_id uuid primary key references auth.users (id) on delete cascade,
  first_name text not null default '',
  last_name text not null default '',
  email text not null default '',
  timezone text not null default 'America/Detroit',
  preferred_work_time public.active_hours not null default 'Morning',
  hobbies text[] not null default '{}',
  priorities text[] not null default '{}',  -- most important first
  additional_information text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger users_updated_at before update on public.users
  for each row execute function public.set_updated_at();
create trigger users_check_timezone before insert or update of timezone on public.users
  for each row execute function public.check_timezone();

-- Create the profile automatically when someone signs up. The frontend passes
-- first_name, last_name and timezone as sign-up metadata.
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  zone text := nullif(new.raw_user_meta_data ->> 'timezone', '');
begin
  if zone is null or not exists (select 1 from pg_catalog.pg_timezone_names where name = zone) then
    zone := 'America/Detroit';
  end if;
  insert into public.users (user_id, email, first_name, last_name, timezone)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data ->> 'first_name', ''),
    coalesce(new.raw_user_meta_data ->> 'last_name', ''),
    zone
  );
  return new;
end $$;

create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();


-- 3. calendar_events

create table public.calendar_events (
  event_id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references public.users (user_id) on delete cascade,
  name text not null check (name <> ''),
  start_date date not null,
  start_time time not null,
  end_date date not null,
  end_time time not null,
  recurrence_rule text,                       -- e.g. 'FREQ=WEEKLY;BYDAY=MO,WE,FR' (not used by the AI yet)
  changeable boolean not null default true,   -- false = fixed: the AI may never suggest moving it
  created_by text not null default 'USER' check (created_by in ('USER', 'AI')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (end_date + end_time > start_date + start_time)
);

create index calendar_events_user_day on public.calendar_events (user_id, start_date);
create trigger calendar_events_updated_at before update on public.calendar_events
  for each row execute function public.set_updated_at();


-- 4. tasks

create table public.tasks (
  task_id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references public.users (user_id) on delete cascade,
  name text not null check (name <> ''),
  description text not null default '',
  date date not null,  -- the day it's due
  status text not null default 'NOT_STARTED' check (status in ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED')),
  changeable boolean not null default true,
  created_by text not null default 'USER' check (created_by in ('USER', 'AI')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index tasks_user_day on public.tasks (user_id, date);
create trigger tasks_updated_at before update on public.tasks
  for each row execute function public.set_updated_at();


-- 5. journals: one entry per user per day

create table public.journals (
  journal_id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references public.users (user_id) on delete cascade,
  date date not null,
  information text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, date)
);

create trigger journals_updated_at before update on public.journals
  for each row execute function public.set_updated_at();


-- 6. ai_suggestions: what the AI proposed and what the user decided
--    (format: ai/notes/stage2.md and ai/notes/stage5_api.md)

create table public.ai_suggestions (
  suggestion_id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references public.users (user_id) on delete cascade,
  type text not null check (type in ('CREATE_EVENT', 'MOVE_EVENT')),
  target_id bigint references public.calendar_events (event_id) on delete cascade,
  description text not null default '',
  proposed_change jsonb not null,           -- {"name"?, "start", "end"} as ISO 8601 with offset
  depends_on jsonb not null default '[]',   -- ids of suggestions that must be accepted first
  status text not null default 'PENDING' check (status in ('PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED')),
  created_at timestamptz not null default now(),
  expires_at timestamptz,
  check ((type = 'MOVE_EVENT') = (target_id is not null))
);

create index ai_suggestions_user_status on public.ai_suggestions (user_id, status);


-- 7. activity_log: an audit trail of important changes (who, what, when)

create table public.activity_log (
  log_id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references public.users (user_id) on delete cascade,
  action text not null,        -- e.g. 'SUGGESTION_ACCEPTED'
  target_type text not null,   -- e.g. 'ai_suggestion', 'calendar_event'
  target_id text,
  performed_by text not null check (performed_by in ('USER', 'AI')),
  details jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index activity_log_user_time on public.activity_log (user_id, created_at);


-- 8. Row Level Security: each signed-in user only reaches their own rows.
--    "(select auth.uid())" is evaluated once per query instead of once per row.

alter table public.users enable row level security;
alter table public.calendar_events enable row level security;
alter table public.tasks enable row level security;
alter table public.journals enable row level security;
alter table public.ai_suggestions enable row level security;
alter table public.activity_log enable row level security;

-- Profiles are created by the sign-up trigger; users can read and edit their own.
create policy "read own profile" on public.users
  for select to authenticated using (user_id = (select auth.uid()));
create policy "edit own profile" on public.users
  for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- Full control of your own events, tasks and journal.
create policy "own events" on public.calendar_events
  for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "own tasks" on public.tasks
  for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "own journal" on public.journals
  for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- Suggestions: read, add and answer your own. No deleting: they're the history of decisions.
create policy "read own suggestions" on public.ai_suggestions
  for select to authenticated using (user_id = (select auth.uid()));
create policy "add own suggestions" on public.ai_suggestions
  for insert to authenticated with check (user_id = (select auth.uid()));
create policy "answer own suggestions" on public.ai_suggestions
  for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- Activity log: read and add your own entries; nobody edits or deletes them through the API.
create policy "read own activity" on public.activity_log
  for select to authenticated using (user_id = (select auth.uid()));
create policy "add own activity" on public.activity_log
  for insert to authenticated with check (user_id = (select auth.uid()));

-- Signed-out visitors (the anon role) get nothing.
revoke all on public.users, public.calendar_events, public.tasks, public.journals,
  public.ai_suggestions, public.activity_log from anon;
