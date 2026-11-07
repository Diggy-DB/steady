#!/usr/bin/env bash
# Run Steady Planner's AI for the website on a RunPod GPU pod: the model (Qwen3.5-4B on vLLM) and the
# API the website calls (ai/src/ai/server.py, with real data in Supabase). In the pod's web terminal:
#
#   cd /workspace && tar xzf steady-pod.tar.gz && bash steady/ai/deploy/runpod_app.sh
#
# steady-pod.tar.gz comes from `bash ai/deploy/make_pod_bundle.sh` on the laptop; it includes
# ai/deploy/pod.env with the Supabase URL, its public anon key and the website's address.
# Running this again restarts both servers (e.g. after uploading a new bundle).
#
# The pod needs: a 24 GB GPU (RTX 4090 / A5000 / L4 / 3090), HTTP ports 8888 (Jupyter) and 8000 (this
# API). Only port 8000 is public; the model listens on 127.0.0.1:18001, inside the pod only
# (not 8001: RunPod's template runs nginx there).
# See ai/notes/team_test.md.
#
#   LLM_THINKING=off bash steady/ai/deploy/runpod_app.sh    # faster chat answers, no thinking
set -euo pipefail

MODEL="${MODEL:-Qwen/Qwen3.5-4B}"
MODEL_PORT=18001
HERE="$(cd "$(dirname "$0")" && pwd)"
AI="$(dirname "$HERE")"  # .../steady/ai
mkdir -p /workspace/logs  # /workspace is missing when the pod has no volume
export HF_HOME=/workspace/hf  # the model download stays on the volume across restarts
VENV=/workspace/venv

# ---- Settings ----
if [ -f "$HERE/pod.env" ]; then
  set -a; . "$HERE/pod.env"; set +a
fi
: "${SUPABASE_URL:?missing: make the bundle with make_pod_bundle.sh, or run SUPABASE_URL=... SUPABASE_ANON_KEY=... bash $0}"
: "${SUPABASE_ANON_KEY:?missing (the anon / publishable key, never the service_role key)}"
CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:5173}"

cat > "$AI/.env" << EOF
LLM_BASE_URL=http://127.0.0.1:$MODEL_PORT/v1
LLM_API_KEY=inside-the-pod
LLM_MODEL=$MODEL
LLM_THINKING=${LLM_THINKING:-on}
STORE=supabase
SUPABASE_URL=$SUPABASE_URL
SUPABASE_ANON_KEY=$SUPABASE_ANON_KEY
CORS_ORIGINS=$CORS_ORIGINS
MEMORY=off
EOF

# ---- Install (first time only; about 5 minutes) ----
if ! command -v uv > /dev/null; then
  PIP_BREAK_SYSTEM_PACKAGES=1 pip install --quiet uv
fi
# vLLM gets its own environment: a plain `pip install vllm` on RunPod's Ubuntu 24.04 image fails.
if [ ! -x "$VENV/bin/vllm" ]; then
  echo "Installing vLLM..."
  uv venv --python 3.12 --managed-python "$VENV"
  uv pip install --python "$VENV/bin/python" vllm
fi
echo "Installing the API's packages..."
(cd "$AI" && uv sync --frozen --quiet)

# ---- Start ----
# The API always restarts (to pick up new code). The model only restarts if it isn't already running on
# MODEL_PORT, so running this again never interrupts a model that's still downloading or loading.
# RESTART_MODEL=1 forces it.
model_up() {  # true only when vLLM itself answers with our model (not some other server on the port)
  curl -sf "http://127.0.0.1:$MODEL_PORT/v1/models" | grep -q "\"$MODEL\""
}
pkill -f "uvicorn ai.server:app" 2> /dev/null || true
if pgrep -f "vllm serve.*--port $MODEL_PORT" > /dev/null && [ "${RESTART_MODEL:-0}" != 1 ]; then
  echo "The model server is already running (or still loading); leaving it alone."
else
  pkill -f "vllm serve" 2> /dev/null || true  # e.g. one on an old port
  for _ in $(seq 1 30); do pgrep -f "vllm serve" > /dev/null || break; sleep 1; done
  if curl -s -o /dev/null "http://127.0.0.1:$MODEL_PORT/"; then
    echo "Something else is using port $MODEL_PORT; change MODEL_PORT at the top of this script."; exit 1
  fi
  # Sized for a small team: 16 requests at once (vLLM's default plans for hundreds and reserves memory
  # for them, which didn't fit next to the image reader on a 24 GB card).
  echo "Starting the model (the first time it downloads about 9 GB; then 1-2 minutes)..."
  # vLLM's own tools (ninja, nvcc) must be on PATH: it builds some GPU kernels the first time it starts.
  PATH="$VENV/bin:$PATH" nohup "$VENV/bin/vllm" serve "$MODEL" \
    --host 127.0.0.1 --port "$MODEL_PORT" \
    --max-model-len 32768 --gpu-memory-utilization 0.92 --max-num-seqs 16 --max-num-batched-tokens 8192 \
    --enable-auto-tool-choice --tool-call-parser qwen3_coder \
    --reasoning-parser qwen3 \
    --limit-mm-per-prompt '{"image": 12, "video": 0}' \
    > /workspace/logs/vllm.log 2>&1 &
fi

for i in $(seq 1 360); do  # up to 30 minutes (a slow pod downloads the model slowly)
  if model_up; then break; fi
  if ! pgrep -f "vllm serve" > /dev/null; then
    echo "The model server stopped. Its errors (full log: /workspace/logs/vllm.log):"
    grep -E "Error|error:|memory" /workspace/logs/vllm.log | grep -v 'File "' | grep -v "\^\^\^" | tail -8 | cut -c1-400
    exit 1
  fi
  if [ $((i % 12)) = 0 ]; then  # every minute, the model server's latest line (download progress etc.)
    echo "  still loading ($((i / 12)) min): $(tail -c 2000 /workspace/logs/vllm.log | tr '\r' '\n' | grep -v '^\s*$' | tail -1 | cut -c1-150)"
  fi
  sleep 5
done
model_up || { echo "The model isn't up after 30 minutes. It keeps loading in the background: run this script again later (it won't restart the model). Log: /workspace/logs/vllm.log"; exit 1; }
echo "Model ready."

cd "$AI"
nohup uv run --frozen uvicorn ai.server:app --host 0.0.0.0 --port 8000 > /workspace/logs/app.log 2>&1 &
for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/health > /dev/null; then break; fi
  sleep 2
done
curl -sf http://127.0.0.1:8000/health || { echo "The API didn't start; the end of /workspace/logs/app.log:"; tail -30 /workspace/logs/app.log; exit 1; }

# ---- Check the whole path once: a tiny chat and a tiny picture through the model ----
uv run --frozen python - << 'EOF'
import base64, io, os
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw
from ai.llm import thinking_off

load_dotenv(".env")
client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])
image = Image.new("RGB", (400, 120), "white")
ImageDraw.Draw(image).text((20, 50), "HW 3 due Feb 12", fill="black")
buffer = io.BytesIO(); image.save(buffer, format="PNG")
reply = client.chat.completions.create(
    model=os.environ["LLM_MODEL"], max_tokens=40, extra_body=thinking_off(os.environ["LLM_BASE_URL"]),
    messages=[{"role": "user", "content": [
        {"type": "text", "text": "What does the picture say? Answer with the text only."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()}}]}])
print("Vision check:", (reply.choices[0].message.content or "").strip())
EOF

cat << EOF

=== Steady Planner AI is running ===
The website's AI address (repository variable VITE_AI_API_URL):

    https://${RUNPOD_POD_ID:-<POD_ID>}-8000.proxy.runpod.net

Logs: tail -f /workspace/logs/app.log   (model: /workspace/logs/vllm.log, syllabus imports: $AI/logs/imports.jsonl)
Allowed website addresses: $CORS_ORIGINS
Stop the pod when the team is done testing: it bills while it's on.
EOF
