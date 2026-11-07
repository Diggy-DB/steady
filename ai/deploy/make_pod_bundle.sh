#!/usr/bin/env bash
# Pack the AI code into one file to upload to a RunPod pod (the GitHub repo is private, so the pod
# can't clone it). Only files git would keep: no .env, logs, data, memory or .venv.
# For runpod_app.sh it also writes ai/deploy/pod.env (only inside the bundle) with the Supabase URL and
# public anon key from Front-end/.env.local, and the website addresses the API should accept.
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

# Settings for the website's AI (runpod_app.sh). The anon key is public by design (it's in the website);
# refuse anything that looks like the secret service_role key.
FRONT_ENV=Front-end/.env.local
if [ -f "$FRONT_ENV" ]; then
  url="$(sed -n 's/^VITE_SUPABASE_URL=//p' "$FRONT_ENV" | tr -d '"' | tr -d "'")"
  key="$(sed -n 's/^VITE_SUPABASE_ANON_KEY=//p' "$FRONT_ENV" | tr -d '"' | tr -d "'")"
  role="$(python3 -c "import base64,json,sys; p=sys.argv[1].split('.'); print(json.loads(base64.urlsafe_b64decode(p[1]+'==')).get('role','') if len(p)==3 else '')" "$key" 2>/dev/null || true)"
  if [ "$role" = "service_role" ] || [[ "$key" == sb_secret_* ]]; then
    echo "Front-end/.env.local has a SECRET key; it must be the anon / publishable key. Not writing pod.env." >&2
    exit 1
  fi
  owner="$(git remote get-url origin | sed -E 's#.*github.com[:/]([^/]+)/.*#\1#' | tr '[:upper:]' '[:lower:]')"
  {
    echo "SUPABASE_URL=$url"
    echo "SUPABASE_ANON_KEY=$key"
    echo "CORS_ORIGINS=https://$owner.github.io,http://localhost:5173"
  } > "$STAGE/steady/ai/deploy/pod.env"
  echo "Included pod.env (Supabase $url, website https://$owner.github.io)"
else
  echo "No $FRONT_ENV: pod.env not included; runpod_app.sh will ask for SUPABASE_URL and SUPABASE_ANON_KEY."
fi
tar czf "$OUT" -C "$STAGE" steady
echo "Wrote $OUT ($(wc -l < "$STAGE/files.txt" | tr -d ' ') files, $(du -h "$OUT" | cut -f1 | tr -d ' '))"
