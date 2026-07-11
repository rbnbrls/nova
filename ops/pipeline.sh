#!/usr/bin/env bash
# The closed loop: deploy → observe → (heal → redeploy → observe)* with a cap.
#
# Intended to run on the Nova AI VM (or any host with docker + the repo +
# claude CLI authenticated). Trigger it from Coolify's post-deployment webhook,
# a systemd timer, or manually after a push.
#
# Usage: ops/pipeline.sh

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

OBSERVE="$OPS_DIR/observe.sh"
DEPLOY="$OPS_DIR/deploy.sh"
HEAL="$OPS_DIR/heal.sh"

attempt=0
"$DEPLOY"

while true; do
  if incident_out="$("$OBSERVE")"; then
    log "pipeline: deployment healthy ✔"
    exit 0
  fi
  incident="$(echo "$incident_out" | tail -1)"
  log "pipeline: deployment unhealthy — incident: $incident"

  if [[ "${HEAL_ENABLED,,}" != "true" ]]; then
    die "healing disabled; manual intervention required (see $incident)"
  fi
  attempt=$(( attempt + 1 ))
  if (( attempt > HEAL_MAX_ATTEMPTS )); then
    die "heal attempts exhausted ($HEAL_MAX_ATTEMPTS); manual intervention required (see $incident)"
  fi

  log "pipeline: heal attempt $attempt/$HEAL_MAX_ATTEMPTS"
  if ! "$HEAL" "$incident"; then
    die "heal did not produce a deployable fix; manual intervention required (see $incident)"
  fi

  # With HEAL_AUTO_PUSH+HEAL_PUSH_TO_MAIN, the push already re-triggered
  # Coolify; give it a moment, then re-deploy explicitly to be sure and
  # loop back to observation.
  if [[ "${HEAL_AUTO_PUSH,,}" == "true" && "${HEAL_PUSH_TO_MAIN,,}" == "true" ]]; then
    sleep 20
    "$DEPLOY"
  else
    log "pipeline: fix awaits review — loop pauses here until the fix branch is merged"
    exit 3
  fi
done
