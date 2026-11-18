-- Importing other calendars (Nov 18, 2026): Google Calendar, Apple iCloud, Outlook, Canvas and any other calendar
-- with a private iCal (.ics) address.
--
-- The person pastes the address once, in Settings. The AI server (ai/src/ai/calendar_import.py) reads it with the
-- person's own login token, so Row Level Security applies, and copies each event of the coming months into
-- calendar_events as a fixed event (changeable = false: the AI plans around it and never suggests moving or
-- deleting it). Each sync adds, changes and removes those copies to match the other calendar. Removing an import
-- removes its events. Nothing is ever written back to the other calendar.
--
-- Needs 20261116120000_google_sign_in_and_calendar_link.sql (it replaces calendar_feed from there).


-- 1. calendar_imports: one row per imported calendar.
create table public.calendar_imports (
  import_id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references public.users (user_id) on delete cascade,
  name text not null check (name <> '' and length(name) <= 100),
  url text not null check (url ~ '^https://' and length(url) <= 2000), -- secret: anyone with it can read that calendar
  last_checked_at timestamptz,  -- the last try, worked or not (automatic syncs wait an hour after it)
  last_synced_at timestamptz,   -- the last time it worked
  last_error text,              -- why the last try failed, in plain words; null when it worked
  created_at timestamptz not null default now(),
  unique (user_id, url),
  unique (import_id, user_id)  -- lets calendar_events point at (import_id, user_id) below
);

alter table public.calendar_imports enable row level security;
create policy "own calendar imports" on public.calendar_imports
  for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
revoke all on public.calendar_imports from anon;


-- 2. Imported events: which import they came from, and their id there (the event's UID and, for a repeating event,
--    which time it is). The foreign key includes user_id, so an event can only point at its owner's import.
alter table public.calendar_events
  add column import_id bigint,
  add column external_id text check (length(external_id) <= 1000),
  add constraint calendar_events_import foreign key (import_id, user_id)
    references public.calendar_imports (import_id, user_id) on delete cascade,
  add constraint calendar_events_import_key unique (import_id, external_id),
  add constraint calendar_events_import_both check ((import_id is null) = (external_id is null));


-- 3. The calendar link (calendar_feed) leaves imported events out: they are already in the calendar they came
--    from, and sending them back would show them twice there. Otherwise unchanged.
create or replace function public.calendar_feed(feed_token text) returns jsonb
language sql stable security definer set search_path = '' as $$
  select jsonb_build_object(
    'timezone', u.timezone,
    'events', coalesce((
      select jsonb_agg(jsonb_build_object(
          'id', e.event_id, 'name', e.name, 'start_date', e.start_date, 'start_time', e.start_time,
          'end_date', e.end_date, 'end_time', e.end_time, 'recurrence_rule', e.recurrence_rule,
          'changeable', e.changeable, 'updated_at', e.updated_at)
        order by e.start_date, e.start_time)
      from public.calendar_events e
      where e.user_id = f.user_id and e.import_id is null
        and (e.recurrence_rule is not null or e.end_date >= current_date - 90)), '[]'::jsonb),
    'tasks', coalesce((
      select jsonb_agg(jsonb_build_object(
          'id', t.task_id, 'name', t.name, 'date', t.date, 'status', t.status, 'updated_at', t.updated_at)
        order by t.date)
      from public.tasks t
      where t.user_id = f.user_id and t.date >= current_date - 90), '[]'::jsonb))
  from public.calendar_feeds f
  join public.users u on u.user_id = f.user_id
  where length(feed_token) = 64 and f.token = feed_token
$$;
revoke execute on function public.calendar_feed(text) from public, authenticated;
grant execute on function public.calendar_feed(text) to anon;
