#!/usr/bin/env bash
# Shared helpers for the Nova ops loop. Source this; don't execute it.

set -euo pipefail

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$OPS_DIR/.." && pwd)"
INCIDENT_DIR="$OPS_DIR/incidents"

# Load config (real file wins over example so the loop is runnable in dev).
if [[ -f "$OPS_DIR/config.env" ]]; then
  # shellcheck source=/dev/null
  source "$OPS_DIR/config.env"
else
  echo "ops: no ops/config.env found — copy ops/config.env.example first" >&2
  exit 1
fi

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { log "ERROR: $*"; exit 1; }

require() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

coolify_api() {
  # coolify_api <method> <path> — authenticated call against the Coolify API.
  local method="$1" path="$2"
  curl -fsS -X "$method" \
    -H "Authorization: Bearer $COOLIFY_API_TOKEN" \
    -H "Content-Type: application/json" \
    "$COOLIFY_URL/api/v1$path"
}

# Iterate "name:value" pairs from a comma-separated env var.
# usage: for_each_pair "$NOVA_SERVICES" callback   → callback <name> <value>
for_each_pair() {
  local pairs="$1" fn="$2" entry name value
  IFS=',' read -ra entries <<< "$pairs"
  for entry in "${entries[@]}"; do
    entry="${entry## }"; entry="${entry%% }"
    [[ -z "$entry" ]] && continue
    name="${entry%%:*}"
    value="${entry#*:}"
    "$fn" "$name" "$value"
  done
}
