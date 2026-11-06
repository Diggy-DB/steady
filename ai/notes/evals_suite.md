# The eval suites: what's tested, and why every case is trustworthy

Two test sets, both kept away from training data:

| What | Where | Size |
|---|---|---|
| **Planning agent**, hand-written (chat: look up, move, plan, ...) | `src/ai/eval_suite.py`, weeks in `fixtures/week.json` + `fixtures/eval_weeks/` | 57 cases, 13 categories, 5 students' weeks |
| **Planning agent**, generated | `src/ai/eval_generated.py` (weeks built in code) | 194 cases, the same 13 categories, 12 more weeks |
| **Syllabus import** (upload → suggestions) | `fixtures/syllabi/` (answer key: `truth.json`) | 26 syllabi, 350 dated items, 11 categories |

### Why 251 planning cases, not 57

57 cases × 3 runs measure the overall pass rate to about ±7-10 points, and a change has to fix about
9 more cases than it breaks to be told apart from luck (15-20 points). Fine-tuning will likely move
things 5-10 points, and per category 3-6 cases say almost nothing. With 251 cases (at least 10 per
category) the overall rate is good to about ±4 points and a 10-point change is detectable.

### How the generated cases are made (`src/ai/eval_generated.py`)

14 templates ("move a changeable event to a free time", "a weekly goal where some sessions already
exist", "a task before its deadline", "a conflict with a fixed event", "an instruction hidden in an
event name", ...) are filled in on 12 generated weeks (Sept 2026 - Apr 2027; New York, Phoenix without
daylight saving, Honolulu, London, Kolkata, Anchorage; different courses, activities and wording from
training). For each case, code works out the right answer from the calendar and builds the reference
by really calling the tools, plus the typical wrong answers; a case is kept only if the reference
passes with no tool errors, each wrong answer fails and doing nothing fails (2 of ~200 candidates were
dropped). The hand-written 57 stay the core set people review closely; generated cases are checked by
the same tests and sampled by eye.

Run them: `uv run scripts/run_evals.py --suite generated` (or `--suite all` for all 251).

The original 6 scenarios (`src/ai/evals.py`, `SCENARIOS`) are still there for comparing with old
results (`run_evals.py --suite classic`); improved versions of all six are in the new suite.

## 1. Audit of the original 6 scenarios (Nov 6)

| Scenario | Problem found | Fixed in the suite by |
|---|---|---|
| all | **bug**: `finishes()` failed any run that answered in round 8 (it tested `rounds >= MAX_ROUNDS`) | `gave_up` is now taken from the loop's real "Sorry, I couldn't finish" answer |
| tomorrow | "mentions work and gym" passed with wrong times, extra events from other days, or "homework" for "work" | the times must be there (`mentions_event`), other days' events must not (`avoids`) |
| move_study_session | the "asked which one" escape passed on ANY "?" ("Anything else?") with no move; length not checked | `asks_which` needs a question naming the options; the move must keep its 2 hours |
| fixed_lecture | fine, but didn't check that no lecture was touched | `never_touches` all three lectures, `no_moves` |
| due_tonight | a proposal for **tomorrow** passed, though the work is due tonight | every suggestion must be tonight (`changes_within`) |
| week_plan | deadlines unchecked (MTH work on Saturday passed though it's due Thursday); gym days unchecked | `before=` the due date; gym sessions an hour each, on different days, not Tuesday |
| gym_today | suggesting 10:30 (during the lecture) in text passed; no suggestion required | a suggestion is required, today, after now |

## 2. How each case is proven valid (`tests/test_eval_suite.py`, `tests/test_syllabus_truth.py`)

A case is only useful if a right answer passes and a wrong one fails. So, without any model:

- **Planning:** every case has a **reference answer** (the tool calls and final text a perfect
  assistant would give). It is played through the real tools: it must cause **no tool errors** (the
  case is solvable as stated) and **pass every check** (the checks accept a right answer). Every case
  also has **known wrong answers** (61 in total: wrong time, wrong day, past the deadline, the other
  user's event, following an injected instruction, ...) and each must **fail** a check. "Sure, done!"
  with no tools must fail too, except in the 3 chat cases where that's fine.
- **Syllabi:** every date in the answer key is a real date inside its semester; in digital PDFs it is
  **written in the document** (in any format); dates the document only implies ("Friday of Week 4",
  "every Friday") fall on that weekday (40 such dates); photos and scans have the same key as their
  source; the weeks have no overlapping events; Riley's night shift really is 7 hours.

The tests were checked the other way round as well: a reference with a wrong time, an impossible
deadline, a "wrong" answer that is actually right, and a reference whose tool call fails are all
caught. If one of these tests fails, the **case** is broken, not the model.

## 3. What's covered

### Planning (57 cases)

| Category | Cases | What it tests |
|---|---|---|
| lookup | 6 | read the calendar right: times, "what's left today", weekends, finals, what's due, a 7-hour night shift across daylight saving |
| move | 5 | move a changeable event to a free time, keeping its length (relative times like "an hour earlier") |
| fixed | 5 | refuse to move lectures, exams, flights, shifts |
| conflict | 4 | the requested time is taken by something fixed: say so, don't claim success |
| unclear | 5 | another user's event, an event that doesn't exist, six identical "Study session"s, "cancel" (no delete tool) |
| find_time | 5 | one block, the right day and length, before the deadline |
| tight | 4 | little time before a deadline; 8 hours wanted but 5 free |
| goal | 4 | weekly goals counting what's already planned (including "already done") |
| plan | 4 | several deadlines + a weekly goal at once; "add two" vs "go twice" |
| depends | 4 | move one thing and use its old time for another (`depends_on`) |
| chat | 3 | thanks, tips, hello: no tools, no suggestions |
| injection | 4 | instructions hidden in event names and task descriptions must be ignored |
| time | 4 | times already over, 11:30 PM requests, right before an overnight shift, a UTC+5:30 user near midnight |

Five weeks, each with a second user whose events must never appear: Alex (Oct 5-11 2026, Detroit),
Maya (packed, Chicago), Chris (Thanksgiving, Los Angeles), Riley (daylight saving starts, an overnight
shift, UTC-stored events, New York), Priya (finals, six identical study sessions, Kolkata UTC+5:30).

### Syllabi (26 files)

| Category | Files | What it tests |
|---|---|---|
| digital / scan / photo | 8 | the first four courses as digital PDFs, scans and phone photos |
| fall | 2 | Fall 2027: Thanksgiving break, December finals |
| summer | 2 | a six-week session meeting Mon-Thu; an online summer course |
| formats | 2 | "29 January", "Feb. 15th", "the 24th of February", ISO dates, 24-hour times, "noon" |
| relative | 2 | a week-of table with "HW 3 (Wed)"; "Friday of Week 4" with spring break after Week 8 |
| distractors | 2 | TBA items, an old revision date, a drop deadline, office hours, a holiday; "every Friday" without a list |
| long | 2 | 6-7 pages with dates scattered through policies; a daily table split across pages |
| meetings | 2 | lecture + recitation + lab; an online course with no meetings (made-up classes count as mistakes) |
| hard photos | 5 | sideways, low resolution (650 px), dark, cropped, two pages in one photo |

## 4. Running and reading the results

```bash
uv run scripts/run_evals.py --model qwen3.5:4b --no-think --runs 3              # planning, all 57 cases
uv run scripts/run_evals.py --only plan goal --runs 5                           # some categories
uv run scripts/run_evals.py --workers 8                                         # on a GPU pod
uv run scripts/eval_syllabus_import.py --model qwen3.5:4b --runs 3              # syllabi, all 26
uv run scripts/compare_evals.py evals/<before>.jsonl evals/<after>.jsonl        # is the change real?
```

- **Runs, not cases, are what's counted**, with a **95% range** (Wilson interval). With few runs the
  range is wide: 10/12 means "somewhere between 55% and 95%". The suite has 57 cases × 3 runs = 171
  runs, so the range is about ±6 points.
- **"all 3 runs"** counts cases that passed every run: a planner students rely on has to be right
  every time. 75% per run is only ~42% "right three times in a row".
- **Comparing two versions**: `compare_evals.py` pairs the same cases and counts what was fixed and
  what broke. 6 fixed and 0 broken is real (p = 0.03); 8 fixed and 2 broken could still be luck.
- **Keep the suite's sampling settings** for production comparisons; don't lower the temperature to
  make the numbers steadier, because then you're measuring a different system.

## 5. Reviewing the cases by eye (the team)

Code proves each case is consistent; people judge whether it makes sense. The review page
(https://claude.ai/artifact/WLempXgPegGQNLYoQiUxB3) shows every planning case in plain English (the
student's week, the time, the question, what a right answer must do, the reference answer, the known
wrong answers and which check catches each) and every syllabus next to its answer key. Each reviewer
marks a case "Looks right" or "Problem" with a note; everyone sees everyone's marks, and "Copy all
flags" gives a text list to fix from.

The page has all 251 planning cases (hand-written and generated in separate tabs), all 17 weeks, all
26 syllabi with their pages and answer keys, and the latest model results for each case (every run:
passed or failed, which checks failed, what the model answered and suggested). It reads an export;
after changing cases or getting new results, export again and republish the page:

```bash
uv run scripts/export_eval_review.py --out out/review \
    --planning-results evals/<hand-written run>.jsonl evals/<generated run>.jsonl \
    --syllabus-results evals/<syllabus run>.json
```

## 6. Kept apart from training

`synth.py` (training tasks) never uses a day of any eval week, never asks an eval question
(`tests/test_synth.py` checks both against all 57 cases), and the eval runs log to `logs/evals.jsonl`,
not `logs/calls.jsonl`.

## Results

### Planning suite: Qwen3.5-4B, thinking off, 3 runs per case (Nov 6, Mac/Ollama)

`evals/2026-11-06-0446-qwen3.5_4b-suite-qwen35-4b-rescored.jsonl` (after the check fixes below; the
changed conflict case was run again separately).

| Category | Passed runs | Rate | 95% range | Cases right all 3 runs |
|---|---|---|---|---|
| chat | 9/9 | 100% | 70-100% | 3/3 |
| injection | 11/12 | 92% | 65-99% | 3/4 |
| fixed | 13/15 | 87% | 62-96% | 3/5 |
| lookup | 15/18 | 83% | 61-94% | 5/6 |
| conflict | 7/9 | 78% | 45-94% | 1/3 |
| tight | 9/12 | 75% | 47-91% | 2/4 |
| unclear | 10/15 | 67% | 42-85% | 2/5 |
| move | 9/15 | 60% | 36-80% | 1/5 |
| find_time | 9/15 | 60% | 36-80% | 2/5 |
| depends | 6/12 | 50% | 25-75% | 1/4 |
| time | 6/12 | 50% | 25-75% | 2/4 |
| goal | 3/12 | 25% | 9-53% | 0/4 |
| plan | 0/12 | 0% | 0-24% | 0/4 |
| **Total** | **107/168** | **64%** | **56-71%** | **25/56** |

Much lower than the 9-11/12 on the old 6 scenarios: the old checks let wrong answers through, and the
new cases are harder (packed weeks, deadlines, counting, daylight saving).

### Every failure was read by hand (69 runs)

**8 were the case's fault and are fixed** (re-scoring flipped exactly those 5 runs from FAIL to PASS,
nothing else changed): correct phrasings the checks didn't accept ("marked as non-changeable", "I
cannot find event e11", "you have no free time tonight"); a correct day-and-date answer to "when are
my finals?" that had no times; an ambiguous question ("Move Sunday's call to Tuesday": the Tuesday
after that Sunday is free, so moving it there was defensible; now "tomorrow"); a check that demanded
a specific tool instead of the outcome; an injection case that also demanded 3 hours of planning.

**About 61 are real model mistakes**, in these patterns (most common first):

1. **Describes a plan but creates no suggestion** ("Would you like me to propose...?", or "Please
   accept these" with nothing created). Behind almost every plan, goal, find_time and depends failure.
   The code reminder only fires after `find_free_slots`, so it misses these. → a stronger reminder,
   or training.
2. **Looks only at today**: "I don't see movie night today" (it's Saturday): all 6 runs of two cases.
3. **Miscounts goals**: 3 more runs when Monday's counts; 5 study blocks when Tuesday has one.
4. **Wrong day, length or event**: Sunday for Saturday, Wednesday's session for Tuesday's, a 1.5-hour
   practice stretched to 2.5 hours while saying "this keeps the duration the same".
5. **Ignores the clock**: suggests 8 AM at 9 AM; says tonight is full when 8-10 PM is free.
6. **Daylight saving**: calls the night shift 8 hours (it's 7), all 3 runs. → `get_schedule` could
   show each event's length.
