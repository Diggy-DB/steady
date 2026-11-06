# Stage 4: running the model on RunPod

Everything here is ready except the steps that need your RunPod account (creating a pod or
endpoint, and paying for it). Nothing in the code changes: only the three `LLM_*` values in
`.env` point somewhere else.

```
Frontend ─► Backend ─► AI service (ai/src/ai/server.py, runs on your laptop or next to the backend)
                         │   tools, checks, suggestions, Supabase access
                         ▼
               RunPod: vLLM serving Qwen3-4B-Thinking-2507 (only turns text into text)
```

The RunPod machine never gets database keys and never runs tools.

## Which RunPod option

| | GPU Pod | Serverless (worker-vLLM) |
|---|---|---|
| Billing | per hour while it's on, **even when idle** | per second while a worker runs; nothing when idle |
| First request | instant once started | cold start (worker + model load) after quiet periods |
| Best for | measuring speed, running evals, collecting training data, the training itself | the deployed app |

Suggested order: **Pod first** (evals + training-data collection in one session), then
**Serverless** for the app.

## The GPU session, step by step (about 2–3 hours of GPU time)

> The **training session** (collect → fine-tune → compare) is one script now:
> `deploy/runpod_train.sh`, described in `notes/training.md`. The steps below are for serving
> the model to a laptop and measuring it by hand.

The GitHub repo is private, so the pod can't clone it. Pack the code on the Mac and upload it:

1. On the Mac: `bash ai/deploy/make_pod_bundle.sh` writes `~/Downloads/steady-pod.tar.gz` (code
   only: no `.env`, logs, data or memory).
2. On RunPod, create a pod (see A below for the GPU, template and ports), open Jupyter Lab and
   drag the file into its file list (it lands in `/workspace`).
3. In a Jupyter terminal:

   ```bash
   cd /workspace && tar xzf steady-pod.tar.gz && bash steady/ai/deploy/runpod_pod.sh
   ```

It installs vLLM, starts the **thinking** model and prints three `LLM_…` lines. Paste them into
`ai/.env` on your laptop. Then, on the laptop, from `ai/`:

| # | Command | What you learn |
|---|---|---|
| 1 | `uv run scripts/check_server.py` | all PASS = the server is set up right |
| 2 | `uv run scripts/run_evals.py --runs 3 --label runpod-thinking` | pass rate and speed on a GPU (Mac: 11/12, planning up to 15 min) |
| 3 | `uv run scripts/collect_traces.py --tasks 200 --samples 4 --start 1000 --workers 8` | training data in `data/` (for fine-tuning); `--workers 8` runs 8 tasks at once, which vLLM handles well |
| 4 | In the pod: Ctrl+C, then `MODEL=Qwen/Qwen3-4B-Instruct-2507 bash steady/ai/deploy/runpod_pod.sh`; update `LLM_MODEL` in `ai/.env` | |
| 5 | `uv run scripts/check_server.py --no-thinking` then `uv run scripts/run_evals.py --runs 3 --label runpod-instruct` | is the faster no-thinking model good enough? |
| 6 | **Stop the pod** | it bills while it's on |

Long-term memory follows `LLM_BASE_URL` too (Mem0 uses the same server), so memory updates
also run on the GPU. Its small embedding model (`nomic-embed-text`) stays in Ollama on the
laptop, so keep `ollama serve` running there.

## A. GPU Pod

1. **GPU:** a 24 GB card (RTX 4090, RTX A5000, L4 or RTX 3090). The model is about 8 GB in BF16;
   the rest holds the 32K context. Speed per reply depends mostly on memory bandwidth (a 4090
   is much faster than an L4). Training later can use the same size of card.
2. **Template:** a RunPod PyTorch template. A volume at `/workspace` is optional. Without one,
   the model downloads again after each restart (a few minutes), but nothing bills while the pod
   is off. Add one for the long training session.
3. **HTTP ports: 8888 and 8000**, as two rows in the pod settings. 8888 is Jupyter, the easiest
   terminal; replacing it with 8000 loses the terminal. Set them before deploying: editing a
   running pod restarts it and wipes everything outside the volume.
4. Open Jupyter Lab → File → New → Terminal and run (or use `deploy/runpod_pod.sh`, which does
   the same):

   ```bash
   mkdir -p /workspace && cd /workspace  # missing when the pod has no volume
   export HF_HOME=/workspace/hf          # keep the model download on the volume
   # vLLM in its own environment: plain `pip install vllm` fails on the Ubuntu 24.04 image
   PIP_BREAK_SYSTEM_PACKAGES=1 pip install -q uv
   uv venv --python 3.12 --managed-python venv && uv pip install --python venv/bin/python vllm
   source venv/bin/activate
   vllm serve Qwen/Qwen3-4B-Thinking-2507 \
     --max-model-len 32768 \
     --reasoning-parser deepseek_r1 \
     --enable-auto-tool-choice --tool-call-parser hermes \
     --api-key <make-up-a-long-random-secret> \
     --port 8000
   ```

   - `--reasoning-parser deepseek_r1` is what Qwen's model card uses for this model: its output has
     `</think>` but no opening `<think>`, and this parser handles that.
   - The model card also shows `--enable-reasoning`; current vLLM doesn't need (or accept) it.
   - `--api-key` matters: the pod's URL is public.
5. On your Mac, point `.env` at the pod (template in `.env.example`):

   ```
   LLM_BASE_URL=https://<POD_ID>-8000.proxy.runpod.net/v1
   LLM_API_KEY=<the secret from step 4>
   LLM_MODEL=Qwen/Qwen3-4B-Thinking-2507
   ```

6. Check it, then measure it (from `ai/`):

   ```bash
   uv run scripts/check_server.py                       # all PASS before going on
   uv run scripts/run_evals.py --runs 3 --label runpod  # compare with the Mac baseline in notes/stage3.md
   ```

   If `check_server.py` says FAIL, it prints which vLLM flag to fix.
7. **Stop the pod when you're done.** It bills while it's on.

## First GPU test (Nov 5): RTX 4090, thinking model, vLLM

Setup to first answer took about 10 minutes (install, then download). `check_server.py`: all
PASS, **97 tokens/s** for one request, against about 27 on the Mac. Then the whole eval suite
(6 scenarios × 2 runs) ran with the 6 scenarios **at the same time**, which vLLM handles:
**4 minutes in all, against 66 on the Mac**, about $0.06 of GPU time.

| Scenario | Mac (Ollama, 8-bit) | 4090 (vLLM, BF16) | Avg time (Mac → 4090) | Avg tokens (Mac → 4090) |
|---|---|---|---|---|
| tomorrow | 2/2 | 2/2 | 55 s → 15 s | 1,197 → 1,165 |
| move_study_session | 2/2 | 2/2 | 131 s → 36 s | 3,310 → 2,815 |
| fixed_lecture | 2/2 | 2/2 | 87 s → 37 s | 2,156 → 2,881 |
| due_tonight | 2/2 | 1/2 | 428 s → 121 s | 10,493 → 9,823 |
| week_plan | 1/2 | **0/2** | 909 s → 114 s | 16,550 → 9,280 |
| gym_today | 2/2 | 2/2 | 367 s → 49 s | 9,176 → 3,805 |
| **Total** | **11/12** | **9/12** | | |

- **Speed is solved by the GPU**: every answer took under 2.5 minutes, and simple questions
  10–40 s. With 6 requests at once each still got about 80 tokens/s.
- **Planning quality is not**: same model, same weak spot. week_plan failed both times:
  - once the model wrote its four proposals *inside its thinking* and never closed it, so vLLM
    treated them as thinking and no suggestion was made;
  - once it decided the existing study sessions "cover" the assignments and proposed nothing.

  due_tonight failed once by running out of rounds (it kept re-proposing moves). With 2 runs
  each, 9/12 against 11/12 is within chance; the planning failures match the Mac's.
- The model also writes tool calls inside its thinking with Ollama (11 of 88 turns in the logs);
  usually it repeats them after the thinking, which is why it rarely mattered there.
- Lessons for the setup (already in the steps above and `deploy/runpod_pod.sh`): install vLLM with
  uv in its own environment; `mkdir -p /workspace` without a volume; expose 8888 *and* 8000.

## B. Serverless endpoint

1. In the RunPod console, deploy **worker-vLLM** from the RunPod Hub.
2. Environment variables:

   | Variable | Value |
   |---|---|
   | `MODEL_NAME` | `Qwen/Qwen3-4B-Thinking-2507` |
   | `MAX_MODEL_LEN` | `32768` |
   | `ENABLE_AUTO_TOOL_CHOICE` | `true` |
   | `TOOL_CALL_PARSER` | `hermes` |
   | `REASONING_PARSER` | `deepseek_r1` |

   Turn on RunPod's model caching so cold starts don't download the model.
3. `.env`:

   ```
   LLM_BASE_URL=https://api.runpod.ai/v2/<ENDPOINT_ID>/openai/v1
   LLM_API_KEY=<your RunPod API key>
   LLM_MODEL=Qwen/Qwen3-4B-Thinking-2507
   ```

4. `uv run scripts/check_server.py` twice: the first run shows the cold start, the second the
   normal speed. For a demo, set one **active worker** during the demo so nobody waits for a
   cold start, then set it back to zero.

## Things to know

- **Keys:** the RunPod key and pod secret live only in `.env` (git-ignored) and on the server
  running the AI service. Never in the frontend.
- **Privacy:** chat messages (and later journal text) are sent to the model server. It's your
  own deployment, but keep the server's logs private.
- **Local results won't match exactly:** RunPod runs the full BF16 model with vLLM; your Mac runs
  an 8-bit copy with Ollama. Re-run the evals there instead of assuming.
- **Slow thinking was the main risk for chat.** On the Mac, planning questions took 1.5–15
  minutes (about 27 tokens/s). On an RTX 4090 they took under 2.5 minutes (97 tokens/s); see
  "First GPU test" above.
- **The pod's proxy cuts requests at about 100 s.** One model reply (not a whole chat) must
  finish within that. At 97 tokens/s that is ~9,000 tokens of thinking; Nov 5's longest single
  reply was ~3,300. If `check_server.py` or a chat ever fails with a 524 error, this is why.
