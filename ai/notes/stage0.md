# Stage 0 notes

Goal: talk to the model locally, understand the request/response, and record
baseline numbers for later comparison (prompt changes, RunPod, training).

## Setup

| | |
|---|---|
| Machine | MacBook Pro, Apple M3 Pro, 18 GB (Ollama sees 13.3 GiB for the GPU) |
| Server | Ollama 0.32.5, started with `OLLAMA_CONTEXT_LENGTH=32768 ollama serve` |
| Model | `qwen3:4b-thinking-2507-q8_0` (4.3 GB download) |
| Loaded size | 9.2 GB at 32K context, 100% GPU |
| Ollama defaults | temperature 0.6, top_k 20, top_p 0.95, repeat_penalty 1 (matches Qwen's recommendation) |

## How the response is shaped (Ollama, OpenAI-compatible endpoint)

- Thinking comes back in `choices[0].message.reasoning`, separate from `content`.
  vLLM uses `reasoning_content` (newer versions may use `reasoning`), so handle both.
- `usage.completion_tokens` counts thinking + answer together. There is no
  separate reasoning count; the script estimates it by counting streamed chunks (about 1 token each).
- `finish_reason: "stop"` = finished on its own; `"length"` = cut off by `max_tokens`.

## Run 1: first curl, no system prompt

- When: 2026-10-05 14:15 EDT
- Question: "I have class 10am-12pm and a 3-hour assignment due tonight. When should I work on it?"
- System prompt: none (model was not told the date or time)

| prompt tokens | completion tokens | finish_reason | time |
|---|---|---|---|
| 37 | 2,389 | stop | not measured (~1.5 min estimated at ~25 tok/s) |

By length, roughly half the completion was thinking and half was the answer (not measured).

Observations:

1. **No sense of time.** The thinking went in circles ("*checks mental clock*",
   "I'm getting tangled"), and the answer has errors: it says class is
   *tomorrow* (never stated), says to finish "by 3–4 PM (before your class
   starts)" when class is 10–12, and calls noon "early morning".
   → Put the current date, time and timezone in the system prompt.
2. **Very long.** About 1,100 answer tokens of tables, emojis and headings for
   a simple question. → First lever: a system prompt asking for short,
   plain answers. Shrinking the thinking is the harder part (training later).
3. **Makes things up.** "90% of students do this correctly", "Most students
   finish in 2–2.5 hours", guesses the user is a high schooler.
   → System prompt: don't invent statistics; later, an eval check.
4. **Missing spaces: not real.** Copy-paste artifact: the terminal drops the space
   where it wraps a long line. The log has the spaces (see Finding 5).

Good: it ended by asking whether "tonight" meant today or tomorrow. That's
the right instinct for an ambiguous request, but it should ask *instead of*
guessing.

## Run 2: script, with date/time in the system prompt

- When: 2026-10-05 16:43 EDT. System prompt: "Current date and time: Monday October 5, 2026, 4:43 PM (America/Detroit)."
- Same question as Run 1.

| prompt | completion | thinking / answer | first token | answer starts | total | speed | finish |
|---|---|---|---|---|---|---|---|
| 69 | 2,359 | ~1,719 / ~628 | 4.49 s | 66.19 s | 90.04 s | 27.6 tok/s | stop |

Observations:
1. Tonight/tomorrow confusion gone, but it **ignored the current time**: recommended
   12pm–3pm when it was already 4:43 PM ("the current date ... probably not relevant here").
   → Stating a fact isn't enough; compute "what's left of today" in code (Stage 1).
   → First eval check: never suggest a time in the past.
2. 73% of tokens were thinking, mostly "Wait," loops. Answer took 66 s to start.
3. Answer shorter than Run 1 but still emojis/headings and invented claims.
4. (Corrected) The missing spaces were a terminal copy-paste artifact, not the model.

## Experiment 1: same question, 5 runs (6:26–6:32 PM)

| run | thinking | answer | answer starts | total | recommendation | correct? |
|---|---|---|---|---|---|---|
| 1 | ~1,437 | ~1,107 | 54.5 s | 97.8 s | start now, but "class is tomorrow"; only 2.25 h planned | partly |
| 2 | ~805 | ~1,086 | 29.0 s | 69.0 s | 7–9 AM or 1–3 PM (already past) | no |
| 3 | ~919 | ~1,109 | 33.1 s | 74.4 s | 12:30–3:30 PM (already past); fake citations | no |
| 4 | ~1,414 | ~954 | 51.4 s | 87.3 s | start now, but "class is tomorrow" | partly |
| 5 | ~2,040 | ~780 | 75.3 s | 105.0 s | start now (6:32), finish 9:32 | yes |

- Thinking varied 2.5× for the same question → evals must repeat each scenario.
- Only the longest-thinking run was fully correct. Small sample, but training for shorter
  thinking must keep only correct runs and measure correctness alongside tokens.

## Experiment 2: "What's the date tomorrow?"

| system prompt | tokens | total | answer | correct? |
|---|---|---|---|---|
| no date | 481 | 17.6 s | can't know, "cutoff 2023" (thinking first guessed Oct 26, 2023) | honest |
| with date | 611 | 22.4 s | Tuesday, October 6, 2026 | yes |

→ The date in the prompt works for direct questions; Experiment 1 shows knowing ≠ using.

## Experiment 3: easy vs hard (6:35 PM)

| question | thinking | answer | answer starts | total | problems |
|---|---|---|---|---|---|
| easy: gym, nothing scheduled | ~448 | ~696 | 17.5 s | 43.4 s | all 3 suggested windows already past; invented Detroit weather |
| hard: week schedule | ~1,925 | ~1,156 | 69.7 s | 113.4 s | Fri assignment 10–1 overlaps Fri class while claiming "zero conflicts"; Mon 8–9 AM gym already past; backup plan reuses a taken slot |

## Experiment 4: Instruct vs Thinking (Tue Oct 6, 10:39–10:43 AM)

| run | model | completion tokens | answer starts | total | recommendation | valid? |
|---|---|---|---|---|---|---|
| class ×3 | instruct | 424 / 372 / 533 | 13.0* / 0.2 / 0.3 s | 29 / 14 / 22 s | 12–3 PM | yes ×3 |
| class ×1 | thinking | 1,991 (756 + 1,215) | 34.5 s | 87 s | 12–3 PM | yes (but "text your teacher now" during class) |
| gym | instruct | 477 | 0.4 s | 20 s | 6–7 PM | yes |
| hard week | instruct | 1,046 | 0.5 s | 44 s | invented Tue/Thu class; Thu assignment overlaps work; Mon gym already past; claims no conflicts | no |

*includes ~13 s loading the model (Ollama swaps models; both don't fit at 32K context).

- Not comparable with Experiment 1: at 10:40 AM "after class, 12–3 PM" is the easy, obvious
  answer; in the evening those times had already passed.

## Findings so far

1. Past times: 5 of 8 planning answers recommended a time that had already passed.
2. Conflicts: claimed "zero conflicts" with a real overlap → conflict checks must be code (Stage 2).
3. Invents facts: "class is tomorrow", fake citations with links, weather/commute claims.
4. Time: steady ~27 tok/s; first token 0.2–0.4 s when loaded (~4.5 s cold). Time ≈ tokens ÷ 27.
   Thinking is 39–73% of tokens, but answers alone are 630–1,160 tokens (23–43 s).
5. Missing spaces were a terminal copy-paste artifact; the log is correct.
6. Instruct: 4–6× fewer tokens and the answer starts at once; same quality on simple
   questions. It also fails the hard schedule, so constraint checking must be code either way.
7. Time of day changes how hard a question is → evals need a fixed fake "now", not the real clock.
8. To test in Stage 3: if code does the time math and conflict checks, is Instruct good enough?
