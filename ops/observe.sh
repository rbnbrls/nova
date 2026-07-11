#!/usr/bin/env bash
# Observe a deployment: poll health endpoints and container state; on failure,
# capture logs into a structured incident report that ops/heal.sh can consume.
#
# Exit 0 = healthy. Exit 1 = unhealthy; incident written and its path printed
# on stdout as the last line (for pipeline.sh to pick up).

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require curl

mkdir -p "$INCIDENT_DIR"

declare -a FAILURES=()

check_health() {
  local name="$1" url="$2" attempt=1 body http_code
  while (( attempt <= HEALTH_RETRIES )); do
    http_code="$(curl -s -o /tmp/nova_health_body -w '%{http_code}' --max-time 10 "$url" || echo "000")"
    body="$(cat /tmp/nova_health_body 2>/dev/null || true)"
    if [[ "$http_code" == "200" ]]; then
      log "observe: $name healthy ($url)"
      return 0
    fi
    log "observe: $name attempt $attempt/$HEALTH_RETRIES → HTTP $http_code"
    sleep "$HEALTH_INTERVAL_SECONDS"
    attempt=$(( attempt + 1 ))
  done
  FAILURES+=("$name|$url|HTTP $http_code|$body")
  return 0
}

for_each_pair "$NOVA_HEALTH_CHECKS" check_health

if [[ ${#FAILURES[@]} -eq 0 ]]; then
  log "observe: all health checks passed"
  exit 0
fi

# ── Build the incident report ────────────────────────────────────────────────
TS="$(date '+%Y%m%d-%H%M%S')"
INCIDENT="$INCIDENT_DIR/incident-$TS.md"

{
  echo "# Incident $TS — deployment health check failed"
  echo
  echo "- Repo: $REPO_DIR"
  echo "- Commit: $(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
  echo "- Branch: $(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'n/a')"
  echo "- Time: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo
  echo "## Failed checks"
  echo
  for f in "${FAILURES[@]}"; do
    IFS='|' read -r name url code body <<< "$f"
    echo "### $name"
    echo "- URL: $url"
    echo "- Last result: $code"
    echo '- Body:'
    echo '```'
    echo "${body:-<empty>}"
    echo '```'
    echo
  done

  echo "## Container state"
  echo
  echo '```'
  docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' 2>/dev/null \
    || echo "docker not available on this host"
  echo '```'
  echo
  echo "## Recent logs"
  echo
  for f in "${FAILURES[@]}"; do
    name="${f%%|*}"
    echo "### $name (last $LOG_TAIL_LINES lines)"
    echo '```'
    docker logs --tail "$LOG_TAIL_LINES" "$name" 2>&1 \
      || echo "no container named '$name' on this host"
    echo '```'
    echo
  done
  echo "## Recent commits"
  echo
  echo '```'
  git -C "$REPO_DIR" log --oneline -10 2>/dev/null || echo "n/a"
  echo '```'
} > "$INCIDENT"

log "observe: FAILED — incident written"
echo "$INCIDENT"
exit 1
