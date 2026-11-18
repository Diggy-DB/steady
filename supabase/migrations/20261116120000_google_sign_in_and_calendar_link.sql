-- Sign in with Google, and a private calendar link for Apple Calendar, Google Calendar and Outlook (Nov 16, 2026).

-- 1. Profiles for Google sign-ups. Our sign-up form sends first_name, last_name and timezone; Google sends
--    given_name and family_name (or only a full name) and no time zone. The app sets the time zone from the
--    browser right after the first log-in. Everything else is as before.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  meta jsonb := coalesce(new.raw_user_meta_data, '{}'::jsonb);
  zone text := nullif(meta ->> 'timezone', '');
  full_name text := trim(coalesce(nullif(meta ->> 'full_name', ''), nullif(meta ->> 'name', ''), ''));
  first_word text := split_part(trim(coalesce(nullif(meta ->> 'full_name', ''), nullif(meta ->> 'name', ''), '')), ' ', 1);
begin
  if zone is null or not exists (select 1 from pg_catalog.pg_timezone_names where name = zone) then
    zone := 'America/Detroit';
  end if;
  insert into public.users (user_id, email, first_name, last_name, timezone)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(nullif(meta ->> 'first_name', ''), nullif(meta ->> 'given_name', ''), first_word),
    coalesce(nullif(meta ->> 'last_name', ''), nullif(meta ->> 'family_name', ''),
             trim(substr(full_name, length(first_word) + 1))),
    zone
  );
  return new;
end $$;
revoke execute on function public.handle_new_user() from public, anon, authenticated;


-- 2. The calendar link: one secret token per user. Calendar apps fetch the link with no login, so the token is
--    the only key: 64 random hex characters, made by the database (a user can't pick a weak one). Turning the
--    link off deletes the row; a new link is a new row with a new token, and the old link stops working.
create table public.calendar_feeds (
  user_id uuid primary key default auth.uid() references public.users (user_id) on delete cascade,
  token text not null unique
    default replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', ''),
  created_at timestamptz not null default now()
);

alter table public.calendar_feeds enable row level security;
create policy "own calendar link" on public.calendar_feeds
  for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- Read and delete your own row; insert only user_id (the token always comes from the default above).
revoke all on public.calendar_feeds from anon, authenticated;
grant select, delete on public.calendar_feeds to authenticated;
grant insert (user_id) on public.calendar_feeds to authenticated;


-- 3. What a calendar link shows: one user's events and tasks, found by the token alone. The Edge Function
--    calendar-feed calls this as the public anon role (no admin key anywhere) and turns the answer into an
--    .ics file. A wrong or short token returns null. Events: all repeating ones, and single ones from the last
--    90 days on; tasks from the last 90 days on. No journal, profile details or suggestions.
create function public.calendar_feed(feed_token text) returns jsonb
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
      where e.user_id = f.user_id and (e.recurrence_rule is not null or e.end_date >= current_date - 90)), '[]'::jsonb),
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
