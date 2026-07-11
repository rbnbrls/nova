#!/usr/bin/env bash
# Forgejo issues CLI — the ops loop's interface to https://git.7rb.nl/ruben/nova/issues
#
# Usage:
#   ops/issue.sh create "<title>" <body-file> <label,label,...>   → prints issue number
#   ops/issue.sh comment <num> <body-file|->                      (- = stdin)
#   ops/issue.sh close <num>
#   ops/issue.sh label <num> add|remove <name>
#   ops/issue.sh body <num>                                       → prints title + body
#   ops/issue.sh list-autoheal                                    → open auto-heal issue numbers
#   ops/issue.sh setup-labels                                     → create the loop's labels

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require curl
require jq

[[ -n "${FORGEJO_TOKEN:-}" ]] || die "FORGEJO_TOKEN not set in ops/config.env"
API="${FORGEJO_URL%/}/api/v1/repos/$FORGEJO_REPO"

fapi() {
  # fapi <method> <path> [json-body]
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -fsS -X "$method" -H "Authorization: token $FORGEJO_TOKEN" \
      -H "Content-Type: application/json" -d "$body" "$API$path"
  else
    curl -fsS -X "$method" -H "Authorization: token $FORGEJO_TOKEN" "$API$path"
  fi
}

label_id() {
  # Resolve a label name to its numeric ID (Forgejo API wants IDs).
  fapi GET "/labels?limit=100" | jq -r --arg n "$1" '.[] | select(.name == $n) | .id'
}

label_ids_json() {
  # "a,b,c" → JSON array of IDs; warns about labels that don't exist.
  local names="$1" name id ids=()
  IFS=',' read -ra parts <<< "$names"
  for name in "${parts[@]}"; do
    name="${name## }"; name="${name%% }"
    [[ -z "$name" ]] && continue
    id="$(label_id "$name")"
    [[ -n "$id" ]] && ids+=("$id") || log "issue: label '$name' missing (run setup-labels)" >&2
  done
  printf '%s\n' "${ids[@]:-}" | jq -sc 'map(select(. != "") | tonumber? // .) | map(select(type=="number"))'
}

cmd="${1:?usage: issue.sh <create|comment|close|label|body|list-autoheal|setup-labels> ...}"
shift

case "$cmd" in
  create)
    title="${1:?title}" body_file="${2:?body-file}" labels="${3:-}"
    ids="$(label_ids_json "$labels")"
    payload="$(jq -n --arg t "$title" --rawfile b "$body_file" --argjson l "$ids" \
      '{title: $t, body: $b, labels: $l}')"
    fapi POST "/issues" "$payload" | jq -r '.number'
    ;;

  comment)
    num="${1:?issue number}" body_file="${2:?body-file or -}"
    if [[ "$body_file" == "-" ]]; then
      payload="$(jq -n --rawfile b /dev/stdin '{body: $b}')"
    else
      payload="$(jq -n --rawfile b "$body_file" '{body: $b}')"
    fi
    fapi POST "/issues/$num/comments" "$payload" >/dev/null
    ;;

  close)
    num="${1:?issue number}"
    fapi PATCH "/issues/$num" '{"state":"closed"}' >/dev/null
    ;;

  label)
    num="${1:?issue number}" action="${2:?add|remove}" name="${3:?label name}"
    id="$(label_id "$name")"
    [[ -n "$id" ]] || die "label '$name' does not exist (run setup-labels)"
    case "$action" in
      add)    fapi POST "/issues/$num/labels" "{\"labels\":[$id]}" >/dev/null ;;
      remove) fapi DELETE "/issues/$num/labels/$id" >/dev/null ;;
      *)      die "unknown label action: $action" ;;
    esac
    ;;

  body)
    num="${1:?issue number}"
    fapi GET "/issues/$num" | jq -r '"# " + .title + "\n\n" + (.body // "")'
    ;;

  list-autoheal)
    # Open, labeled auto-heal, not currently being worked (healing) or done (fix-ready).
    fapi GET "/issues?state=open&labels=auto-heal&type=issues&limit=50" \
      | jq -r '.[] | select((.labels | map(.name)) as $l
                 | ($l | index("healing") | not) and ($l | index("fix-ready") | not))
               | .number'
    ;;

  setup-labels)
    declare -A LABELS=(
      [incident]="#d73a4a" [monitoring]="#1d76db" [user]="#0e8a16"
      [auto-heal]="#fbca04" [healing]="#c2e0c6" [fix-ready]="#5319e7" [heal-failed]="#b60205"
    )
    existing="$(fapi GET "/labels?limit=100" | jq -r '.[].name')"
    for name in "${!LABELS[@]}"; do
      if grep -qx "$name" <<< "$existing"; then
        log "issue: label '$name' exists"
      else
        fapi POST "/labels" "$(jq -n --arg n "$name" --arg c "${LABELS[$name]}" \
          '{name: $n, color: $c}')" >/dev/null
        log "issue: created label '$name'"
      fi
    done
    ;;

  *) die "unknown command: $cmd" ;;
esac
