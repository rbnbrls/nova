# Nova Deployment State & Hidden Logs — Raw Evidence

**Task:** t_d7549f69 — Capture current deployment state and hidden logs for nova
**Captured:** 2026-08-03 ~06:47 UTC (from hermesagent 192.168.3.132)
**App:** nova (Coolify UUID `w13ad9wlmjv2yjh1s7p3nip6`)
**Repo:** https://github.com/rbnbrls/nova.git (branch `main`)
**Coolify instance:** https://dev.7rb.nl (Coolify 4.1.2)
**Target server:** nova-ai (192.168.3.190, Proxmox VMID 110)

---

## 1. Summary of findings

1. **The original `starting:unknown` + empty-logs incident is RESOLVED.** The
   two failed deployments on 2026-08-01 (commit `d58350e`) failed at container
   **create** time with an OCI prestart-hook error
   (`nvidia-container-cli: initialization error: nvml error: driver not loaded`).
   Containers never started, so `docker logs` was empty — which is exactly why
   Coolify reported "no log output available" and the app sat at
   `starting:unknown`.
2. **Root cause of the original failure** (confirmed in hidden deployment log
   entries): `docker-compose.yml` had GPU `deploy.resources.reservations.devices`
   blocks on `ollama` and `whisper` requesting the `nvidia` runtime, but the
   nova-ai VM has **no NVIDIA driver/GPU** (Proxmox host has no NVIDIA).
3. **Fix** (commit `ef497b0` "fix: remove GPU deploy config from ollama and
   whisper", deployed 2026-08-01T14:08Z, deployment `f1ofkscca73zhbdo1adf1c85`
   → **finished**) removed the GPU blocks. Current running image tags confirm:
   `w13ad9wlmjv2yjh1s7p3nip6_nova-core:ef497b04...`.
4. **Current state (healthy):** all 10 nova stack containers are Up; nova-core,
   postgres, ops-bridge, radicale are `(healthy)`; `GET /health` on
   192.168.3.190:8080 returns `HTTP 200 {"status":"ok","ollama_ready":true}`.
5. **New observation (2026-08-03 06:41–06:45 UTC):** a redeploy of the same
   commit `ef497b04` failed twice with a *different* hidden error —
   `Error response from daemon: network coolify not found` — then succeeded on
   the third attempt (`kvhqp3tgs26hfhi555qtrtxx` → **finished**) once the
   `coolify` network existed again on the host. The `coolify` network is
   currently present (`docker network ls`), and all containers are attached to
   `nova-net` + the per-app network. This is a transient infra issue
   (Coolify's `delete_unused_networks: true` + daily docker cleanup can remove
   the shared `coolify` network), not an app bug.
6. **GitHub issue #1** is **closed** (2026-08-01T14:22Z) with a fix summary
   comment from `rbnbrls`.

---

## 2. Exact commands run (Coolify API)

```bash
# Token sourced from ~/.hermes/config.yaml mcp_servers.coolify.headers.Authorization
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://dev.7rb.nl/api/v1/deployments/applications/w13ad9wlmjv2yjh1s7p3nip6?per_page=100&page=1"
# → count: 131 (page 1 of deployment history)

curl -s -H "Authorization: Bearer $TOKEN" "https://dev.7rb.nl/api/v1/deployments/<deployment_uuid>"
# → full deployment log JSON, incl. hidden entries (used for each UUID below)
```

### Deployment history (most recent 10)

| deployment_uuid                  | status   | created_at (UTC)       | commit         |
|----------------------------------|----------|------------------------|----------------|
| kvhqp3tgs26hfhi555qtrtxx        | finished | 2026-08-03 06:45:12    | ef497b04c36c   |
| phtv911iijanv8opt4tu5xsy        | failed   | 2026-08-03 06:43:55    | HEAD           |
| zc5y3ichdiec4imjh8vptu5g        | failed   | 2026-08-03 06:41:38    | HEAD           |
| f1ofkscca73zhbdo1adf1c85        | finished | 2026-08-01 14:08:50    | ef497b04c36c   |
| k12grr2pasnah9z17go8o26p        | failed   | 2026-08-01 07:23:45    | d58350e905e3   |
| o8ip9fz06ax1v81npk958h5p        | failed   | 2026-08-01 07:20:58    | d58350e905e3   |
| elr3kh7slg3newsrz4yah8p2        | failed   | 2026-08-01 07:11:23    | HEAD           |
| sj2qh1yw90wscv0l6gjqw1cs        | failed   | 2026-07-23 23:17:19    | HEAD           |
| cupptbvhvt9ku8tovgc4cjel        | failed   | 2026-07-23 23:05:14    | HEAD           |
| hbxbrwme20ps42otm2cisizf        | failed   | 2026-07-23 22:56:03    | HEAD           |

### Hidden error #1 — original GPU failure (deployments k12grr2 / o8ip9fz, commit d58350e)

From `GET /api/v1/deployments/k12grr2pasnah9z17go8o26p` (log entry, `hidden=false`):

```
Error response from daemon: failed to create task for container: failed to create
shim task: OCI runtime create failed: runc create failed: unable to start container
process: error during container init: error running prestart hook #0: exit status 1,
stdout: , stderr: Auto-detected mode as 'legacy'
nvidia-container-cli: initialization error: nvml error: driver not loaded

Deployment failed: Command execution failed (exit code 1):
COOLIFY_BRANCH='main' COOLIFY_RESOURCE_UUID=w13ad9wlmjv2yjh1s7p3nip6
docker compose --env-file /data/coolify/applications/w13ad9wlmjv2yjh1s7p3nip6/.env
  --project-name w13ad9wlmjv2yjh1s7p3nip6
  --project-directory /data/coolify/applications/w13ad9wlmjv2yjh1s7p3nip6
  -f /data/coolify/applications/w13ad9wlmjv2yjh1s7p3nip6/docker-compose.yml up -d
```

Hidden stack trace: `Error type: App\Exceptions\DeploymentException`, raised at
`app/Traits/ExecuteRemoteCommand.php:242` in `ApplicationDeploymentJob`.
**Why logs were empty:** the OCI runtime failed *before* the container process
started (NVIDIA prestart hook), so the containers never produced any stdout —
`docker logs` had nothing to show, and Coolify's status stayed `starting:unknown`.

### Hidden error #2 — transient network error on 2026-08-03 redeploy (zc5y3ich / phtv911)

```
Deployment failed: Error response from daemon: network coolify not found
Error type: RuntimeException
Error code: 1
```

Both 06:41 and 06:43 attempts hit this; the 06:45 attempt succeeded. The
`coolify` network exists on the host now (see `docker network ls` below).

---

## 3. Exact commands run (host nova-ai, via Coolify deploy key `nova-vm-deploy`)

```bash
ssh -i /tmp/nova-vm-deploy.key -o StrictHostKeyChecking=accept-new root@192.168.3.190 '<cmd>'
```

### docker ps -a

```
$ docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"
NAMES                                              STATUS                        IMAGE                                                                          PORTS
caddy-w13ad9wlmjv2yjh1s7p3nip6-064518440049        Up About a minute             caddy:2                                                                        0.0.0.0:80->80/tcp, [::]:80->80/tcp, 0.0.0.0:443->443/tcp, [::]:443->443/tcp, 443/udp, 2019/tcp
nova-core-w13ad9wlmjv2yjh1s7p3nip6-064518404938    Up About a minute (healthy)   w13ad9wlmjv2yjh1s7p3nip6_nova-core:ef497b04c36c2f8e4c0d018adac48bb68cfe03e8    0.0.0.0:8080->8080/tcp, [::]:8080->8080/tcp
postgres-w13ad9wlmjv2yjh1s7p3nip6-064518409878     Up About a minute (healthy)   pgvector/pgvector:pg16                                                         5432/tcp
vector-w13ad9wlmjv2yjh1s7p3nip6-064518427534       Up About a minute             timberio/vector:latest-alpine
ops-bridge-w13ad9wlmjv2yjh1s7p3nip6-064518432257   Up About a minute (healthy)   w13ad9wlmjv2yjh1s7p3nip6_ops-bridge:ef497b04c36c2f8e4c0d018adac48bb68cfe03e8   0.0.0.0:8085->8080/tcp, [::]:8085->8080/tcp
piper-w13ad9wlmjv2yjh1s7p3nip6-064518423448        Up About a minute             rhasspy/wyoming-piper:latest                                                   0.0.0.0:10200->10200/tcp, [::]:10200->10200/tcp
radicale-w13ad9wlmjv2yjh1s7p3nip6-064518432773     Up About a minute (healthy)   tomsquest/docker-radicale:latest                                               0.0.0.0:5232->5232/tcp, [::]:5232->5232/tcp
whisper-w13ad9wlmjv2yjh1s7p3nip6-064518419566      Up About a minute             rhasspy/wyoming-whisper:latest                                                   0.0.0.0:10300->10300/tcp, [::]:10300->10300/tcp
ollama-w13ad9wlmjv2yjh1s7p3nip6-064518416422       Up About a minute             ollama/ollama:latest                                                           11434/tcp
coolify-sentinel                                   Up 22 hours (healthy)         coollabsio/sentinel:0.0.21
```

(Container suffix `064518...` = deployment `kvhqp3tgs26hfhi555qtrtxx`, 06:45:18 UTC.)

### docker network ls

```
$ docker network ls
NETWORK ID     NAME                       DRIVER    SCOPE
95208307503f   bridge                     bridge    local
314812cbfe9f   coolify                    bridge    local
ff0d17a30640   host                       host      local
b4a73500b1a8   none                       null      local
f6563a6ae161   nova-net                   bridge    local
3676cc02af99   w13ad9wlmjv2yjh1s7p3nip6   bridge    local
```

### docker inspect (network mode)

```
$ docker inspect --format "{{.Name}} network={{.HostConfig.NetworkMode}}" nova-core-w13ad9wlmjv2yjh1s7p3nip6-064518404938
/nova-core-w13ad9wlmjv2yjh1s7p3nip6-064518404938 network=nova-net
```

### docker logs — nova-core (tail, --timestamps)

Healthy probe traffic only, e.g.:
```
2026-08-03T06:46:31.935389787Z INFO:     127.0.0.1:59088 - "GET /health HTTP/1.1" 200 OK
2026-08-03T06:46:51.532552429Z INFO:     192.168.3.132:45492 - "GET /health HTTP/1.1" 200 OK
...
2026-08-03T06:40:04.189136812Z WARNI [nova-core.scheduler] check_new_emails failed: command UID only possible with COPY, FETCH, EXPUNGE (w/UIDPLUS) or STORE (was SEARCH)
```
(The scheduler email warning is a separate, non-deployment issue — an IMAP
UID command incompatibility in the email tool stub.)

### docker logs — caddy (tail)

```
2026-08-03T06:46:26.929149994Z {"level":"info","ts":...,"msg":"using config from file","file":"/etc/caddy/Caddyfile"}
... "server running","name":"srv0" ... "enabling automatic TLS certificate management","domains":["nova.local"]"
```
No proxy/healthcheck errors. Caddy serves `nova.local` with the local CA.

### docker logs — whisper (tail)

```
2026-08-03T06:46:17.656606415Z [2026-08-03 06:46:17.656] [ctranslate2] [thread 7] [warning] The compute type inferred from the saved model is float16, but the target device or backend do not support efficient float16 computation. The model weights have been automatically converted to use the float32 compute type instead.
2026-08-03T06:46:17.687196428Z INFO:__main__:Ready
```
This confirms CPU-only operation (float16 → float32 fallback) — consistent with
the GPU config removal.

### docker logs — ollama (tail)

```
2026-08-03T06:46:16.266450188Z time=2026-08-03T06:46:16.266Z level=INFO source=routes.go:2054 msg="vram-based default context" total_vram="0 B" default_num_ctx=4096
2026-08-03T06:46:31.934658374Z [GIN] 2026/08/03 - 06:46:31 | 200 | ... | GET "/api/version"
```
`total_vram="0 B"` confirms no GPU visible to ollama — CPU inference.

### Health check (from hermesagent)

```
$ curl -s -o /dev/null -w "HTTP %{http_code}" http://192.168.3.190:8080/health
HTTP 200
$ curl -s http://192.168.3.190:8080/health
{"status":"ok","ollama_ready":true}
```

---

## 4. Coolify app config (GET /api/v1/applications/w13ad9wlmjv2yjh1s7p3nip6)

Key fields:
- `build_pack: dockercompose`, `docker_compose_location: /docker-compose.yml`
- `status: running:unknown` (Coolify's runtime status; host-side all containers Up)
- `health_check_path: /health`, `health_check_port: 8080`, `health_check_host: 192.168.3.190`
- `ports_exposes: 8080`, `limits_memory/swap/reservation: "0"`
- `last_online_at: 2026-08-01 14:09:16`
- `restart_count: 0`, `max_restart_count: 10`
- `is_reachable: true` (server nova-ai)

---

## 5. GitHub issue #1 state

- https://github.com/rbnbrls/nova/issues/1 — **closed** 2026-08-01T14:22:14Z
- One comment from `rbnbrls` (2026-08-01T14:22:03Z): "Fix Applied – Deployment Recovery Complete"
  summarizing the GPU config mismatch and the port fix.
- Timeline: `labeled` (07:25:46Z) → `commented` (14:22:03Z) → `closed` (14:22:14Z).

---

## 6. Files in this bundle

- `EVIDENCE_REPORT.md` — this file
- `docker_ps_a.txt` — `docker ps -a` full output
- `docker_ps_running.txt` — `docker ps` (running) output
- `docker_network_ls.txt` — `docker network ls` output
- `docker_inspect_network.txt` — nova-core network mode
- `docker_logs_nova_core.txt` — nova-core logs (timestamps, tail 40)
- `docker_logs_caddy.txt` — caddy logs (timestamps, tail 25)
- `docker_logs_ollama.txt` — ollama logs (timestamps, tail 10)
- `docker_logs_whisper.txt` — whisper logs (timestamps, tail 10)
- `docker_events_30m.txt` — `docker events` 30-min window (filtered)
- `health_check.txt` — curl /health output
- `dep_*.json` — raw Coolify deployment log JSON for the 7 deployments examined
  (f1ofkscca73zhbdo1adf1c85, k12grr2pasnah9z17go8o26p, o8ip9fz06ax1v81npk958h5p,
  elr3kh7slg3newsrz4yah8p2, zc5y3ichdiec4imjh8vptu5g, phtv911iijanv8opt4tu5xsy,
  kvhqp3tgs26hfhi555qtrtxx)
- `nova_deployments.json` — deployment history JSON (per-app endpoint)
