# Stage 3: the eval suite, and what improved the AI

Goal: measure the assistant instead of judging answers by eye, so every change to the prompt, the
tools or the model can be compared with numbers.

## The suite (`src/ai/evals.py`, `scripts/run_evals.py`)

Six scenarios on the fake week (`fixtures/week.json`), each at a fixed fake time so every run
faces the same situation. Each one is scored by **checks written in code**:

| Scenario | Question | Passes if |
|---|---|---|
| tomorrow | What do I have tomorrow? | called `get_schedule`, mentions work and gym, proposed nothing |
| move_study_session | Move my study session to 8 PM. | moved tonight's session (e2) to 8 PM, **or** asked which one; never touched the other two |
| fixed_lecture | Move my CSE 232 lecture to Thursday afternoon. | proposed nothing, and said it's fixed / can't |
| due_tonight | I have a 3-hour assignment due tonight. When should I work on it? | at least one proposal; never said "earlier today" / "this morning" |
| week_plan | Gym 3 times for an hour + two assignments this week. | exactly 2 new gym sessions (Tuesday has one), ≥ 180 min for each assignment |
| gym_today | When can I go to the gym today? (Wednesday 9 AM) | called `find_free_slots`, never suggested 8 AM |

**These are the test set: never train on them.** Eval runs log to `logs/evals.jsonl`, separate
from `logs/calls.jsonl`, so they can't leak into training data.

Run: `uv run scripts/run_evals.py --runs 2 [--only week_plan] [--model …] [--label …]`.
Results go to `evals/<date>-<model>-<label>.jsonl`.

## Results (thinking model, 8-bit, Ollama on an M3 Pro Mac, 2 runs each)

| Scenario | Baseline (Oct 15) | With fixes (Nov 5) | Avg tokens (before → after) | Avg time (before → after) | Reminder used |
|---|---|---|---|---|---|
| tomorrow | 2/2 | 2/2 | 1,554 → 1,197 | 70 s → 55 s | 0/2 |
| move_study_session | 2/2 | 2/2 | 4,426 → 3,310 | 185 s → 131 s | 0/2 |
| fixed_lecture | 2/2 | 2/2 | 2,603 → 2,156 | 99 s → 87 s | 0/2 |
| due_tonight | 1/2 | **2/2** | 7,146 → 10,493 | 270 s → 428 s | 1/2 |
| week_plan | 0/2 | **1/2** | 8,433 → 16,550 | 342 s → **909 s** | 2/2 |
| gym_today | 2/2 | 2/2 | 3,894 → 9,176 | 147 s → 367 s | 2/2 |
| **Total** | **9/12 (75%)** | **11/12 (92%)** | | 37 min → 66 min | 5/12 |

### The fixes (Oct 15)

1. **Shorter `find_free_slots` output**: free times grouped by day as `"HH:MM-HH:MM"`.
2. **`depends_on`**: "move X, then use its old time" works; the second suggestion depends on the first.
3. **A reminder in code**: if the model recommends times after searching for free time but
   creates no suggestions, the loop reminds it once.
4. **A prompt rule**: count what's already on the calendar toward the user's goals.

### What the numbers say

- The reminder did most of the work: it fired in 5 of 12 runs, all planning questions. Without
  it, the model still mostly describes plans instead of proposing them.
- Planning is now right but **slow on a laptop** (a week plan took ~15 minutes): look up → find
  time → answer → reminder → several proposals, with thinking at every step. → A GPU (Stage 4).
- The remaining failure: a week plan proposed **3** new gym sessions though Tuesday already had
  one (the prompt rule didn't stick). Its assignment blocks were right.
- Simple questions used 15–25% fewer tokens, but with 2 runs each that's partly chance.

### Follow-up fix (Nov 5): "already planned this week"

`propose_new_event` now tells the model about events and pending suggestions with a similar
name in the same week ("Already planned this week with a similar name: Gym (Tuesday, October 6,
6:00 PM – 7:00 PM). Count these toward the user's goal before suggesting more."), ignoring
generic words like "session" and events that are already over.

Re-run of `week_plan` (2 runs, label `similar-note`): **0/2**, ~18,500 tokens, ~15.5 min each.

| Run | Gym | Assignments | Failure |
|---|---|---|---|
| 1 | 2 new (right) | MTH 133 only | forgot the CSE 232 project |
| 2 | 3 new, one right after Tuesday's gym | both (right) | ignored the existing gym session |

The note fired correctly every time, but it **arrived too late**: in both runs the model wrote
its whole plan as text, got the reminder, then made all its proposals **in one round** (parallel
calls), so it only saw the note after every proposal already existed. The mistakes were already
in the plan. The note stays (it costs nothing and helps when proposals come one at a time), but
the week plan is a problem with the model's planning itself, which no tool message fixes. That
points to fine-tuning (`notes/training.md`): the `weekly_goal` training task teaches exactly this
counting. With 2 runs, 1/2 → 0/2 is within chance.

## Next

- Run the same suite on a GPU, for the thinking and the instruct model (Stage 4).
- The suite is small (6 scenarios × 2 runs): add scenarios before trusting small differences,
  e.g. a journal-memory scenario, two events with the same name, and requests in other weeks.
