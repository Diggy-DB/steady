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
  separate reasoning count, so measure it with the tokenizer.
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
4. **Missing spaces.** "tounpack", "assumeit's", "from10am", "notin bursts".
   Not caused by sampling settings (defaults match Qwen's). Cause unknown:
   the model or Ollama. → Check whether it still happens on vLLM.

Good: it ended by asking whether "tonight" meant today or tomorrow. That's
the right instinct for an ambiguous request, but it should ask *instead of*
guessing.

## Experiments (fill in from your script)

### 1. Same question, 5 runs

| run | reasoning tokens | answer tokens | seconds | answer summary |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

### 2. "What's the date tomorrow?" with and without the date in the system prompt

| system prompt | answer | correct? |
|---|---|---|
| no date | | |
| with date/time/timezone | | |

### 3. Easy vs hard question

| question | reasoning tokens | answer tokens | seconds |
|---|---|---|---|
| easy: | | | |
| hard: | | | |

### 4. Thinking vs Instruct (`qwen3:4b-instruct-2507-q8_0`)

| model | question | completion tokens | seconds | quality notes |
|---|---|---|---|---|
| thinking | | | | |
| instruct | | | | |

## Open questions

- Where does the time go: loading the model, thinking, or the answer? (Streaming will show this.)
- Are the missing spaces from the model or from Ollama?
