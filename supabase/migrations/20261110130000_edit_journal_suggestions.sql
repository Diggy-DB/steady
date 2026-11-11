-- Nov 2026: the AI can also suggest editing a journal entry. EDIT_JOURNAL's proposed_change is
-- {"date": "YYYY-MM-DD", "text": the whole edited entry, "old": the entry it was written from}. Accepting
-- replaces that day's text, and the AI service refuses if the entry changed since (it compares with "old"),
-- so a suggestion never overwrites something the user wrote afterwards. Only the list of types grows.

alter table public.ai_suggestions drop constraint ai_suggestions_type_check;
alter table public.ai_suggestions add constraint ai_suggestions_type_check
  check (type in ('CREATE_EVENT', 'MOVE_EVENT', 'CREATE_TASK',
                  'DELETE_EVENT', 'DELETE_TASK', 'DELETE_JOURNAL', 'ADD_JOURNAL', 'EDIT_JOURNAL'));
