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

## A. GPU Pod

1. **GPU:** a 24 GB card (RTX 4090, RTX A5000, L4 or RTX 3090). The model is about 8 GB in BF16;
   the rest holds the 32K context. Speed per reply depends mostly on memory bandwidth (a 4090
   is much faster than an L4). Training later can use the same size of card.
2. **Template:** a RunPod PyTorch template. Add a volume (about 40 GB) mounted at `/workspace`,
   so the model isn't downloaded again after a restart.
3. **Expose HTTP port 8000** in the pod settings.
4. Open the pod's web terminal and run:

   ```bash
   export HF_HOME=/workspace/hf          # keep the model download on the volume
   pip install vllm                      # a few minutes the first time
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
- **Slow thinking is the main risk for chat.** On the Mac, planning questions took 1.5–8 minutes
  (about 27 tokens/s). A fast GPU should be several times faster; `run_evals.py` will tell you
  exactly how much.
