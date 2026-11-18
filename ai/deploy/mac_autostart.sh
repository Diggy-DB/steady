#!/usr/bin/env bash
# Run Steady's AI on this Mac whenever you're logged in, and let the website on GitHub Pages reach it from any
# network through a permanent https address (Tailscale Funnel). When the Mac is off or asleep, the website still
# works (it reads Supabase directly); only the chat, the daily overview and calendar syncing wait for it.
#
#   ai/deploy/mac_autostart.sh install     # once: the three login items below, then Tailscale sign-in and Funnel
#   ai/deploy/mac_autostart.sh status      # what's running, and the public address
#   ai/deploy/mac_autostart.sh restart     # after changing the AI code or ai/.env
#   ai/deploy/mac_autostart.sh uninstall   # remove all three; the public address stops answering
#
# Three macOS LaunchAgents (~/Library/LaunchAgents; started at login, restarted if they stop):
#   org.steady.ollama      the model server (Ollama), on 127.0.0.1:11434
#   org.steady.ai-server   the AI server (uvicorn), on 127.0.0.1:8000 only: nothing on the network reaches it directly
#   org.steady.tailscaled  Tailscale in userspace mode (no admin rights, no VPN, no system extension). Funnel passes
#                          https://<name>.<tailnet>.ts.net/... to 127.0.0.1:8000, and nothing else on this Mac.
# Every AI request still needs a valid Steady (Supabase) login. Logs: ~/Library/Logs/steady/.
#
# Settings (environment variables, read by install):
#   OLLAMA_MODELS   where Ollama keeps its models (default: Ollama's own, ~/.ollama/models)
#   CORS_ORIGINS    web pages allowed to call the AI (default: the GitHub Pages site and localhost:5173)
#   TS_HOSTNAME     the machine's name in the address (default: steady-ai)
set -euo pipefail

AI_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs/steady"
TS_STATE="$HOME/Library/Application Support/steady-tailscale"
TS_SOCKET="$TS_STATE/tailscaled.sock"
TS_HOSTNAME="${TS_HOSTNAME:-steady-ai}"
CORS_ORIGINS="${CORS_ORIGINS:-https://diggy-db.github.io,http://localhost:5173}"
OLLAMA_MODELS="${OLLAMA_MODELS:-$HOME/.ollama/models}"
PORT=8000
LABELS=(org.steady.ollama org.steady.ai-server org.steady.tailscaled)

ts() { tailscale --socket "$TS_SOCKET" "$@"; }
need() { command -v "$1" > /dev/null || { echo "Missing $1. Install it with: brew install $2"; exit 1; }; }

# plist LABEL LOGNAME ENV(k=v;k=v) WORKDIR PROGRAM ARGS...
plist() {
  local label=$1 log=$2 env=$3 dir=$4; shift 4
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    echo '<plist version="1.0"><dict>'
    echo "  <key>Label</key><string>$label</string>"
    echo '  <key>ProgramArguments</key><array>'
    for arg in "$@"; do echo "    <string>$arg</string>"; done
    echo '  </array>'
    echo "  <key>WorkingDirectory</key><string>$dir</string>"
    echo '  <key>EnvironmentVariables</key><dict>'
    echo '    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>'
    local IFS=';'
    for pair in $env; do echo "    <key>${pair%%=*}</key><string>${pair#*=}</string>"; done
    echo '  </dict>'
    echo '  <key>RunAtLoad</key><true/>'
    echo '  <key>KeepAlive</key><true/>'
    echo '  <key>ThrottleInterval</key><integer>10</integer>'
    echo "  <key>StandardOutPath</key><string>$LOGS/$log.log</string>"
    echo "  <key>StandardErrorPath</key><string>$LOGS/$log.log</string>"
    echo '</dict></plist>'
  } > "$AGENTS/$label.plist"
}

load() { launchctl bootstrap "gui/$(id -u)" "$AGENTS/$1.plist" 2> /dev/null || launchctl kickstart -k "gui/$(id -u)/$1"; }
unload() { launchctl bootout "gui/$(id -u)/$1" 2> /dev/null || true; }

public_address() { ts funnel status 2> /dev/null | grep -o 'https://[^ ]*' | head -1; }

case "${1:-status}" in
  install)
    need tailscale tailscale
    need ollama ollama
    [ -x "$AI_DIR/.venv/bin/uvicorn" ] || { echo "Run 'uv sync' in $AI_DIR first."; exit 1; }
    mkdir -p "$AGENTS" "$LOGS" "$TS_STATE"
    plist org.steady.ollama ollama "OLLAMA_HOST=127.0.0.1:11434;OLLAMA_MODELS=$OLLAMA_MODELS;OLLAMA_CONTEXT_LENGTH=16384" \
      "$HOME" "$(command -v ollama)" serve
    plist org.steady.ai-server ai-server "CORS_ORIGINS=$CORS_ORIGINS" \
      "$AI_DIR" "$AI_DIR/.venv/bin/uvicorn" ai.server:app --host 127.0.0.1 --port "$PORT"
    plist org.steady.tailscaled tailscaled "" \
      "$TS_STATE" "$(command -v tailscaled)" --tun=userspace-networking --statedir="$TS_STATE" --socket="$TS_SOCKET"
    for label in "${LABELS[@]}"; do load "$label"; done
    for _ in $(seq 1 30); do [ -S "$TS_SOCKET" ] && break; sleep 1; done  # Tailscale's background service is up
    echo "Sign in to Tailscale (a link appears if it's needed; open it, sign in, then come back):"
    ts up --hostname "$TS_HOSTNAME"
    echo "Turning on Funnel (if Tailscale asks you to allow it, open the link, allow it, and run install again):"
    ts funnel --bg "$PORT"
    echo "Public address: $(public_address)"
    echo "Put it in GitHub: Settings > Environments > github-pages > VITE_AI_API_URL, then publish the site again."
    ;;
  status)
    for label in "${LABELS[@]}"; do
      if launchctl print "gui/$(id -u)/$label" > /dev/null 2>&1; then echo "$label: running"; else echo "$label: not running"; fi
    done
    curl -s -m 5 "http://127.0.0.1:$PORT/health" && echo || echo "AI server: no answer on 127.0.0.1:$PORT"
    echo "Public address: $(public_address || true)"
    ;;
  restart)
    for label in "${LABELS[@]}"; do launchctl kickstart -k "gui/$(id -u)/$label"; done
    ;;
  uninstall)
    ts funnel reset 2> /dev/null || true
    for label in "${LABELS[@]}"; do unload "$label"; rm -f "$AGENTS/$label.plist"; done
    echo "Removed. (Tailscale's sign-in is kept in $TS_STATE; delete that folder to forget it.)"
    ;;
  *)
    echo "usage: $0 install | status | restart | uninstall"; exit 2
    ;;
esac
