# Nova Ops — Closed-Loop Incident Management & CI/CD

One incident queue, two producers, one automated consumer:

```
                       Docker stack (compose)
                          │ logs + metrics
                          ▼
                       Vector ──► OpenObserve  (Coolify service)
                                      │ alert webhook (X-Bridge-Token)
                                      ▼
 Ruben / Méral ──file issue──►  ops-bridge (dedup by fingerprint)
        │                             │ create / comment
        ▼                             ▼
   ┌──────────────────────────────────────────────────┐
   │  Forgejo issues — git.7rb.nl/ruben/nova/issues   │   ◄── observe.sh
   │  (single source of truth for incidents)          │       (deploy failures)
   └──────────────────────┬───────────────────────────┘
                          │ open + `auto-heal` label
                          ▼
                triage.sh (systemd timer)
                          │
                heal.sh — claude -p (headless, tool-allowlisted)
                          │
        fix branch ──► comment + `fix-ready` ──► merge ──► Coolify redeploys
        (or auto-merge to main when fully autonomous)  ──► observe verifies ✔
```

## Label protocol

| Label | Meaning |
|---|---|
| `incident` / `monitoring` / `user` | Provenance. Bridge + observe set `incident,monitoring`; humans use `user`. |
| `auto-heal` | **The gate.** Only issues with this label are picked up by triage. Alert/deploy issues get it automatically; add it manually to user issues you trust Claude with. |
| `healing` | Lock while a heal run is in progress. |
| `fix-ready` | A committed fix exists (branch named in the issue comment) awaiting review/merge. |
| `heal-failed` | Heal ran, no deployable fix; diagnosis commented, `auto-heal` removed — a human takes over. |

Create them once: `ops/issue.sh setup-labels`.

## Components

| Piece | Role |
|---|---|
| `infra/vector/vector.yaml` + `vector` service | Ships all container logs + host metrics into OpenObserve. |
| OpenObserve (Coolify service) | Dashboards, log search, **alerts**. Each alert gets a webhook destination pointing at ops-bridge. |
| `services/ops-bridge/` | FastAPI webhook receiver: authenticates (`X-Bridge-Token`), fingerprints the alert, dedups against open issues, creates/comments Forgejo issues with `incident,monitoring,auto-heal`. |
| `issue.sh` | Forgejo API CLI: `create`, `comment`, `close`, `label`, `body`, `list-autoheal`, `setup-labels`. |
| `deploy.sh` | Triggers Coolify deployments via API and waits for completion. |
| `observe.sh` | Post-deploy verification; failures become Forgejo issues (health results, container state, log tails, recent commits). |
| `triage.sh` | The consumer: polls open `auto-heal` issues, locks with `healing`, runs `heal.sh`, comments the outcome + heal log on the issue, applies `fix-ready`/`heal-failed`. |
| `heal.sh` | Claude Code headless (`claude -p`, `--permission-mode acceptEdits`, strict `--allowedTools`, `--max-turns`). Smallest fix, verified, committed on `nova/heal-<ts>`. Non-repo causes → written diagnosis, no code change. |
| `pipeline.sh` | Deploy → observe → triage loop for push-triggered runs, capped by `HEAL_MAX_ATTEMPTS`. |
| `incidents/` | Local artifacts only: claude JSON transcripts + diagnosis files. Issues are the record. |

## Setup

1. **Forgejo**: create an API token (issue read/write) → `FORGEJO_TOKEN` in both
   `.env` (for ops-bridge) and `ops/config.env` (for the scripts). Then:
   ```bash
   cp ops/config.env.example ops/config.env    # fill in Coolify + Forgejo
   ops/issue.sh setup-labels
   ```
2. **OpenObserve** (Coolify service): note URL/org/user/password into `.env`
   (`OPENOBSERVE_*`) — Vector starts shipping on next deploy. For each alert,
   add a webhook destination:
   - URL: `http://<nova-vm>:8085/webhooks/openobserve`
   - Header: `X-Bridge-Token: <BRIDGE_TOKEN from .env>`
   - Body: OpenObserve's default alert JSON is fine (bridge reads `alert_name`/`stream_name`).
   - Set a silence period (e.g. 30 min) per alert; the bridge also dedups by fingerprint.
3. **Triage timer** on the ops host (repo checkout + docker + jq + curl + git +
   authenticated `claude` CLI):

   ```ini
   # /etc/systemd/system/nova-triage.service
   [Service]
   Type=oneshot
   WorkingDirectory=/opt/nova
   ExecStart=/opt/nova/ops/triage.sh
   User=nova

   # /etc/systemd/system/nova-triage.timer
   [Timer]
   OnCalendar=*:0/5          # poll the issue queue every 5 minutes
   [Install]
   WantedBy=timers.target
   ```

## User workflow

File an issue at https://git.7rb.nl/ruben/nova/issues describing the problem
(label it `user`). If you want Claude to attempt it autonomously, add the
`auto-heal` label — the next triage tick picks it up, works it, and reports
back as a comment on your issue. Everything Claude did is auditable there.

## Autonomy levels

| Level | Settings | Behavior |
|---|---|---|
| **Supervised** (default) | `HEAL_AUTO_PUSH=false` | Fix committed locally on a heal branch; issue gets `fix-ready` + instructions. |
| **Review-gated** | `HEAL_AUTO_PUSH=true` | Fix branch pushed; merge on Forgejo to deploy. |
| **Autonomous** | + `HEAL_PUSH_TO_MAIN=true` | Fix merged + pushed → Coolify redeploys → observe verifies → issue closed. Capped by `HEAL_MAX_ATTEMPTS`. |

## Guardrails on the healing agent

- `--permission-mode acceptEdits` + explicit `--allowedTools`: read/search, file
  edits, and only scoped Bash (`git status/diff/log/add/commit`, `python3`,
  `docker logs/ps`, `docker compose config`). No pushes, no restarts, no arbitrary shell.
- `--max-turns` caps runaway sessions; JSON transcripts kept in `ops/incidents/`.
- Refuses to run on a dirty working tree; failed runs delete their branch.
- `healing` label prevents double-processing; failed issues lose `auto-heal` so
  the timer never retries them unattended.
- Every action is a comment on the issue — full audit trail in Forgejo.
