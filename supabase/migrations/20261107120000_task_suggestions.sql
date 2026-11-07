-- Syllabus import (Nov 2026): the AI can also suggest TASKS, e.g. "HW 3 due Friday 11:59 PM" read from a
-- syllabus. A deadline isn't a calendar event (an event must end after it starts), so accepting one adds a
-- row to public.tasks. Weekly classes from a syllabus use calendar_events.recurrence_rule, already there.
-- proposed_change for CREATE_TASK: {"name", "due": ISO 8601 with offset, "kind": "deadline"}.

alter table public.ai_suggestions drop constraint ai_suggestions_type_check;
alter table public.ai_suggestions add constraint ai_suggestions_type_check
  check (type in ('CREATE_EVENT', 'MOVE_EVENT', 'CREATE_TASK'));
