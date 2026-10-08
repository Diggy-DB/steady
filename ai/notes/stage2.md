# Stage 2 notes

Goal: let the model find free time and suggest changes, with every rule checked in
code, and nothing changing until the user accepts.

## What was built

| File | What changed |
|---|---|
| `src/ai/planning.py` (new) | `find_free_slots` (gaps between 8 AM and 10 PM, never in the past), `check_time` (the shared validation), `propose_new_event`, `propose_move_event`. |
| `src/ai/schedule.py` | `FixtureStore` gained `event()` (one event by id, only the user's own) and an in-memory list of suggestions (`suggestions()`, `add_suggestion()`). `get_schedule` returns task descriptions. |
| `src/ai/agent.py` | Four tools instead of one; `MAX_ROUNDS` 5 → 8; system prompt rules for finding time and proposing. |
| `scripts/chat.py` | Renamed from `stage1_chat.py`; prints pending suggestions (what the app would show as Accept / Decline cards). |
| `tests/test_planning.py` (new) | 14 tests. 38 tests in total. |

### What the checks enforce (`check_time` and the propose tools)

| Rule | Where | Example error the model gets back |
|---|---|---|
| End after start | `check_time` | "the end time must be after the start time" |
| Not in the past | `check_time` | "... has already started; it is now 6:30 PM on Monday, October 5" |
| No overlap with events | `check_time` | "... overlaps CSE 232 lecture (...). Use find_free_slots to pick a free time." |
| No overlap with other pending suggestions | `busy` | "... overlaps your pending suggestion s1 (...)" |
| Only the user's own events | `store.event` | "there is no event with id 'e11'" (another user's event looks like it doesn't exist) |
| Fixed events can't move | `propose_move_event` | "CSE 232 lecture is fixed (changeable: false) and can't be moved" |
| Finished events can't move | `propose_move_event` | "Study session on ... is already over" |

The backend must run the same checks again when the user taps Accept, because the
calendar may have changed since the suggestion was made.

## Suggestion format (v0, to agree with the backend team)

Each suggestion is one row of the planned `ai_suggestions` table:

```json
{
  "suggestion_id": "s1",
  "user_id": "user-1",
  "status": "PENDING",
  "type": "MOVE_EVENT",
  "target_id": "e2",
  "description": "Move study session to start at 8 PM for better focus",
  "proposed_change": {"start": "2026-10-05T20:00:00-04:00", "end": "2026-10-05T22:00:00-04:00"},
  "created_at": "2026-10-05T18:30:00-04:00",
  "expires_at": "2026-10-05T20:00:00-04:00"
}
```

| type | target_id | proposed_change |
|---|---|---|
| `CREATE_EVENT` | `null` | `{"name", "start", "end"}` |
| `MOVE_EVENT` | the event's id | `{"start", "end"}` |

- Times are ISO 8601 with the offset, so they work with `timestamptz` columns.
- `description` is the model's one-sentence reason, shown to the user.
- `expires_at` = the proposed start time: once it would have started, the suggestion is useless.

## Runs (thinking model, Monday Oct 5, 6:30 PM)

| question | tools used | tokens | time | result |
|---|---|---|---|---|
| Move my study session to 8 PM | get_schedule → propose_move_event(e2) | 3,861 | 143 s | **pass**: today's session, same length, pending suggestion |
| Move my CSE 232 lecture to Thursday | get_schedule | 2,751 | 101 s | **pass**: refused, lecture is fixed |
| 3-hour assignment due tonight | get_schedule → find_free_slots (none) | 5,678 | 216 s | **fail**: "work on it earlier today" (already past); didn't think of moving the study session |
| Gym 3× + two assignments this week | get_schedule → find_free_slots | 8,724 | 338 s | **fail**: valid times, but no proposals created (text only); two extra gym sessions around Tuesday's existing one |

Then two prompt rules were added ("when you recommend a time, create it with propose_*";
"if there isn't enough time, consider moving a changeable event or splitting the work"):

| question | tools used | tokens | time | result |
|---|---|---|---|---|
| 3-hour assignment due tonight | get_schedule → propose_move_event(e2 → 10 PM–12 AM) → propose_new_event(7–10 PM) **rejected: overlaps the study session** → find_free_slots | 11,261 | 431 s | **partly**: used the tools and reacted to the error, but the final text plan (6:30–8 and 9–10:30 PM) overlaps the moved session and wasn't proposed |
| Gym 3× + two assignments this week | get_schedule → find_free_slots | 11,545 | 458 s | **fail**: valid, conflict-free times, but still no proposals created |

## Findings

1. **The checks work and the model reacts to them.** A rejected proposal came back as an
   error, and the model tried another approach instead of repeating it.
2. **Simple requests pass; big plans don't.** Single moves and refusals work. For multi-part
   plans the model answers in text after a long think instead of creating proposals, even
   with an explicit rule. → Stage 3 should measure this, and try: fewer free slots per call,
   a code check that nudges the model when its answer mentions times but it proposed
   nothing, and the Instruct model.
3. **Suggestions can depend on each other, and the design doesn't support it yet.**
   "Move the study session, then use its old time" was rejected, correctly: the move is
   only pending, so the old time is still busy. → Team question: should a suggestion be
   able to contain several changes that are accepted together (a "plan"), or depend on
   another suggestion?
4. **Existing events aren't counted toward goals.** Tuesday already has a gym session, but
   "gym 3 times" added three more. → An eval scenario.
5. **Planning is slow.** 2.7k–11.5k tokens and 1.7–7.6 minutes per question on the Mac. The
   whole-week free-slot list (about 3,000 prompt tokens) makes the thinking long. → Cap the
   slots returned; measure on a RunPod GPU; compare with Instruct.

## Questions for the team

- The suggestion format above: does it fit the `ai_suggestions` table and the Accept endpoint?
- Multi-change plans (finding 3): one suggestion with several changes, or linked suggestions?
- Should pending suggestions block time for new proposals? (Currently yes, so the AI's own
  proposals can't overlap each other.)
- Where do the "day" hours (now 8 AM–10 PM) come from: user settings, or the
  morning/night preference from sign-up?
