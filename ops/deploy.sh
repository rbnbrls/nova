#!/usr/bin/env bash
# Deploy the Nova stack as code: trigger Coolify deployments via API and wait
# for them to finish. Exit 0 = all services deployed; non-zero = deploy failed.
#
# Usage: ops/deploy.sh [--staging|--prod|--all] [service-name ...]
#   --staging  (default) deploy staging services only
#   --prod     deploy production services only
#   --all      deploy both staging and production
#   service-name  deploy specific service(s) regardless of target

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require curl
require jq

# Parse arguments
DEPLOY_TARGET="staging"  # default: staging-first
declare -a ONLY_SERVICES=()

for arg in "$@"; do
  case "$arg" in
    --all)  DEPLOY_TARGET="all" ;;
    --prod) DEPLOY_TARGET="prod" ;;
    --staging) DEPLOY_TARGET="staging" ;;
    --help)
      echo "Usage: $0 [--staging|--prod|--all] [service-name ...]"
      echo "  --staging  (default) deploy staging services only"
      echo "  --prod     deploy production services only"
      echo "  --all      deploy both staging and production"
      echo "  service-name  deploy specific service(s) regardless of target"
      exit 0
      ;;
    *)
      ONLY_SERVICES+=("$arg")
      ;;
  esac
done

wants_service() {
  [[ ${#ONLY_SERVICES[@]} -eq 0 ]] && return 0
  local s
  for s in "${ONLY_SERVICES[@]}"; do [[ "$s" == "$1" ]] && return 0; done
  return 1
}

FAILED=0

# ── Select service list based on target ─────────────────────────────────────
STAGING_SERVICES="${STAGING_SERVICES:-$NOVA_SERVICES}"
PROD_SERVICES="${PROD_SERVICES:-$NOVA_SERVICES}"

case "$DEPLOY_TARGET" in
  staging)
    log "deploy: staging-first mode — deploying staging services"
    SELECTED_SERVICES="$STAGING_SERVICES"
    ;;
  prod)
    log "deploy: production-only mode"
    SELECTED_SERVICES="$PROD_SERVICES"
    ;;
  all)
    log "deploy: deploying staging first, then production"
    for_each_pair "$STAGING_SERVICES" deploy_service
    log "deploy: staging deployed, waiting 15s before production deploy …"
    sleep 15
    SELECTED_SERVICES="$PROD_SERVICES"
    ;;
esac

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

if [[ "$DEPLOY_TARGET" != "all" ]]; then
  for_each_pair "$SELECTED_SERVICES" deploy_service
fi

if (( FAILED )); then
  die "one or more deployments failed"
fi
log "deploy: all requested services deployed"
