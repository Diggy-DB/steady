-- Nov 2026: the AI can also suggest deleting an event, a task or a journal entry, and adding to the journal;
-- and it writes a daily overview (how yesterday went, compared with the week before).

-- 1. More kinds of suggestions. Deletes name what they delete inside proposed_change
--    ({"what": "event" | "task" | "journal", "id", "name", ...}), not in target_id: target_id references
--    calendar_events ON DELETE CASCADE, so an accepted delete would erase its own suggestion (the record of
--    what the user decided), and tasks and journal entries aren't events anyway. So target_id keeps its
--    meaning (only MOVE_EVENT uses it) and only the list of types grows.
--    ADD_JOURNAL: {"date": "YYYY-MM-DD", "text", "adds_to_existing"}; accepting adds to that day's entry.

alter table public.ai_suggestions drop constraint ai_suggestions_type_check;
alter table public.ai_suggestions add constraint ai_suggestions_type_check
  check (type in ('CREATE_EVENT', 'MOVE_EVENT', 'CREATE_TASK',
                  'DELETE_EVENT', 'DELETE_TASK', 'DELETE_JOURNAL', 'ADD_JOURNAL'));

-- 2. daily_overviews: one per user per day, written by the AI service with the user's own token, so the
--    app doesn't wait for the model every time it opens. A refresh replaces the day's row (upsert).

create table public.daily_overviews (
  overview_id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references public.users (user_id) on delete cascade,
  date date not null,       -- the day it was written for; it looks back at the day before
  overview jsonb not null,  -- {"headline", "yesterday", "compared", "suggestions", "quote", "stats", ...}
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, date)
);

create trigger daily_overviews_updated_at before update on public.daily_overviews
  for each row execute function public.set_updated_at();

alter table public.daily_overviews enable row level security;
create policy "own overviews" on public.daily_overviews
  for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
revoke all on public.daily_overviews from anon;
