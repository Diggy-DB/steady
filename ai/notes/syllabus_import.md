# Syllabus import: reading PDFs and photos, and adding many items at once

Goal: a student uploads a syllabus (PDF or a photo of it) and Steady suggests every exam, deadline
and weekly class, which the student then accepts. Two questions, both tested on the Mac (M3 Pro,
18 GB, Ollama) on Nov 5–6:

1. Which free model reads syllabi best?
2. Can the agent add a big syllabus (17+ items) by itself, over several tool calls?

## The test set (`fixtures/syllabi/`)

Four made-up Spring 2027 syllabi in the formats students upload, with an answer key
(`truth.json`, 63 dated items, 6 weekly meetings). `make_syllabi.py` rebuilds them.

| File | Format | Items | What makes it hard |
|---|---|---|---|
| `a_cse260.pdf` | digital PDF, 3 pages | 17 | schedule table with dates like "2/18"; the 11:59 PM rule is on page 1 |
| `b_bs161.pdf` | digital PDF, 3 pages | 18 | dates inside paragraphs and a list; long policies; distractors (drop dates, office hours) |
| `c_mth234_photo.jpg` | phone photo | 17 | tilted, shadowed, blurry dense table |
| `d_phy183_scan.pdf` | scanned PDF, 2 pages | 11 | no text layer, crooked |

Scoring (`scripts/eval_syllabus.py`): an item counts as **found** if the model returned it with the
right date (and number: "HW 3" must be 3); **made up** = returned items that aren't in the
syllabus; **times** = found items with the right due/start time; **meetings** = weekly classes with
the right days, start and end. One run per setup, so small differences are noise.

## 1. Reading: which model?

Candidates that run free on a laptop (all in Ollama): **Qwen3.5** 4B and 9B (Feb–Mar 2026, read
images natively, Apache-2.0), **Gemma 4 E4B** (Google), **GLM-OCR** (0.9B, a dedicated OCR model,
used in front of a text model), and the current **Qwen3-4B-Thinking** (text only). Routes: *vision*
(pages as images), *text* (the PDF's text layer; digital PDFs only), *ocr* (GLM-OCR turns each page
into text, then the model reads the text).

| Model, route | Found | Made up | Times right | Meetings | Time (4 syllabi) |
|---|---|---|---|---|---|
| **Qwen3.5-4B, ocr** (GLM-OCR + 4B) | **63/63** | 0 | 57/63 | 4/6 | 254 s |
| Qwen3.5-9B, ocr | 63/63 | 0 | 57/63 | 4/6 | 362 s |
| **Qwen3.5-4B, vision** | 61/63 | 1 | 56/61 | **6/6** | **217 s** |
| Qwen3.5-9B, vision | 52/63 | 11 | 52/52 | 6/6 | 323 s |
| Gemma 4 E4B, vision | 11/63 | 51 | 2/11 | 2/6 | 140 s |
| *digital PDFs only (35 items):* | | | | | |
| **Qwen3.5-4B, text** | 34/35 | 0 | 34/34 | 3/3 | **82 s** |
| Qwen3.5-9B, text | 34/35 | 0 | 34/34 | 3/3 | 136 s |
| Qwen3-4B-Thinking (current), text | 35/35 | 0 | 35/35 | 3/3 | 668 s |

Per file, Qwen3.5-4B vision got the photo (17/17) and the scan (11/11) completely right; its misses
were on the long prose PDF (final exam on May 17 instead of May 3, the final paper). The 9B by
vision had the same weak spot, worse (7/18 on the prose PDF), and was perfect on the other three.
Gemma 4 E4B invented dates (shifted weeks, February 29) and is not usable here.

**Answer: Qwen3.5-4B** (`qwen3.5:4b`, 3.3 GB). Digital PDFs: read the text layer (34/35 in 82 s for
both). Photos and scans: send the page images (28/28 on the photo and the scan), or GLM-OCR first
(63/63 overall, a little slower and weaker on the class times). The current thinking model is just
as accurate on text but 8x slower and can't see images.

### What mattered more than the model

These four settings moved results from near zero to near perfect, so they belong in the real code:

1. **Sampling.** Ollama runs Qwen3.5 with its chat defaults (temperature 1.0, `presence_penalty`
   1.5). The presence penalty pushes the model away from repeating words, which breaks lists like
   "WebWork 1 … WebWork 14, 23:59, 23:59": items went missing and JSON broke (Qwen3.5-4B: 4/63).
   For extraction: temperature 0.3, top_p 0.8, top_k 20, **presence_penalty 0**, plus a length cap
   (`num_predict` 6144) so a model stuck repeating itself can't run forever.
2. **No constrained decoding.** Forcing the JSON schema with Ollama's `format` broke Qwen3.5's
   output (placeholders like `"{year}-{month}-{day}"`). Describe the shape with an example in the
   prompt instead, and parse the JSON out of the reply in code.
3. **No thinking** for extraction. Qwen3.5-4B with thinking on the photo: 24,000 tokens, 14 minutes,
   and made-up dates. Without thinking: 52 s and 17/17.
4. **The year.** Dates like "2/18" have no year; the prompt must say "use the semester's year".

## 2. Many steps: can the agent add a whole syllabus?

`scripts/syllabus_agent.py` runs the real agent loop (8 rounds) with the request "Please put all my
exams and due dates on my calendar" plus the syllabus, then scores the suggestions it created.

| Design | What the model must do | Result |
|---|---|---|
| **current** (the app's 4 tools) | one `propose_new_event` per item, each a time block that may not overlap | **0/17** for all three models: they asked `get_schedule` for the whole semester (limit: 14 days), proposed one lecture on the wrong day, said "let me continue…" and stopped |
| **batch** (prototype `propose_syllabus_items`: all items in one call; `propose_weekly_class`) | one call | 9–14/17: exams were rejected because the model put "7:00–8:20 PM" only into `end_time`, then it promised to fix them and stopped |
| **batch2** (same tool, fixed: `start_time`/`end_time` fields, "7:00 PM" accepted, rejections say exactly what to resend) | one call | **Qwen3.5-9B: 17/17 on the PDF and 17/17 on the photo, in one call, ~1 minute**. Qwen3.5-4B: 17/17 (PDF), 11/11 (scan), 13/18 (prose PDF), 0/17 (photo: read the year as 2026) |

So yes: the agent can add a whole syllabus, **but only with a batch tool**; with one tool call per
item it fails completely. Failure modes still seen with batch2, each with a fix:

| Failure | Seen in | Fix |
|---|---|---|
| Repeats the same failing `get_schedule` call until the round limit | 4B, 3 of 4 runs | guard in the loop: a repeated identical call that failed gets "you already tried this"; the 14-day error should suggest a valid range |
| Promises "I will fix those" and stops | batch runs | rejections say exactly what to resend (batch2); a loop reminder like the existing one if problems remain |
| Wrong year (2026) → everything "already over" | 4B, photo | the extraction step says "use the semester's year"; code notices "all dates are in the past" and asks to recheck |
| "11:59" without PM → 11:59 AM | 9B, photo | let the model copy times as written ("11:59 PM") and convert in code |
| Chat answer states wrong exam dates though the suggestions are right | 9B, photo | show the suggestion cards (from data); keep the model's text to "I suggested 17 items" |

## Follow-up (Nov 6): OCR or vision, and getting the 4B agent past its failures

Built the recommended design as a real module, **`src/ai/syllabus.py`** (tests:
`tests/test_syllabus_import.py`), and measured it end to end with `scripts/eval_syllabus_import.py`:
upload → suggestions, scored. The test set grew to **8 syllabi** (scanned copies of A, B and C and a
photo of D were added), 2 runs each, model Qwen3.5-4B, thinking off.

```
upload ──► 1. pages: PDF text layer (digital PDFs), else page images (scans, photos)    [code]
       ──► 2. read: ONE model call returns the syllabus as JSON                         [model]
       ──► 3. check: the year (from "Spring 2027"), 12-hour times ("11:59" → PM if the  [code]
              syllabus says PM), exams without times get the class time, impossible and past
              dates, duplicates, numbering of series ("quizzes due Jan 17, Jan 24, ...")
              and, when there's text: dates the model wrote that aren't in the syllabus get
              "please check", dates the syllabus has that weren't imported are listed
       ──► 4. suggest: deadlines, timed events and one weekly event per class, PENDING   [code]
```

### Question 1: GLM-OCR + Qwen3.5-4B, or Qwen3.5-4B reading the images?

Same pipeline, same code, on the 6 scans and photos × 2 runs (the 2 digital PDFs use their text
either way):

| Route for scans and photos | Items found | Made up | Times right | Weekly classes right | Time per syllabus |
|---|---|---|---|---|---|
| **Qwen3.5-4B reads the images** | 167/182 | 7 | 100% | **18/18** | **~40 s** |
| GLM-OCR → text → Qwen3.5-4B | 169/182 | 11 | 88% | 11/18 | ~57 s |

Items found were a tie. GLM-OCR lost on everything else: given a whole page it **silently skips
blocks** (the header with the lecture times disappeared, so classes and in-class quiz times were
wrong), it dropped table rows on the scanned MTH 234 schedule (11/17 both runs), and it's a second
model to run. Its one win was the scanned prose syllabus (18/18 vs 9–12/18), and that case is now
fixed in code (series numbering, below). **Use vision; drop GLM-OCR.** If OCR is ever needed, GLM-OCR
should be run with its layout-detection SDK, region by region, not on whole pages.

### Final pipeline results (vision for scans and photos)

| Version | Items found | Made up | Weekly classes | Perfect imports |
|---|---|---|---|---|
| v1: the checks above, no series support | 222/252 (88%) | 17 | 24/24 | 12/16 |
| v2: + series ("dates": [...]) and the not-imported list | 241/252 (96%) | 10 | 24/24 | 13/16 |
| v3: + renumbering a series named after its first item | scanned prose syllabus: **54/54 in 3 runs** (was 9–18/18) | 0 | 3/3 | 3/3 |

All of v1's misses were BS 161's sentence listing ten quiz dates: the model shifted dates and mixed
up numbers. Letting it return one item with a list of dates, numbered by code, fixed it. In v1 the
"please check" flag fired 7 times, all 7 on wrong items. v2's remaining misses: one misread row on
the photo (WW7 on 2/24 instead of 3/2), one missed final exam on a scan, and the numbering bug fixed
in v3.

### Question 2: the 4B as an agent

| How the agent adds a syllabus (Qwen3.5-4B) | Result |
|---|---|
| step by step, today's tools | 0/17 (all models) |
| batch tool (batch2) | 0–17/17, loops on failing calls until the round limit |
| batch2 + **loop guards** (repeated failing call refused; the 14-day error suggests a valid range) | the loops are gone (it followed the suggested ranges), but on the photo it then **paged through the whole semester two weeks at a time** and ran out of rounds: 0/17; scan 11/11 (no classes); prose 10/18 + 5 made up |
| **one tool, `import_syllabus(upload_id)`** (the pipeline above, in code) | **124/126 items, 1 made up, 12/12 weekly classes, over all 8 syllabi; one tool call and no errors every time; 41–71 s** |

So the way past the 4B's agent failures is not a bigger model or more reminders: **take the
multi-step work away from the model**. With `import_syllabus` the agent makes one decision (call
it), and code does the 20+ steps. The loop guards stay in `agent.py` (`call_key`, `REPEATED_CALL`,
`too_many_days` in `schedule.py`), because they help every tool.

## Recommended design (built: `src/ai/syllabus.py`)

- **Upload** in the app → the backend keeps the file for the request and gives the agent an
  `upload_id` → the agent calls `import_syllabus` → the student sees a review list of the
  suggestions (with "please check" marks and "not imported: Feb 21, Feb 28") and accepts.
- **Model**: Qwen3.5-4B, thinking off, the reading settings in `syllabus.SAMPLING`. Digital PDFs by
  their text layer, scans and photos as images. `Reader.for_server` switches thinking off for Ollama
  and vLLM alike.
- **Licenses**: `pypdfium2` (Apache/BSD) reads PDFs in the app; PyMuPDF (AGPL) is only used by the
  experiment scripts, through `--with`, so it never ships.
- The chat answer should not restate dates (the 9B once garbled them while the suggestions were
  right); the tool result tells the model to say how many items, which need checking, and to review.
- **Database (teammates' call, not done)**: `ai_suggestions.type` only allows CREATE_EVENT and
  MOVE_EVENT. Deadlines fit better as tasks (a CREATE_TASK type, or tasks with a due date), and a
  weekly class needs accepting a suggestion to write `calendar_events.recurrence_rule` (the column
  exists, "not used by the AI yet"). Uploads: process the file in memory, or a private Supabase
  Storage bucket with RLS if it must be kept.

### A bigger implication

Qwen3.5 reads images, and Qwen reports much stronger agent scores than our current model
(TAU2-Bench: Qwen3.5-4B 79.9, Qwen3.5-9B 79.1). If it also passes our 6 planning scenarios, **one
model could do everything** and the training plan would move to Qwen3.5. Not decided: it needs the
eval suite run on Qwen3.5 first, and vLLM serves it with a different tool-call parser
(`qwen3_coder`), so the training format changes too.

## Limits

- Made-up syllabi (4 courses, 8 files, 126 items) and 1–3 runs per setup; randomness matters (the
  9B read the photo perfectly in one run and returned broken JSON in another before the settings
  fix). Real syllabi from club members would be the best next test set.
- Not wired into the API or the frontend yet: that needs an upload endpoint and the database
  decisions above (deadlines as tasks, accepting a weekly class).
- Everything ran on the Mac via Ollama; vLLM on a GPU should give the same accuracy, faster.
- Disk: the test models take ~18 GB (`ollama rm gemma4:e4b qwen3.5:9b glm-ocr:q8_0` frees ~15 GB).

## Run it

```bash
uv run scripts/eval_syllabus_import.py --model qwen3.5:4b --runs 2                   # the pipeline, end to end
uv run scripts/syllabus_agent.py --model qwen3.5:4b --design import --syllabus c_mth234_photo.jpg --no-think
uv run --with pymupdf scripts/eval_syllabus.py --model qwen3.5:4b --route vision    # reading only: or text / ocr
uv run --with pymupdf scripts/syllabus_agent.py --model qwen3.5:9b --design batch2 --syllabus c_mth234_photo.jpg --route vision --no-think
uv run --with reportlab --with pymupdf --with pillow python fixtures/syllabi/make_syllabi.py variants   # rebuild the scans/photo copies
```

Results are in `evals/2026-11-06-*-syllabus-*.json`.

Sources: [Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B) (benchmarks, settings),
[Ollama qwen3.5](https://ollama.com/library/qwen3.5), [Ollama glm-ocr](https://ollama.com/library/glm-ocr),
[Ollama gemma4](https://ollama.com/library/gemma4), [Ollama OpenAI compatibility](https://docs.ollama.com/openai)
(`reasoning_effort: "none"` turns thinking off), a community IDP comparison of Gemma 4 E4B and
Qwen3.5-4B ([Reddit snapshot](https://reddit.sentinel-team.org/posts/1sfrb4i/snapshots/2026-04-09T17%3A23%3A43.391309Z)),
and Anthropic's [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents).
