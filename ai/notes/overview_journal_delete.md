# Daily overview, journal add/edit, and delete suggestions (Nov 10-11, 2026)

What the user asked for: an AI overview generated from the previous day (how yesterday went compared with
before, habit and schedule suggestions, a motivational quote), the AI able to add to and edit the journal,
and the AI able to suggest deleting events, tasks and journal entries, applied only if the user accepts.

## What was built

| Piece | Where |
|---|---|
| `get_journal`, `propose_journal_entry` (add, or `replace: true` to edit), `propose_delete` (event / task / journal) | `src/ai/planning.py`, registered in `src/ai/agent.py` (7 tools now) |
| Accepting them: delete rows, add to or replace a journal entry | `FixtureStore.apply` (`schedule.py`), `SupabaseStore.apply` |
| The daily overview | `src/ai/overview.py`; `GET /overview`, `POST /overview/refresh` in `server.py` |
| Database: new suggestion types, table `daily_overviews` | `supabase/migrations/20261110120000_*.sql`, `20261110130000_*.sql` (both applied Nov 10, approved) |
| Website: overview box, red delete cards, journal cards (edits show before/after), "Ask Steady" | `Front-end/src/components/AIOverview.jsx`, `ChatWidget.jsx` |

## Design decisions

- **Deletes name their target in `proposed_change`, not `target_id`.** `ai_suggestions.target_id` references
  `calendar_events ON DELETE CASCADE`: accepting a delete would erase its own suggestion (the record of what the
  user decided), and tasks and journal entries aren't events. Tested in `supabase/tests/test_migration.mjs`.
- **Edits never overwrite newer writing.** `EDIT_JOURNAL` stores the entry it was written from (`old`); Accept
  refuses if the entry has changed since.
- **What the AI may not delete:** fixed (changeable: false) events and tasks, and weekly classes (a delete would
  remove the whole series); it tells the user to remove those themselves. An event can't have a pending move
  and a pending delete at once. A pending delete still counts as busy until it's accepted.
- **Deletes and journal entries need the user to have asked, checked in code.** In a real run, asked only for
  time for a lab report, the 4B also suggested deleting an unrelated problem set. The prompt rule didn't stop
  it, so `run_agent` puts the user's message (and Steady's previous reply, for "yes, delete it") in
  `ctx.asked`, and the tools refuse unless it has delete words (delete, remove, cancel, drop, take it off,
  not going, don't need, ...) or journal words. Code calling the tools directly (`asked=None`) isn't checked.
- **Journal dates:** a new entry more than 7 days back is refused with today's and yesterday's dates in the
  message. In the evals the 4B wrote "yesterday" as 2026-01-11 (a year off) and "Friday" as last Friday.
- **"I suggest deleting X" without a card gets one reminder,** like the existing reminder for times without
  proposals (an end-to-end run said it but never called the tool).
- **The overview's numbers come from code.** First tries with the model writing everything: it called a task
  due yesterday "overdue", called the second journal entry the "first", and invented "eight days of zero
  progress". Now code counts tasks due/done, hours planned, journal days, overdue tasks and writes the
  comparison sentence; the model writes only the headline, the look back, 2-3 suggestions (each schedule
  suggestion with an "ask" the chat can act on) and one line of encouragement. Thinking off (with thinking on,
  the 4B used the whole token budget thinking and never wrote the JSON). One retry, and a repair for the slip
  `,""quote":`, before falling back to an overview written entirely by code. Quotes come from a fixed list of
  20 with checked sources (no famous-but-misattributed ones); the model picks a number.

## Evals

New categories in the suite: **delete** (9 hand-written + 17 generated: delete an event / a task / a journal
entry, refuse fixed events, ask which of six identical sessions, "not found", move rather than delete) and
**journal** (8 + 10: add today / yesterday, refuse a future day, edit keeping the rest, don't write unasked).
Every other case now also fails if the assistant deletes or journals without being asked. The old
`unclear/chris_cancel_movie` ("I can't delete events") is now `delete/chris_movie_night_short`.

Qwen3.5-4B (Ollama on the Mac, thinking on), one run per case:

| run | delete | journal |
|---|---|---|
| Nov 10, first version (before the reminder, date guard, request check and edits) | 23/25 (92%) | 13/16 (81%) |
| Nov 11, generated cases (after the reminder and date guard) | **17/17** | **10/10** |
| Nov 11, final code, hand-written cases | 7/8 | **8/8** |

The delete case it keeps failing: "Delete my study session" with six identical ones: it picks Monday's instead
of asking. The card shows the date, so the user can decline it.

**Ollama's context window.** The first full run after the change had 12 empty answers (0 in 168 runs before):
Ollama on the Mac defaults to a 4,096-token window for this much memory, and the prompt with 7 tools
(~2,000-2,500 tokens before any thinking) no longer leaves room. Rerun with `OLLAMA_CONTEXT_LENGTH=16384`: no
empty answers. The pod's vLLM has 32,768. **Run Ollama with `OLLAMA_CONTEXT_LENGTH=16384 ollama serve` from now on.**

**Did the new tools hurt the old categories?** The full run (with the context problem) had the old cases at 35/56
against 35.7 expected from their earlier pass rates; the rerun of the 17 worst of them, with 16k context, at 5
against 7.7, and none of those failures used a new tool or the new reminder (they're mostly plans and goals
that were already failing 2-3 of 3). No sign of harm, but one run per case can't rule out a small drop: run
the whole suite 3 times on the GPU to settle it:

    cd /workspace/steady/ai && LLM_BASE_URL=http://127.0.0.1:18001/v1 LLM_API_KEY=x LLM_MODEL=Qwen/Qwen3.5-4B \
      uv run scripts/run_evals.py --suite all --runs 3 --workers 8 --label tools7-gpu

Results: `evals/2026-11-10-2250-*delete-journal-v1*`, `2026-11-10-2310-*tools7-core*`,
`2026-11-11-1029-*tools7-gen-delete-journal*`, `2026-11-11-1044-*tools7-ctx16k-recheck*`.
