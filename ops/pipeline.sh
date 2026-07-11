#!/usr/bin/env bash
# The closed loop: deploy → observe → (triage/heal → redeploy)* with a cap.
#
# observe.sh files failures as Forgejo issues; triage.sh consumes every open
# `auto-heal` issue (including ones from OpenObserve alerts and users) and
# runs the Claude Code heal. Fully autonomous only when HEAL_AUTO_PUSH and
# HEAL_PUSH_TO_MAIN are both true.
#
# Usage: ops/pipeline.sh

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

OBSERVE="$OPS_DIR/observe.sh"
DEPLOY="$OPS_DIR/deploy.sh"
TRIAGE="$OPS_DIR/triage.sh"

attempt=0
"$DEPLOY"

while true; do
  if observe_out="$("$OBSERVE")"; then
    log "pipeline: deployment healthy ✔"
    exit 0
  fi
  issue="$(echo "$observe_out" | tail -1)"
  log "pipeline: deployment unhealthy — issue #$issue ($FORGEJO_URL/$FORGEJO_REPO/issues/$issue)"

  if [[ "${HEAL_ENABLED,,}" != "true" ]]; then
    die "healing disabled; manual intervention required (issue #$issue)"
  fi
  attempt=$(( attempt + 1 ))
  if (( attempt > HEAL_MAX_ATTEMPTS )); then
    die "heal attempts exhausted ($HEAL_MAX_ATTEMPTS); manual intervention required (issue #$issue)"
  fi

  log "pipeline: triage attempt $attempt/$HEAL_MAX_ATTEMPTS"
  if ! "$TRIAGE"; then
    die "triage produced no deployable fix; manual intervention required (issue #$issue)"
  fi

  if [[ "${HEAL_AUTO_PUSH,,}" == "true" && "${HEAL_PUSH_TO_MAIN,,}" == "true" ]]; then
    # Push to main already re-triggered Coolify; redeploy explicitly and re-observe.
    sleep 20
    "$DEPLOY"
  else
    log "pipeline: fix awaits review on the issue — loop pauses until merged"
    exit 3
  fi
done
