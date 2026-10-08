# Stage 1 notes

Goal: one tool (`get_schedule`) and the agent loop, working against fake data
at a fixed, fake "now", with every round logged.

## What was built

| File | What it does |
|---|---|
| `fixtures/week.json` | Fake week (Oct 5–11, 2026) for Alex (`user-1`): class MWF 10–12, work Tue/Thu 1–5 (fixed), study sessions and gym (changeable), 3 tasks. Sam (`user-2`) exists only to test that users never see each other's data. |
| `src/ai/schedule.py` | `FixtureStore` (data access; a Supabase version will have the same methods), `ToolContext` (user and time come from code, never the model), `overlaps`, and the `get_schedule` tool. Each event is labeled "already over" / "happening now" / "upcoming" in code. |
| `src/ai/agent.py` | The loop: model → tool calls → `run_tool` checks them → results back → repeat, max 5 rounds. Every round is logged with a `run_id`. |
| `scripts/stage1_chat.py` | Ask a question at a fake time (`--now`, default Monday Oct 5, 6:30 PM). |
| `tests/test_schedule.py`, `tests/test_agent.py` | 18 tests; the loop tests use a fake client, so they're fast and repeatable. 24 tests in total with Stage 0. |

## Runs (thinking model, Monday Oct 5, 6:30 PM)

| question | tool call | tokens | time | result |
|---|---|---|---|---|
| "What do I have tomorrow?" | `get_schedule(Oct 6 → Oct 6)` | 801 | 31 s | correct: work 1–5 PM, gym 6–7 PM |
| "3-hour assignment due tonight" | `get_schedule(Oct 5 → Oct 5)` | 1,929 | 70 s | 9 PM–midnight: in the future, no overlap, but kept the changeable 7–9 PM study session instead of using it |
| "Gym 3× + two assignments this week" | `get_schedule(Oct 5 → Oct 11)` | 4,667 | 181 s | no conflicts, no past times; but 2-hour blocks for 3-hour assignments |
| same, after adding `description` to task results | `get_schedule(Oct 5 → Oct 11)` | 3,455 | 142 s | gym Wed and Fri 12:30–1:30 (valid); now mentions "3 hours", but gives no time for the problem set and a 2-hour slot for the 3-hour project |

## Findings

1. **Tool use works end to end.** The model picked the right tool and the right date range every
   time (one day for "tomorrow"/"tonight", the whole week for "this week").
2. **No past times in these runs** (Stage 0: 5 of 8 answers). The "already over" labels from
   code fixed what the time in the prompt alone couldn't.
3. **No conflicts in these runs** (Stage 0: an overlap with Friday class). Single runs, and
   nothing checked them → Stage 2 adds validation; Stage 3 measures how often it's right.
4. **The model only knows what the tools return.** Task descriptions ("About 3 hours of work")
   were missing, so it planned 2-hour blocks. Adding `description` let it see the 3 hours.
5. **Finding free time is still hard for it.** Even knowing the durations, it left one task
   without a time and gave the other too little, after 3,000+ tokens of thinking
   (2–2.5 minutes). → Stage 2: a `find_free_slots` tool that computes gaps in code.
6. **It treats changeable events as fixed.** Using tonight's study session for the assignment
   would have been better. → Stage 2: `propose_*` tools to suggest changes.
7. **Shorter answers.** The system prompt rules (no tables/emojis, 5 lines max) worked:
   answers are a few bullet points instead of 600–1,100 tokens.
