#!/usr/bin/env bash
# Self-heal a failed deployment: feed the incident report to Claude Code in
# headless mode, let it diagnose and fix the code, and commit the fix on a
# heal branch. Pushing (manual by default) re-triggers Coolify → closes the loop.
#
# Usage: ops/heal.sh <incident-file>

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require claude
require git
require jq

INCIDENT_FILE="${1:?usage: ops/heal.sh <incident-file>}"
[[ -f "$INCIDENT_FILE" ]] || die "incident file not found: $INCIDENT_FILE"
[[ "${HEAL_ENABLED,,}" == "true" ]] || die "healing disabled (HEAL_ENABLED=$HEAL_ENABLED)"

cd "$REPO_DIR"
[[ -z "$(git status --porcelain)" ]] || die "working tree not clean — refusing to heal on top of local changes"

TS="$(date '+%Y%m%d-%H%M%S')"
HEAL_BRANCH="${HEAL_BRANCH_PREFIX}-${TS}"
BASE_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git checkout -b "$HEAL_BRANCH"

cleanup_on_fail() {
  git checkout "$BASE_BRANCH" >/dev/null 2>&1 || true
  git branch -D "$HEAL_BRANCH" >/dev/null 2>&1 || true
}

PROMPT="You are the on-call engineer for Nova, a self-hosted household assistant \
deployed via Coolify from this repository. A deployment just failed its health \
checks. The full incident report (failed checks, container state, logs, recent \
commits) follows.

Your job, in order:
1. Diagnose the root cause from the incident report and the repository code.
2. Fix it with the smallest change that resolves the failure. Do not refactor.
3. If the cause is NOT fixable from this repo (e.g. host misconfiguration, \
missing secret in Coolify, external service down), do NOT change code — instead \
write your diagnosis to the file ${INCIDENT_FILE%.md}-diagnosis.md and stop.
4. If you changed code: verify it (python -m compileall for Python, config \
syntax checks where possible) and commit with message \
'fix(heal): <summary>' plus a body explaining root cause. Commit on the \
current branch. Do NOT push.

Incident report:

$(cat "$INCIDENT_FILE")"

log "heal: invoking Claude Code headless (branch $HEAL_BRANCH)"

CLAUDE_ARGS=(
  -p "$PROMPT"
  --output-format json
  --max-turns "${CLAUDE_MAX_TURNS:-40}"
  --permission-mode acceptEdits
  --allowedTools "Read,Grep,Glob,Edit,Write,Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git add:*),Bash(git commit:*),Bash(python3:*),Bash(docker logs:*),Bash(docker ps:*),Bash(docker compose config:*)"
)
[[ -n "${CLAUDE_MODEL:-}" ]] && CLAUDE_ARGS+=(--model "$CLAUDE_MODEL")

RESULT_JSON="$INCIDENT_DIR/heal-$TS.json"
if ! claude "${CLAUDE_ARGS[@]}" > "$RESULT_JSON"; then
  log "heal: claude invocation failed — see $RESULT_JSON"
  cleanup_on_fail
  exit 1
fi

log "heal: result → $(jq -r '.result // "no result field"' "$RESULT_JSON" | head -5)"

# Did Claude actually commit a fix?
if [[ -z "$(git log "$BASE_BRANCH..$HEAL_BRANCH" --oneline)" ]]; then
  log "heal: no fix committed (likely diagnosed as not repo-fixable) — see ${INCIDENT_FILE%.md}-diagnosis.md"
  cleanup_on_fail
  exit 2
fi

log "heal: fix committed on $HEAL_BRANCH:"
git log "$BASE_BRANCH..$HEAL_BRANCH" --oneline

if [[ "${HEAL_AUTO_PUSH,,}" == "true" ]]; then
  if [[ "${HEAL_PUSH_TO_MAIN,,}" == "true" ]]; then
    log "heal: auto-merging into $BASE_BRANCH and pushing (fully autonomous mode)"
    git checkout "$BASE_BRANCH"
    git merge --no-edit "$HEAL_BRANCH"
    git push origin "$BASE_BRANCH"
  else
    log "heal: pushing $HEAL_BRANCH for review"
    git push -u origin "$HEAL_BRANCH"
    git checkout "$BASE_BRANCH"
  fi
else
  git checkout "$BASE_BRANCH"
  log "heal: fix ready on $HEAL_BRANCH — review with: git diff $BASE_BRANCH..$HEAL_BRANCH"
  log "heal: push to deploy: git push -u origin $HEAL_BRANCH (or merge to $BASE_BRANCH)"
fi
