#!/usr/bin/env bash
# Pack the AI code into one file to upload to a RunPod pod (the GitHub repo is private, so the pod
# can't clone it). Only files git would keep: no .env, logs, data, memory or .venv.
#
#   bash ai/deploy/make_pod_bundle.sh                # writes ~/Downloads/steady-pod.tar.gz
#   bash ai/deploy/make_pod_bundle.sh other/path.tar.gz
set -euo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
OUT="${1:-$HOME/Downloads/steady-pod.tar.gz}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cd "$ROOT"
mkdir -p "$STAGE/steady"
# Tracked and new (not ignored) files under ai/, skipping old eval results and deleted files.
git ls-files --cached --others --exclude-standard -- ai | grep -v '^ai/evals/' | while read -r file; do
  [ -f "$file" ] && echo "$file"
done > "$STAGE/files.txt"
rsync -a --files-from="$STAGE/files.txt" . "$STAGE/steady/"
tar czf "$OUT" -C "$STAGE" steady
echo "Wrote $OUT ($(wc -l < "$STAGE/files.txt" | tr -d ' ') files, $(du -h "$OUT" | cut -f1 | tr -d ' '))"
