#!/usr/bin/env bash
# Deploy the Nova stack as code: trigger Coolify deployments via API and wait
# for them to finish. Exit 0 = all services deployed; non-zero = deploy failed.
#
# Usage: ops/deploy.sh [service-name ...]   (default: all in NOVA_SERVICES)

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require curl
require jq

ONLY_SERVICES=("$@")

wants_service() {
  [[ ${#ONLY_SERVICES[@]} -eq 0 ]] && return 0
  local s
  for s in "${ONLY_SERVICES[@]}"; do [[ "$s" == "$1" ]] && return 0; done
  return 1
}

FAILED=0

deploy_service() {
  local name="$1" uuid="$2"
  wants_service "$name" || return 0

  log "deploy: triggering $name ($uuid)"
  local resp deployment_uuid
  resp="$(coolify_api GET "/deploy?uuid=$uuid")" \
    || { log "deploy: API trigger failed for $name"; FAILED=1; return 0; }
  deployment_uuid="$(echo "$resp" | jq -r '.deployments[0].deployment_uuid // empty')"
  [[ -z "$deployment_uuid" ]] \
    && { log "deploy: no deployment_uuid returned for $name: $resp"; FAILED=1; return 0; }

  # Poll the deployment until it leaves in_progress/queued or we time out.
  local waited=0 status
  while (( waited < DEPLOY_TIMEOUT_SECONDS )); do
    status="$(coolify_api GET "/deployments/$deployment_uuid" | jq -r '.status // "unknown"')"
    case "$status" in
      finished)            log "deploy: $name finished"; return 0 ;;
      failed|cancelled*)   log "deploy: $name ended with status=$status"; FAILED=1; return 0 ;;
      *)                   sleep 10; waited=$(( waited + 10 )) ;;
    esac
  done
  log "deploy: $name timed out after ${DEPLOY_TIMEOUT_SECONDS}s (status=$status)"
  FAILED=1
}

for_each_pair "$NOVA_SERVICES" deploy_service

if (( FAILED )); then
  die "one or more deployments failed"
fi
log "deploy: all requested services deployed"
