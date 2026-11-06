#!/usr/bin/env bash
# Start the Steady Planner model server on a RunPod GPU pod. Run it in the pod's web terminal:
#
#   bash runpod_pod.sh                                      # the thinking model (default)
#   MODEL=Qwen/Qwen3-4B-Instruct-2507 bash runpod_pod.sh    # the instruct model (no thinking)
#
# The pod needs: a 24 GB GPU (RTX 4090 / A5000 / L4 / 3090) and HTTP ports 8888 (Jupyter, for
# the terminal) and 8000 (the model). A volume at /workspace is optional: without one, the model
# downloads again after each restart. See ai/notes/stage4_runpod.md.
set -euo pipefail

MODEL="${MODEL:-Qwen/Qwen3-4B-Thinking-2507}"
mkdir -p /workspace  # missing when the pod has no volume
KEY_FILE=/workspace/vllm_api_key
VENV=/workspace/venv
export HF_HOME=/workspace/hf  # keep the model download on the volume, so a restart doesn't download it again

# The pod's URL is public, so the API needs a secret. Make a long random one once and keep it.
if [ ! -f "$KEY_FILE" ]; then
  python3 -c "import secrets; print(secrets.token_urlsafe(32))" > "$KEY_FILE"
fi
API_KEY="$(cat "$KEY_FILE")"

# vLLM goes into its own environment: a plain `pip install vllm` on RunPod's Ubuntu 24.04 PyTorch
# image fails ("Cannot uninstall PyJWT ... installed by debian"). uv is also much faster.
if [ ! -x "$VENV/bin/vllm" ]; then
  echo "Installing vLLM (2-4 minutes the first time)..."
  PIP_BREAK_SYSTEM_PACKAGES=1 pip install --quiet uv
  uv venv --python 3.12 --managed-python "$VENV"
  uv pip install --python "$VENV/bin/python" vllm
fi
export PATH="$VENV/bin:$PATH"

# Only the thinking model needs a reasoning parser. deepseek_r1 is what Qwen's model card uses:
# the output has </think> but no opening <think>, and this parser handles that.
EXTRA=()
case "$MODEL" in
  *Thinking*) EXTRA+=(--reasoning-parser deepseek_r1) ;;
esac

cat << EOF

=== Steady Planner model server ===
Model: $MODEL
Put these three lines in ai/.env on your laptop (replacing the LLM_ lines there):

LLM_BASE_URL=https://${RUNPOD_POD_ID:-<POD_ID>}-8000.proxy.runpod.net/v1
LLM_API_KEY=$API_KEY
LLM_MODEL=$MODEL

Then, on the laptop: uv run scripts/check_server.py   (add --no-thinking for the instruct model)
Stop the pod when you're done: it bills while it's on.

EOF

exec vllm serve "$MODEL" \
  --max-model-len 32768 \
  --enable-auto-tool-choice --tool-call-parser hermes \
  ${EXTRA[@]+"${EXTRA[@]}"} \
  --api-key "$API_KEY" \
  --port 8000
