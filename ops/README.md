# Nova Ops — Closed-Loop CI/CD

Infra-as-code deployment with an observe → log → self-heal feedback cycle around
Coolify, using **Claude Code headless** as the on-call engineer.

```
              ┌────────────────────────────────────────────────┐
              │                                                │
 git push ──► Coolify build+deploy ──► observe.sh              │
              (webhook / deploy.sh)    health + container +    │
                       ▲               log checks              │
                       │                    │ failure          │
                       │                    ▼                  │
                heal branch push ◄── heal.sh ◄── incident-*.md │
                (or auto-merge)      claude -p    structured   │
                                     diagnose+fix  issue log   │
              └────────────────────────────────────────────────┘
```

## Components

| Script | Role |
|---|---|
| `deploy.sh` | Infra as code: triggers Coolify deployments via its API and waits for completion. The *stack definition* itself is `docker-compose.yml` + Coolify resource config. |
| `observe.sh` | Post-deploy verification: polls health endpoints, inspects container state, and on failure writes a structured **incident report** to `ops/incidents/` (the "log issues" step). |
| `heal.sh` | Feeds the incident to `claude -p` (headless Claude Code) with a constrained tool allowlist. Claude diagnoses from logs + code, applies the smallest fix, verifies, and commits on a `nova/heal-<ts>` branch. Non-repo causes get a written diagnosis instead of a code change. |
| `pipeline.sh` | Orchestrates the loop: deploy → observe → heal → redeploy, capped by `HEAL_MAX_ATTEMPTS`. |
| `incidents/` | Audit trail: every incident report, Claude diagnosis, and heal-run JSON transcript. (Gitignored except `.gitkeep`.) |

## Setup

1. On the Nova AI VM (needs: repo checkout, `docker`, `jq`, `curl`, `git`, and
   an authenticated `claude` CLI):
   ```bash
   cp ops/config.env.example ops/config.env   # fill in Coolify token + UUIDs
   chmod +x ops/*.sh
   ```
2. Wire the loop to deployments — either:
   - **Coolify webhook**: point the post-deployment webhook at a tiny endpoint
     that runs `ops/pipeline.sh`, or
   - **systemd timer** (simplest), running the loop a few minutes after pushes:

   ```ini
   # /etc/systemd/system/nova-ops-loop.service
   [Service]
   Type=oneshot
   WorkingDirectory=/opt/nova
   ExecStart=/opt/nova/ops/pipeline.sh
   User=nova

   # /etc/systemd/system/nova-ops-loop.timer
   [Timer]
   OnCalendar=*:0/15        # every 15 min; observe is cheap when healthy
   [Install]
   WantedBy=timers.target
   ```

## Autonomy levels

Controlled in `config.env` — start supervised, earn autonomy:

| Level | Settings | Behavior |
|---|---|---|
| **Supervised** (default) | `HEAL_AUTO_PUSH=false` | Fix committed locally on a heal branch; you review + push. |
| **Review-gated** | `HEAL_AUTO_PUSH=true` | Fix branch pushed for review; merging deploys it. |
| **Autonomous** | + `HEAL_PUSH_TO_MAIN=true` | Fix merged + pushed to `main` → Coolify redeploys → loop re-observes. Capped by `HEAL_MAX_ATTEMPTS`. |

## Guardrails on the healing agent

- `--permission-mode acceptEdits` with an explicit `--allowedTools` allowlist:
  read/search tools, file edits, and only scoped Bash (`git status/diff/log/add/commit`,
  `python3`, `docker logs/ps`, `docker compose config`). No pushes, no container
  restarts, no arbitrary shell.
- `--max-turns` caps runaway sessions; every run's JSON transcript is kept in
  `ops/incidents/heal-<ts>.json`.
- Refuses to run on a dirty working tree; failed runs clean up their branch.
- Non-code root causes (missing Coolify secret, host issue) produce a
  `*-diagnosis.md` file instead of a code change — the loop stops and asks a human.
