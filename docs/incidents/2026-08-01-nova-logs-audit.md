# Audit: why application 'nova' cannot produce logs

**App:** nova · UUID `w13ad9wlmjv2yjh1s7p3nip6` · repo https://github.com/rbnbrls/nova.git (main, HEAD `ef497b0` at audit time)
**Coolify:** v4.1.2 at dev.7rb.nl · server `nova-ai` (192.168.3.190, VMID 110, no GPU)
**Audited:** 2026-08-03 · build pack `dockercompose` · compose file `/docker-compose.yml`

## Status update (2026-08-03, after fix + redeploy)

The repo-side recommendations below were implemented and verified live:

1. **Logging fixed** — commits `79a01da` ("fix: configure Python logging so nova-core INFO logs reach stdout") and `7de2a61` ("fix: bind logging handler to nova-core logger so it survives alembic fileConfig"). The handler is bound to the `nova-core` logger with `propagate=False` because alembic's `fileConfig` resets the root logger at migration time. `docker logs nova-core` now shows app lines in their own format, e.g. `2026-08-03 08:26:30,544 ERROR [nova-core] Agent loop failed: ...` and `WARNING [nova-core] CardDAV startup sync failed ...`. INFO level is applied from `NOVA_LOG_LEVEL` (default INFO).
2. **Healthchecks added** — commit `f7ee68f` ("fix: add healthchecks to all docker-compose services") added healthchecks to the 6 services that lacked them (ollama, whisper, piper, caddy, radicale, vector). Coolify status moved from `running:unknown` to **`running:healthy`**, confirmed live via `GET /api/v1/applications/w13ad9wlmjv2yjh1s7p3nip6` (status `running:healthy`, restart_count 0).
3. **Redeploy does not time out** — deployment `ohlshl0ojbxb9cdlitjyu6r8` (and later `hd98s65yj13n8euq3pkjclir` on commit `9fb3753`) finished in ~60s with 0 error log lines.
4. **Test hygiene** — commit `9fb3753` ("test: mock _bump_package in dependency-scan tests so they don't rewrite requirements.txt") fixed a test that was silently rewriting the real `requirements.txt`.

Remaining non-repo items are Coolify-side (root causes #2, #3) and are tracked separately; they do not block app health or log visibility.

See also the raw evidence capture: [docs/incidents/2026-08-01-nova-starting-unknown.md](./2026-08-01-nova-starting-unknown.md).

---

## Executive summary

The stack is **running and healthy** — verified live: `GET http://192.168.3.190:8080/health` → HTTP 200 `{"status":"ok","ollama_ready":true}`; ports 8080/8085/5232/10200/10300/80 open; deployment 701 finished cleanly 2026-08-03 06:46 (all 9 containers started, postgres healthy). The process stays up (restart_count 0, `restart: unless-stopped` everywhere). The "cannot produce logs" problem is therefore **not** a crash/uptime issue — it is a combination of (a) the application never configuring Python logging, and (b) Coolify's log surface for docker-compose apps showing the wrong container. A third, separate issue is intermittent deployment failures caused by a missing `coolify` Docker network on nova-ai.

## Prioritized root causes

### 1. [HIGH — repo] nova-core never configures Python logging; app INFO logs are silently dropped

- `config.py:14` defines `nova_log_level: str = "INFO"` — but **no code anywhere reads or applies it** (grep across `services/nova-core/` finds only the definition; the only `StreamHandler` lives in `alembic.ini`, unrelated).
- The app has **no `logging.basicConfig`, no handler, no `dictConfig`** in any module (verified by grep). All 160 `log.*` call sites (`log.info` ×40, `log.warning` ×97, `log.error` ×9, `log.debug` ×14 across agent.py, scheduler, tools, whisper, main.py, …) use `logging.getLogger("nova-core")`, which propagates to the **root logger — which has no handlers**.
- Consequence at runtime (uvicorn configures only its own `uvicorn*` loggers): every `log.info(...)` from Nova is silently discarded (root logger has no handler; Python's `lastResort` handler only catches WARNING+ on stderr). Only uvicorn access logs and WARNING/ERROR lines ever reach stdout/stderr → Coolify `docker logs` shows almost nothing meaningful from the application itself.
- Evidence: `services/nova-core/app/config.py:14`; zero handler config in `services/nova-core/app/`; Dockerfile `CMD ["uvicorn", "app.main:app", ...]` with no `--log-level` (default INFO) — the plumbing is fine, the app logger is not.
- **Fix (applied):** at startup (`main.py`) add a `StreamHandler` bound to the `nova-core` logger with level from `settings.nova_log_level`, `propagate=False`. This is the single highest-leverage fix.

### 2. [HIGH — Coolify] The app Logs API/endpoint returns an arbitrary container's logs, not nova-core

- Coolify `ApplicationsController::logs_by_uuid` **ignores the `container` query parameter** (it only reads `lines` and `show_timestamps`) and returns logs of `$containers->first()` from `docker ps -a --filter='label=coolify.applicationId=1'` (`app/Http/Controllers/Api/ApplicationsController.php:2370-2389`).
- Because this is a docker-compose build-pack app, **all 9 containers carry the `coolify.applicationId=1` label** (Coolify injects `defaultLabels()` into every compose service). `->first()` is therefore nondeterministic: repeated identical API calls returned, in order, **caddy logs → whisper (ctranslate2) logs → vector (maxprocs) logs** — never nova-core's uvicorn logs.
- Net effect: any consumer of `GET /api/v1/applications/{uuid}/logs` (scripts, dashboards, the default log view) sees logs from the wrong service, or a container with almost no output — indistinguishable from "the app produces no logs".
- The Livewire UI (`Logs.php` → `get-logs.blade.php`) actually renders one panel **per labeled container**, so all 9 panels exist in the web UI — but the first/default panel and any API consumer get an arbitrary container.
- Evidence: 6 repeated API calls returning 3 different containers; Coolify source (v4.1.2) as cited.
- **Fix (Coolify side, not in repo):** for compose apps, resolve the log target to the container whose `com.docker.compose.service` equals the app name (or honor `container=`); alternatively surface a container picker on the API. Until then, read logs per-container (e.g. `docker logs nova-core`).

### 3. [HIGH — infra/Coolify] Intermittent `network coolify not found` breaks deployments (and produces near-zero logs)

- Deployments 699 (2026-08-03 06:41) and 700 (06:43) **failed in ~2s** with:
  `Deployment failed: Error response from daemon: network coolify not found`
  followed by `No such container: …` (helper container never started) and `Failed to write deployment configurations`.
- Deployment 701 (06:45) then succeeded — so the `coolify` Docker network on nova-ai is **intermittently missing** (also failed 2026-08-01 07:11 the same way; succeeded 14:08 same day).
- Impact: failed deploys leave the app on the old image, produce essentially no log output (the failure is before build), and the UI shows a red failed deployment. The deployment pipeline is flaky until the network is recreated (`docker network create coolify` on nova-ai, or Coolify's network provisioning is fixed).
- This is a known Coolify pitfall (documented in the coolify-mcp skill: "network coolify not found — the server you're deploying to doesn't have the coolify Docker network").
- Evidence: deployment logs for `zc5y3ich…` (699), `elr3kh7s…` (Aug 1), and the succeeding `kvhqp3tgs…` (701).

### 4. [MEDIUM — Coolify] App status stuck at `running:unknown` despite a working health check

- Coolify config: `health_check_enabled: true`, `health_check_type: http`, `GET http://192.168.3.190:8080/health`, return 200, interval 30s — and the endpoint **does** return 200. Yet status = `running:unknown`, `last_online_at` only refreshed at deploy time (06:46:28).
- Reason: for docker-compose apps Coolify aggregates per-container docker health states (`ComplexStatusCheck` → `ContainerStatusAggregator`); 6 of the 9 compose services (**ollama, whisper, piper, caddy, radicale, vector — no `healthcheck:` in `docker-compose.yml`**) report no health → aggregate resolves to `running:unknown`.
- Impact: dashboard shows the app as "Unknown", monitoring/alerting on status is unreliable, and it reinforces the impression that the app is broken. Cosmetic for logs but worth fixing (add healthchecks to all compose services or map the app-level HTTP check into status).
- Evidence: `GET /api/v1/resources` (nova = `running:unknown`), docker-compose.yml healthchecks (only nova-core/postgres/ops-bridge have them), Coolify source aggregator.
- **Fix (applied):** healthchecks added to all 6 remaining compose services; status now `running:healthy`.

### 5. [LOW — observability] Vector log shipping to OpenObserve is a separate, silent-failure path

- `infra/vector/vector.yaml` ships docker logs + host metrics to OpenObserve (`http://${OPENOBSERVE_HOST}/api/${OPENOBSERVE_ORG}/docker/_json`, `tls.verify_certificate: false`, **sink `healthcheck.enabled: false`**).
- Env in Coolify: `OPENOBSERVE_HOST=openobserve-of62cx…` (Coolify-generated hostname), `OPENOBSERVE_LAN_IP=192.168.3.110` (pinned via `extra_hosts`). If OpenObserve's hostname/IP changes, Vector fails **silently** (healthcheck disabled) and "logs disappear" from OpenObserve while Coolify still shows the vector container as running.
- Impact: only relevant if the user's "no logs" complaint refers to OpenObserve rather than the Coolify UI. Verify OpenObserve actually receives `docker` stream.

### Ruled out (with evidence)

- **Process not staying up:** all 9 containers running since 06:46, `restart_count: 0`, `last_restart_at: null`, health endpoint live → not a crash/uptime issue.
- **stdout/stderr not captured:** no `logging:` driver in compose → default json-file driver; `PYTHONUNBUFFERED=1` set in both Dockerfiles; `docker logs` demonstrably returns data (the API returned caddy/whisper/vector logs) → Docker capture works.
- **Missing env vars / .env:** Coolify stores 41 env vars (incl. `POSTGRES_PASSWORD` set, 48 chars); compose parser auto-injects `env_file: ['.env']` per service; deployment log shows "Creating .env file with runtime variables" → env wiring is intact. (`AZURE_*`/`WHATSAPP_*` empty are legacy leftovers, harmless.)
- **Port mismatch:** `ports_exposes: 8080`, compose `8080:8080`, health check port 8080, `/health` returns 200 → port/config consistent.
- **GPU blocker (historical):** previous failure `nvidia-container-cli: initialization error: nvml error: driver not loaded` (GPU reservations on a GPU-less host) was **fixed in commit ef497b0** ("fix: remove GPU deploy config from ollama and whisper"); current compose has no `deploy.resources` GPU blocks and ollama/whisper run CPU-only.

## Recommended actions (priority order)

1. **Repo (done):** add `logging.basicConfig(level=settings.nova_log_level)`-equivalent handler at nova-core startup → the app's INFO logs appear in `docker logs`/Coolify immediately. (Root cause #1 — commits `79a01da`, `7de2a61`)
2. **Coolify (open):** fix/raise the compose-app log target resolution (honor `container=`, or map `com.docker.compose.service` to the app) so `GET /applications/{uuid}/logs` shows nova-core. (Root cause #2)
3. **Infra (open):** recreate/verify the `coolify` Docker network on nova-ai and confirm it persists across daemon restarts. (Root cause #3)
4. **Coolify config (done):** add `healthcheck:` to the remaining compose services so status reports healthy. (Root cause #4 — commit `f7ee68f`)
5. **Optional:** enable the Vector→OpenObserve sink healthcheck or alert on its failure. (Root cause #5)
