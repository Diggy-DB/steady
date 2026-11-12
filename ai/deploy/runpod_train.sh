#!/usr/bin/env bash
# The whole training session for Qwen3.5-4B on one RunPod GPU pod, about 2-2.5 hours (~$1.50 on an RTX 4090):
#   1. install vLLM (shared with runpod_app.sh), the Steady code and the training libraries
#   2. with the ORIGINAL model: run the eval suite and the syllabus import eval, and at the same time collect
#      training examples (the model tries practice tasks; its shortest passing try per task is kept)
#   3. fine-tune with LoRA (scripts/train_lora.py), then add the adapter into a full copy of the model
#      (scripts/merge_lora.py) at /workspace/steady-ft
#   4. the same evals on the FINE-TUNED model
#   5. compare, and pack the results (not the 9 GB model) into /workspace/steady-results.tar.gz
#
# On the Mac: bash ai/deploy/make_pod_bundle.sh, then upload ~/Downloads/steady-pod.tar.gz to /workspace in
# Jupyter. In a Jupyter terminal:
#   cd /workspace && tar xzf steady-pod.tar.gz && nohup bash steady/ai/deploy/runpod_train.sh > session.log 2>&1 &
#   tail -f /workspace/session.log
#
# It keeps going if the browser is closed. Running it again skips the steps already done (delete
# /workspace/results to start over). When it ends or fails, the pod stops itself 60 minutes later unless
# /workspace/keep-running exists. To try the fine-tuned model in the website afterwards (same pod):
#   touch /workspace/keep-running && MODEL=/workspace/steady-ft RESTART_MODEL=1 bash steady/ai/deploy/runpod_app.sh
#
# Settings (environment variables, defaults in brackets): TASKS [400] MINUTES [60] SAMPLES [4] WORKERS [16]
# START [1000] EVAL_RUNS [3] EVAL_WORKERS [8] SYLLABUS_RUNS [1] TRAIN_ARGS [""], e.g. TRAIN_ARGS="--epochs 3".
set -euo pipefail

TASKS="${TASKS:-400}"            # at most this many practice tasks...
MINUTES="${MINUTES:-60}"         # ...or as many as fit in this many minutes of collecting
SAMPLES="${SAMPLES:-4}"          # tries per task; the shortest passing one is kept
WORKERS="${WORKERS:-16}"         # practice tasks at the same time
START="${START:-1000}"           # first task seed; use new seeds for new data
EVAL_RUNS="${EVAL_RUNS:-3}"      # runs per eval case, for each model
EVAL_WORKERS="${EVAL_WORKERS:-8}"
SYLLABUS_RUNS="${SYLLABUS_RUNS:-1}"
TRAIN_ARGS="${TRAIN_ARGS:-}"

W=/workspace
AI="$W/steady/ai"
VENV="$W/venv"                   # vLLM's own environment (the same one runpod_app.sh uses)
OUT="$W/results"
MERGED="$W/steady-ft"            # the fine-tuned model, kept on the volume for runpod_app.sh
BASE=Qwen/Qwen3.5-4B
PORT=18001                       # inside the pod only (8001 is RunPod's nginx)
URL="http://127.0.0.1:$PORT/v1"
PEFT=peft==0.21.2                # the versions tests/test_train_merge.py ran with
FLA=flash-linear-attention==0.6.0
export HF_HOME="$W/hf" PIP_BREAK_SYSTEM_PACKAGES=1 UV_LINK_MODE=copy
mkdir -p "$OUT" "$W/logs"
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

free_gpu() {  # stop the website's API and any model server, and wait until the GPU's memory is free
  pkill -f "steady-api-loop" 2> /dev/null || true
  pkill -f "uvicorn ai.server:app" 2> /dev/null || true
  pkill -f "vllm serve" 2> /dev/null || true
  for _ in $(seq 30); do
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
    [ "$used" -lt 2000 ] && return
    sleep 2
  done
  pkill -9 -f -i "vllm|EngineCore" 2> /dev/null || true
  sleep 5
}

start_model() {  # $1: the model (a Hugging Face name or a folder). Same flags as the website's server.
  free_gpu
  PATH="$VENV/bin:$PATH" setsid nohup "$VENV/bin/vllm" serve "$1" \
    --host 127.0.0.1 --port "$PORT" \
    --max-model-len 32768 --gpu-memory-utilization 0.92 --max-num-seqs 32 --max-num-batched-tokens 8192 \
    --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3 \
    --limit-mm-per-prompt '{"image": 12, "video": 0}' \
    > "$OUT/vllm-$(basename "$1").log" 2>&1 < /dev/null &
  for i in $(seq 1 360); do
    if curl -sf "$URL/models" | grep -q "\"$1\""; then return; fi
    pgrep -f "vllm serve" > /dev/null || { tail -25 "$OUT/vllm-$(basename "$1").log"; fail "starting the model server"; }
    [ $((i % 12)) = 0 ] && echo "  model still loading ($((i / 12)) min)"
    sleep 5
  done
  fail "the model server didn't start in 30 minutes ($OUT/vllm-$(basename "$1").log)"
}

evals() {  # $1: the model, $2: a label (base / finetuned), $3: runs at once. In the background; see wait_evals.
  uv run --frozen scripts/run_evals.py --suite all --runs "$EVAL_RUNS" --workers "$3" \
    --model "$1" --label "session-$2" > "$OUT/eval-$2.txt" 2>&1 &
  EVAL_PID=$!
  uv run --frozen scripts/eval_syllabus_import.py --model "$1" --base-url "$URL" --runs "$SYLLABUS_RUNS" \
    > "$OUT/syllabus-$2.txt" 2>&1 &
  SYLLABUS_PID=$!
}

wait_evals() {  # $1: the label
  wait "$EVAL_PID" || fail "the eval suite ($OUT/eval-$1.txt)"
  wait "$SYLLABUS_PID" || fail "the syllabus eval ($OUT/syllabus-$1.txt)"
  cp "$(ls -t evals/*-session-"$1".jsonl | head -1)" "$OUT/evals-$1.jsonl"
  cp "$(ls -t evals/*-syllabus-import-*.json | head -1)" "$OUT/syllabus-$1.json"
  touch "$OUT/eval-$1.done"
}

# --- 1. Install -----------------------------------------------------------------------------------
log "1/5 Installing (5-10 minutes the first time). GPU: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"
command -v uv > /dev/null || pip install -q uv || fail "installing uv"
if [ ! -x "$VENV/bin/vllm" ]; then
  # Its own environment: a plain `pip install vllm` fails on RunPod's Ubuntu 24.04 PyTorch image.
  rm -rf "$VENV"  # a half-finished earlier install
  { uv venv -q --python 3.12 --managed-python "$VENV" && uv pip install -q --python "$VENV/bin/python" vllm; } \
    || fail "installing vLLM"
fi
uv sync -q --frozen || fail "installing the Steady code"
# Training uses the same torch version as vLLM (a build that's known to work with this pod's GPU driver).
TORCH="torch==$("$VENV/bin/python" -c "import torch; print(torch.__version__.split('+')[0])")"
TRAIN_WITH=(--with "$TORCH" --with "$PEFT" --with "$FLA")
uv run -q --frozen "${TRAIN_WITH[@]}" python -c "import torch, peft, fla; assert torch.cuda.is_available(), 'no GPU'" \
  || fail "installing the training libraries"
echo "vLLM $("$VENV/bin/python" -c "import vllm; print(vllm.__version__)"), $TORCH, $PEFT, $FLA"
cat > .env << EOF
LLM_BASE_URL=$URL
LLM_API_KEY=inside-the-pod
LLM_MODEL=$BASE
MEMORY=off
EOF

# --- 2. The original model: evals, and collecting training examples at the same time ---------------
if [ ! -f "$OUT/collect.done" ] || [ ! -f "$OUT/eval-base.done" ]; then
  log "2/5 Original model: evals ($EVAL_RUNS runs per case) while collecting examples (up to $TASKS tasks x $SAMPLES tries, at most $MINUTES min)"
  start_model "$BASE"
  [ -f "$OUT/eval-base.done" ] || evals "$BASE" base "$EVAL_WORKERS"  # shares the GPU with collecting
  if [ ! -f "$OUT/collect.done" ]; then
    rm -f data/*.jsonl  # a half-finished earlier attempt
    uv run --frozen scripts/collect_traces.py --model "$BASE" --tasks "$TASKS" --samples "$SAMPLES" --start "$START" \
      --workers "$WORKERS" --minutes "$MINUTES" > "$OUT/collect.txt" 2>&1 || fail "collecting ($OUT/collect.txt)"
    mkdir -p "$OUT/data" && cp data/*.jsonl "$OUT/data/" && touch "$OUT/collect.done"
    tail -22 "$OUT/collect.txt"
  fi
  if [ ! -f "$OUT/eval-base.done" ]; then
    echo "Collecting done; waiting for the original model's evals to finish..."
    wait_evals base
  fi
else
  log "2/5 Already done"
fi

# --- 3. Fine-tune and merge -------------------------------------------------------------------------
if [ ! -f "$MERGED/steady_merge.json" ]; then
  log "3/5 Fine-tuning with LoRA (about 20-40 minutes), then merging"
  free_gpu
  if [ ! -f "$OUT/lora/adapter_config.json" ]; then
    # shellcheck disable=SC2086  # TRAIN_ARGS is meant to split into separate arguments
    uv run --frozen "${TRAIN_WITH[@]}" scripts/train_lora.py --data "$OUT/data/*.jsonl" --out "$OUT/lora" $TRAIN_ARGS \
      2>&1 | tee "$OUT/train.txt" || fail "fine-tuning ($OUT/train.txt)"
    [ -f "$OUT/lora/adapter_config.json" ] || fail "fine-tuning: no adapter was saved ($OUT/train.txt)"
  fi
  uv run --frozen --with "$TORCH" scripts/merge_lora.py --base "$BASE" --adapter "$OUT/lora" --out "$MERGED" \
    2>&1 | tee "$OUT/merge.txt" || fail "merging ($OUT/merge.txt)"
else
  log "3/5 Already fine-tuned and merged"
fi

# --- 4. The fine-tuned model: the same evals --------------------------------------------------------
if [ ! -f "$OUT/eval-finetuned.done" ]; then
  log "4/5 Fine-tuned model: the same evals (about 25-40 minutes)"
  start_model "$MERGED"
  evals "$MERGED" finetuned $((EVAL_WORKERS * 2))  # alone on the GPU: faster, same pass rates
  wait_evals finetuned
else
  log "4/5 Already evaluated"
fi
free_gpu

# --- 5. Compare -----------------------------------------------------------------------------------
log "5/5 Results"
{
  echo "=== Eval suite: original vs fine-tuned (a case counts as right if it passed most runs) ==="
  uv run --frozen scripts/compare_evals.py "$OUT/evals-base.jsonl" "$OUT/evals-finetuned.jsonl"
  for label in base finetuned; do
    echo; echo "=== $label: by category ==="
    sed -n '/^category/,/^Saved/p' "$OUT/eval-$label.txt" | grep -v "^Saved"
    echo; echo "=== $label: syllabus import ==="
    grep "^TOTAL" "$OUT/syllabus-$label.txt" || tail -3 "$OUT/syllabus-$label.txt"
  done
  echo; echo "=== Training data ==="
  grep -A 20 "^task type" "$OUT/collect.txt" || true
  grep -E "examples:|tokens,|by task type|Saved the adapter" "$OUT/train.txt" || true
  cat "$OUT/merge.txt" 2> /dev/null | tail -1
} 2>&1 | tee "$OUT/summary.txt"
tar czf "$W/steady-results.tar.gz" -C "$W" results
echo
echo "Done. Download /workspace/steady-results.tar.gz: in Jupyter's file list, right-click it > Download."
echo "The fine-tuned model is in $MERGED. To try it in the website on this pod:"
echo "  touch $W/keep-running && MODEL=$MERGED RESTART_MODEL=1 bash $AI/deploy/runpod_app.sh"
stop_pod_later
