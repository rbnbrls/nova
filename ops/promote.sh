#!/usr/bin/env bash
# Promote staging to production: run test + eval gates, then deploy prod.
#
# Usage: ops/promote.sh [--force]
#   --force: skip health check (use only if staging is known-healthy)
#
# Exit codes:
#   0 — promoted successfully
#   1 — staging health check failed
#   2 — test suite failed (tests or evals)
#   3 — production deploy failed

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require curl
require jq

FORCE="${1:-}"

log "promote: starting staging-to-production promotion"
log "promote: phase 1 — verify staging is healthy"
log "promote: phase 2 — run test suite + evals"
log "promote: phase 3 — deploy production"

fail() {
  local code="$1" msg="$2"
  log "promote: FAILED — $msg"
  exit "$code"
}

# ── Phase 1: Verify staging health (skip with --force) ──────────────────────
if [[ "$FORCE" != "--force" ]]; then
  log "promote: checking staging health endpoint ..."
  # STAGING_HEALTH_URL is set in ops/config.env
  STAGING_HEALTH_URL="${STAGING_HEALTH_URL:-http://nova-staging.local:8081/health}"
  HEALTH_OK=0
  for i in $(seq 1 5); do
    http_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$STAGING_HEALTH_URL" || echo "000")"
    if [[ "$http_code" == "200" ]]; then
      HEALTH_OK=1
      break
    fi
    log "promote: staging health attempt $i/5 — HTTP $http_code"
    sleep 5
  done
  if [[ "$HEALTH_OK" -ne 1 ]]; then
    fail 1 "staging health endpoint $STAGING_HEALTH_URL unreachable after 5 retries"
  fi
  log "promote: staging is healthy ✔"
else
  log "promote: --force set, skipping health check"
fi

# ── Phase 2: Run test suite + evals ──────────────────────────────────────────
log "promote: running test suite (tests + evals) ..."
if "$OPS_DIR/run-tests.sh"; then
  log "promote: all tests and evals passed ✔"
else
  fail 2 "test suite failed — check output above for details"
fi

# ── Phase 3: Deploy production ──────────────────────────────────────────────
log "promote: tests green, deploying production ..."
if "$OPS_DIR/deploy.sh"; then
  log "promote: production deployed successfully ✔"
else
  fail 3 "production deploy failed — check ops/deploy.sh output"
fi

log "promote: staging→production promotion complete"
