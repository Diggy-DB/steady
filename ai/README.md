# Steady Planner: AI service

The AI part of Steady Planner: a planning assistant (Qwen3-4B-Thinking) that can read the
user's calendar and tasks, find free time, and **propose** changes. It never changes the
calendar itself: every change is a pending suggestion the user accepts or declines, and every
rule (no past times, no overlaps, fixed events stay fixed, only the user's own data) is checked
in code, not left to the model.

## Layout

| Path | What it is |
|---|---|
| `src/ai/llm.py` | talking to any OpenAI-compatible model server (Ollama, vLLM, RunPod) |
| `src/ai/schedule.py` | the data store interface, the fake week, `get_schedule` |
| `src/ai/planning.py` | `find_free_slots`, the shared checks, `propose_new_event`, `propose_move_event`, `recheck` |
| `src/ai/agent.py` | the agent loop and system prompt |
| `src/ai/memory.py` | long-term memory with Mem0 (facts learned from chats and journals) |
| `src/ai/supabase_store.py` | the same store interface on Supabase's REST API |
| `src/ai/server.py` | the HTTP API for the frontend/backend |
| `src/ai/evals.py` | eval scenarios (the **test set**) and their checks |
| `src/ai/synth.py` | synthetic tasks for **training** data (kept apart from the evals) |
| `fixtures/week.json` | the fake week (Oct 5–11, 2026) used by demos and evals |
| `scripts/` | command-line tools (below) |
| `evals/` | saved eval results, one file per run of the suite |
| `notes/` | what was built at each stage, results, and decisions |

## Setup

```bash
cd ai
uv sync                       # install everything
cp .env.example .env          # then pick a model server in .env
OLLAMA_CONTEXT_LENGTH=32768 ollama serve      # in its own terminal, for the local model
ollama pull qwen3:4b-thinking-2507-q8_0       # the chat model (4.3 GB, once)
ollama pull nomic-embed-text                  # the embedding model for long-term memory (274 MB, once)
```

## Commands (run from `ai/`)

| Command | What it does |
|---|---|
| `uv run pytest` | all tests (no model needed) |
| `uv run scripts/chat.py "What do I have tomorrow?"` | ask a question about the fake week; prints pending suggestions |
| `uv run scripts/run_evals.py --runs 3` | run the eval suite (57 cases); pass rates per category with 95% ranges, saves to `evals/` |
| `uv run scripts/compare_evals.py <a> <b>` | is version B really better than A, or luck? (same cases, paired) |
| `uv run scripts/export_eval_review.py` | export every eval case in plain English for the team's review page |
| `uv run uvicorn ai.server:app --port 8000` | start the API (demo mode); docs at http://localhost:8000/docs |
| `uv run scripts/check_server.py` | check a model server (run after deploying to RunPod) |
| `uv run scripts/collect_traces.py --tasks 20` | collect training examples into `data/` |
| `uv run --with pymupdf scripts/eval_syllabus.py --model qwen3.5:4b` | score a model on reading the test syllabi |
| `uv run scripts/eval_syllabus_import.py --model qwen3.5:4b` | score the syllabus import pipeline (`src/ai/syllabus.py`) end to end |
| `uv run scripts/train_lora.py --check` | count the training data's tokens (training itself runs on a GPU pod) |
| `bash deploy/make_pod_bundle.sh` | pack the code for a RunPod pod (`deploy/runpod_train.sh` runs the whole training session there) |

## Notes, in order

1. `notes/stage0.md`: talking to the model, first measurements
2. `notes/stage1.md`: the first tool and the agent loop
3. `notes/stage2.md`: free time, checks, proposals, and the suggestion format
4. `notes/stage3.md`: the eval suite, the baseline, and what improved it
5. `notes/stage4_runpod.md`: deploying the model on RunPod
6. `notes/stage5_api.md`: the API, for the frontend and backend teams
7. `notes/training.md`: collecting training data, fine-tuning, and the training session
8. `notes/memory.md`: long-term memory (Mem0)
9. `notes/syllabus_import.md`: reading syllabus PDFs and photos, and adding many items at once
10. `notes/evals_suite.md`: the eval suites (57 planning cases, 26 syllabi), how each case is proven valid, how to read the numbers
11. `notes/team_test.md`: the team test: the website on GitHub Pages, the AI on RunPod (`deploy/runpod_app.sh`), the data in Supabase
