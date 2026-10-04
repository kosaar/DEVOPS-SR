# shellcheck shell=bash
# Shared helpers for the POC scripts.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example (review the passwords before sharing this instance)"
fi
set -a
# shellcheck disable=SC1091
source .env
set +a
DC="docker compose"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

wait_healthy() { # service timeout_seconds
  local svc=$1 timeout=${2:-900} start; start=$(date +%s)
  local cid; cid=$($DC ps -q "$svc")
  while :; do
    local st; st=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo missing)
    [ "$st" = healthy ] && return 0
    if (( $(date +%s) - start > timeout )); then echo "Timed out waiting for $svc (status: $st)"; return 1; fi
    sleep 5
  done
}

yt_token() { cat "$ROOT/.state/youtrack-token"; }
