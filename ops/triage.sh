#!/usr/bin/env bash
# Triage worker: poll Forgejo for open issues labeled `auto-heal` (from
# OpenObserve alerts, deploy failures, or users who added the label), run the
# Claude Code heal on each, and report the outcome back on the issue.
#
# Label protocol:
#   auto-heal    input gate — only these issues are picked up
#   healing      lock — set while a heal run is in progress
#   fix-ready    heal produced a committed fix awaiting review/merge
#   heal-failed  heal ran but produced no deployable fix (diagnosis commented)
#
# Run from a systemd timer (see ops/README.md). Exit 0 = at least one fix
# produced (or nothing to do); 1 = all attempted heals failed.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require jq

ISSUE="$OPS_DIR/issue.sh"
HEAL="$OPS_DIR/heal.sh"
mkdir -p "$INCIDENT_DIR"

mapfile -t QUEUE < <("$ISSUE" list-autoheal)

if [[ ${#QUEUE[@]} -eq 0 ]]; then
  log "triage: no open auto-heal issues"
  exit 0
fi
log "triage: ${#QUEUE[@]} issue(s) queued: ${QUEUE[*]}"

ANY_FIX=0 ANY_FAIL=0

for num in "${QUEUE[@]}"; do
  log "triage: picking up issue #$num"
  "$ISSUE" label "$num" add healing

  body_file="$(mktemp "/tmp/nova-issue-${num}-XXXXXX")"
  "$ISSUE" body "$num" > "$body_file"

  set +e
  heal_out="$("$HEAL" "$body_file" 2>&1)"
  heal_rc=$?
  set -e
  rm -f "$body_file"

  case $heal_rc in
    0)
      branch="$(echo "$heal_out" | tail -1)"
      ANY_FIX=1
      {
        echo "🤖 **Heal run succeeded** — fix committed on branch \`$branch\`."
        echo
        if [[ "${HEAL_AUTO_PUSH,,}" == "true" && "${HEAL_PUSH_TO_MAIN,,}" == "true" ]]; then
          echo "Merged to main and pushed — Coolify is redeploying. This issue will be closed."
        elif [[ "${HEAL_AUTO_PUSH,,}" == "true" ]]; then
          echo "Branch pushed for review: merge it to deploy the fix."
        else
          echo "Fix is local on the ops host. Review: \`git diff main..$branch\`"
        fi
        echo
        echo "<details><summary>Heal log</summary>"
        echo
        echo '```'
        echo "$heal_out" | tail -40
        echo '```'
        echo "</details>"
      } | "$ISSUE" comment "$num" -
      "$ISSUE" label "$num" add fix-ready
      if [[ "${HEAL_AUTO_PUSH,,}" == "true" && "${HEAL_PUSH_TO_MAIN,,}" == "true" ]]; then
        "$ISSUE" close "$num"
      fi
      ;;
    2)
      ANY_FAIL=1
      {
        echo "🤖 **Heal run: not repo-fixable.** Claude diagnosed the incident but"
        echo "the root cause is outside this repository (host, secret, or external service)."
        echo
        diag="$(ls -t "$INCIDENT_DIR"/*-diagnosis.md 2>/dev/null | head -1)"
        if [[ -n "$diag" ]]; then
          echo "### Diagnosis"
          echo
          cat "$diag"
        else
          echo '```'
          echo "$heal_out" | tail -40
          echo '```'
        fi
        echo
        echo "_Human intervention required._"
      } | "$ISSUE" comment "$num" -
      "$ISSUE" label "$num" add heal-failed
      ;;
    *)
      ANY_FAIL=1
      {
        echo "🤖 **Heal run failed** (exit $heal_rc). See transcript on the ops host."
        echo
        echo '```'
        echo "$heal_out" | tail -40
        echo '```'
      } | "$ISSUE" comment "$num" -
      "$ISSUE" label "$num" add heal-failed
      ;;
  esac

  "$ISSUE" label "$num" remove healing
  # Failed issues keep auto-heal removed so the timer doesn't retry them forever.
  if (( heal_rc != 0 )); then
    "$ISSUE" label "$num" remove auto-heal
  fi
done

(( ANY_FIX == 1 || ANY_FAIL == 0 )) && exit 0 || exit 1
