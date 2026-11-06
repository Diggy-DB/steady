#!/usr/bin/env bash
# The whole training session on one RunPod GPU pod, about 2 hours (~$2 on an RTX 4090):
#   1. install vLLM, the Steady code and the training libraries
#   2. collect training examples: the model tries synthetic tasks, the shortest passing tries are kept
#   3. fine-tune the model on them with LoRA (scripts/train_lora.py)
#   4. run the eval suite on the original model and the fine-tuned one, at the same time
#   5. print a comparison and pack everything into /workspace/steady-results.tar.gz to download
#
# On the Mac: bash ai/deploy/make_pod_bundle.sh, then upload ~/Downloads/steady-pod.tar.gz to
# /workspace in Jupyter. In a Jupyter terminal:
#   cd /workspace && tar xzf steady-pod.tar.gz && nohup bash steady/ai/deploy/runpod_train.sh > session.log 2>&1 &
#   tail -f /workspace/session.log
#
# It keeps going if the browser is closed. Running it again skips the steps already done.
# When it ends (or fails), the pod stops itself an hour later unless /workspace/keep-running exists.
# Settings (environment variables, defaults in brackets): TASKS [200] MINUTES [60] SAMPLES [4]
# WORKERS [12] START [1000] EVAL_RUNS [3] TRAIN_ARGS [""], e.g. TRAIN_ARGS="--skip-reminded".
set -euo pipefail

TASKS="${TASKS:-200}"          # at most this many synthetic tasks...
MINUTES="${MINUTES:-60}"       # ...or as many as fit in this many minutes of collecting
SAMPLES="${SAMPLES:-4}"        # tries per task; the shortest passing one is kept
WORKERS="${WORKERS:-12}"       # tasks at the same time
START="${START:-1000}"         # first task seed; use new seeds for new data
EVAL_RUNS="${EVAL_RUNS:-3}"    # runs per eval scenario, for each model
TRAIN_ARGS="${TRAIN_ARGS:-}"

W=/workspace
AI="$W/steady/ai"
VENV="$W/venv"               # vLLM's own environment
OUT="$W/results"
BASE=Qwen/Qwen3-4B-Thinking-2507
LORA=steady-lora             # the name the fine-tuned model gets on the server
PEFT=peft==0.21.2            # the version the training script was tested with
export HF_HOME="$W/hf" PIP_BREAK_SYSTEM_PACKAGES=1 UV_LINK_MODE=copy
mkdir -p "$OUT"
cd "$AI"

log() { echo; echo "[$(date +%H:%M)] $*"; }

stop_pod_later() {
  echo
  echo "To save money, this pod stops itself in 60 minutes. To keep it running: touch $W/keep-running"
  sleep 3600
  [ -f "$W/keep-running" ] && return
  if command -v runpodctl > /dev/null && [ -n "${RUNPOD_POD_ID:-}" ]; then
    runpodctl stop pod "$RUNPOD_POD_ID"
  else
    echo "Couldn't stop the pod by itself: stop it in the RunPod console."
  fi
}

fail() {
  echo
  echo "FAILED: $*"
  echo "Send Claude the lines above (or the end of the file named there). Fix, then run the same command again."
  stop_pod_later
  exit 1
}

# Only one session at a time: a new run replaces an older one that's still waiting or stuck.
if [ -f "$W/session.pid" ] && kill -0 "$(cat "$W/session.pid")" 2> /dev/null; then
  kill "$(cat "$W/session.pid")" 2> /dev/null || true
fi
echo $$ > "$W/session.pid"
rm -f "$W/keep-running"

SERVER=""
start_server() {  # any extra vLLM flags as arguments
  nohup "$VENV/bin/vllm" serve "$BASE" --max-model-len 32768 \
    --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser deepseek_r1 \
    --api-key "$KEY" --port 8000 "$@" > "$OUT/vllm.log" 2>&1 &
  SERVER=$!
  until curl -s localhost:8000/v1/models > /dev/null; do
    kill -0 "$SERVER" 2> /dev/null || { tail -25 "$OUT/vllm.log"; fail "starting the model server ($OUT/vllm.log)"; }
    sleep 5
  done
}

free_gpu() {  # stop any model server and wait until the GPU's memory is free
  [ -n "$SERVER" ] && kill "$SERVER" 2> /dev/null || true
  pkill -f "vllm serve" 2> /dev/null || true
  for _ in $(seq 30); do
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
    [ "$used" -lt 2000 ] && return
    sleep 2
  done
  pkill -9 -f -i "vllm|EngineCore" 2> /dev/null || true
  sleep 5
}

# --- 1. Install ---------------------------------------------------------------------------------
log "1/5 Installing (5-8 minutes the first time). GPU: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"
command -v uv > /dev/null || pip install -q uv || fail "installing uv"
if [ ! -x "$VENV/bin/vllm" ]; then
  # Its own environment: a plain `pip install vllm` fails on RunPod's Ubuntu 24.04 PyTorch image.
  rm -rf "$VENV"  # a half-finished earlier install
  { uv venv -q --python 3.12 --managed-python "$VENV" && uv pip install -q --python "$VENV/bin/python" vllm; } \
    || fail "installing vLLM"
fi
uv sync -q || fail "installing the Steady code"
# The training libraries come with `uv run --with` (as on the laptop). Fetch them now, so a problem
# shows up before the long collection rather than after it.
uv run -q --with torch --with "$PEFT" python -c "import torch, peft; assert torch.cuda.is_available(), 'no GPU'" \
  || fail "installing the training libraries"

[ -f "$W/vllm_api_key" ] || python3 -c "import secrets; print(secrets.token_urlsafe(32))" > "$W/vllm_api_key"
KEY="$(cat "$W/vllm_api_key")"
cat > .env << EOF
LLM_BASE_URL=http://localhost:8000/v1
LLM_API_KEY=$KEY
LLM_MODEL=$BASE
MEMORY=off
EOF

# --- 2. Collect -----------------------------------------------------------------------------------
if [ ! -f "$OUT/collect.done" ]; then
  log "2/5 Collecting training examples: up to $TASKS tasks x $SAMPLES tries, $WORKERS at a time, for at most $MINUTES minutes"
  free_gpu  # a server left over from an earlier attempt would hold the port
  start_server
  rm -f data/*.jsonl  # a half-finished earlier attempt
  uv run scripts/collect_traces.py --tasks "$TASKS" --samples "$SAMPLES" --start "$START" \
    --workers "$WORKERS" --minutes "$MINUTES" 2>&1 | tee "$OUT/collect.txt" || fail "collecting ($OUT/collect.txt)"
  touch "$OUT/collect.done"
else
  log "2/5 Training examples already collected"
fi

# --- 3. Fine-tune ---------------------------------------------------------------------------------
if [ ! -f "$OUT/lora/adapter_config.json" ]; then
  log "3/5 Fine-tuning with LoRA (about 15-30 minutes)"
  free_gpu
  # shellcheck disable=SC2086  # TRAIN_ARGS is meant to split into separate arguments
  uv run --with torch --with "$PEFT" scripts/train_lora.py --out "$OUT/lora" $TRAIN_ARGS 2>&1 | tee "$OUT/train.txt" \
    || fail "fine-tuning ($OUT/train.txt)"
else
  log "3/5 Already fine-tuned"
fi

# --- 4. Evaluate ----------------------------------------------------------------------------------
log "4/5 Evaluating the original and the fine-tuned model side by side, $EVAL_RUNS runs per scenario (10-15 minutes)"
free_gpu
start_server --enable-lora --lora-modules "$LORA=$OUT/lora" --max-lora-rank 64
STAMP="$(date +%H%M)"
SCENARIOS="$(uv run python -c "from ai.evals import SCENARIOS; print(' '.join(s.name for s in SCENARIOS))")"
pids=()
for model in "$BASE" "$LORA"; do
  label=base; [ "$model" = "$LORA" ] && label=lora
  for scenario in $SCENARIOS; do
    uv run scripts/run_evals.py --runs "$EVAL_RUNS" --only "$scenario" --model "$model" \
      --label "pod-$STAMP-$label-$scenario" > "$OUT/eval-$label-$scenario.txt" 2>&1 &
    pids+=($!)
  done
done
failed=0
for pid in "${pids[@]}"; do wait "$pid" || failed=$((failed + 1)); done
[ "$failed" -eq 0 ] || echo "$failed eval run(s) crashed: see $OUT/eval-*.txt"
free_gpu

# --- 5. Summary -----------------------------------------------------------------------------------
log "5/5 Results"
mkdir -p "$OUT/evals" "$OUT/data"
cp evals/*"pod-$STAMP-"* "$OUT/evals/" 2> /dev/null || true
cp data/*.jsonl "$OUT/data/" 2> /dev/null || true
uv run python - "$OUT/evals" << 'EOF' | tee "$OUT/summary.txt"
import json, sys
from collections import defaultdict
from pathlib import Path

runs = defaultdict(list)
for path in Path(sys.argv[1]).glob("*.jsonl"):
    for line in path.read_text().splitlines():
        r = json.loads(line)
        runs[("lora" if "-lora-" in r["label"] else "base", r["scenario"])].append(r)

print(f"{'scenario':<20} {'original: passed':>17} {'tokens':>7} {'sec':>5} {'remind':>6}   "
      f"{'fine-tuned: passed':>19} {'tokens':>7} {'sec':>5} {'remind':>6}")
totals = defaultdict(lambda: [0, 0])
for scenario in sorted({s for _, s in runs}):
    row = f"{scenario:<20}"
    for model, width in (("base", 17), ("lora", 19)):
        rs = runs[(model, scenario)]
        if not rs:
            row += f" {'-':>{width}} {'-':>7} {'-':>5} {'-':>6}  "
            continue
        passed = sum(r["passed"] for r in rs)
        totals[model][0] += passed
        totals[model][1] += len(rs)
        row += (f" {f'{passed}/{len(rs)}':>{width}} {sum(r['tokens'] for r in rs) // len(rs):>7}"
                f" {sum(r['seconds'] for r in rs) / len(rs):>5.0f} {sum(r['nudged'] for r in rs):>6}  ")
    print(row)
print(f"{'TOTAL':<20} {'%d/%d' % tuple(totals['base']):>17} {'':>21}  {'%d/%d' % tuple(totals['lora']):>19}")
EOF
tail -12 "$OUT/collect.txt" > "$OUT/collect_summary.txt" 2> /dev/null || true
grep -E "examples:|tokens,|by task type|Saved the adapter" "$OUT/train.txt" 2> /dev/null || true
tar czf "$W/steady-results.tar.gz" -C "$W" results
echo
echo "Done. Download /workspace/steady-results.tar.gz: in Jupyter's file list, right-click it > Download."
echo "Then terminate the pod in the RunPod console."
stop_pod_later
