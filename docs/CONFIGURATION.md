<!-- generated-by: gsd-doc-writer -->

# Nova Configuration

Nova is configured entirely through environment variables. The canonical reference is
`.env.example` in the project root, with additional ops-specific settings in
`ops/config.env.example` and staging overrides in `.env.staging.example`.

Configuration is loaded at runtime by
[`services/nova-core/app/config.py`](../services/nova-core/app/config.py) using Pydantic
Settings. All variables are read from a `.env` file in the working directory (not committed
to git) and mapped to a `Settings` class. Docker Compose services read their environment
from the same `.env` file via `env_file:`.

---

## Environment Variables

### Core Service

| Variable | Required | Default | Description |
|---|---|---|---|
| `NOVA_ENV` | No | `development` | Runtime environment: `development`, `staging`, or `production`. |
| `NOVA_LOG_LEVEL` | No | `INFO` | Python logging level for the core service. |
| `NOVA_TIMEZONE` | No | `Europe/Amsterdam` | IANA timezone for scheduling and timestamp rendering. |
| `NOVA_API_TOKEN` | No | `""` | Bearer token for API authentication. When empty, `/v1` endpoints are unprotected. <!-- VERIFY: actual API auth behavior when NOVA_API_TOKEN is empty --> |
| `NOVA_MAX_ITERATIONS` | No | `6` | Maximum agent loop iterations per chat request. |
| `NOVA_MAX_TURN_TIMEOUT` | No | `120` | Per-turn wall-clock timeout in seconds. |
| `NOVA_TRACING_ENABLED` | No | `true` | Emit structured traces to OpenObserve for latency and agent behavior analysis. |

### LLM (Ollama)

| Variable | Required | Default | Description |
|---|---|---|---|
| `OLLAMA_BASE_URL` | No | `http://ollama:11434` | Base URL for the Ollama API. Points to the `ollama` Docker Compose service by default. |
| `NOVA_MODEL` | No | `qwen3:14b` | Primary chat/agent model. |
| `NOVA_EMBED_MODEL` | No | `nomic-embed-text` | Embedding model for RAG and semantic memory. |
| `NOVA_VISION_MODEL` | No | `llava` | Model used for image understanding (e.g., photo analysis). |

### Database (Postgres + pgvector)

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_HOST` | No | `postgres` | Hostname of the Postgres instance. |
| `POSTGRES_PORT` | No | `5432` | Port of the Postgres instance. |
| `POSTGRES_DB` | No | `nova` | Database name. |
| `POSTGRES_USER` | No | `nova` | Database user. |
| `POSTGRES_PASSWORD` | **Yes** | `""` | Database password. Must be set; no default. |
| `OPENOBSERVE_HOST` | No | `openobserve.invalid` | Public hostname of the OpenObserve instance, used by Vector for log shipping. Not a Nova core setting — consumed by the `vector` Docker Compose service. |
| `OPENOBSERVE_LAN_IP` | No | `127.0.0.1` | LAN IP of the Coolify host running OpenObserve, for internal hairpin routing. Not a Nova core setting — consumed by the `vector` Docker Compose service. |

### Household Identity

| Variable | Required | Default | Description |
|---|---|---|---|
| `NOVA_WHATSAPP_USERS` | No | `""` | Comma-separated `number:name` pairs mapping WhatsApp senders to human names. Numbers in E.164 format without `+`. Example: `31600000001:Ruben,31600000002:Meral` |
| `NOVA_TELEGRAM_USERS` | No | `""` | Comma-separated `id:name` pairs mapping Telegram user IDs to human names. |

### WhatsApp (Meta Cloud API)

| Variable | Required | Default | Description |
|---|---|---|---|
| `WHATSAPP_VERIFY_TOKEN` | No | `""` | Verification token for the Meta webhook challenge. Set to an arbitrary secret string. |
| `WHATSAPP_ACCESS_TOKEN` | No | `""` | Meta Cloud API access token with `whatsapp_business_messaging` scope. |
| `WHATSAPP_PHONE_NUMBER_ID` | No | `""` | Meta phone number ID for the WhatsApp Business number. |
| `WHATSAPP_APP_SECRET` | No | `""` | Meta app secret for validating signed webhook payloads. |

### Telegram Bot

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | No | `""` | Bot token from @BotFather. |
| `TELEGRAM_WEBHOOK_SECRET` | No | `""` | Shared secret for Telegram webhook authentication. |
| `NOVA_TELEGRAM_ENABLED` | No | `false` | Boolean toggle: `true` to enable the Telegram integration. |

### Microsoft Graph (Outlook Mailbox)

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_TENANT_ID` | No | `""` | Azure AD tenant ID for the Microsoft Graph app registration. |
| `AZURE_CLIENT_ID` | No | `""` | Client (application) ID for the Microsoft Graph app registration. |
| `AZURE_CLIENT_SECRET` | No | `""` | Client secret for the Microsoft Graph app registration. |
| `AZURE_MAILBOX_EMAIL` | No | `""` | Email address of the shared Outlook mailbox Nova monitors. |

### CalDAV (Calendar)

| Variable | Required | Default | Description |
|---|---|---|---|
| `CALDAV_URL` | No | `http://radicale:5232/` | Base URL of the CalDAV server (Radicale by default). |


### Home Assistant

| Variable | Required | Default | Description |
|---|---|---|---|
| `NOVA_HA_URL` | No | `http://homeassistant:8123` | Base URL of the Home Assistant instance. |
| `NOVA_HA_TOKEN` | No | `""` | Long-lived access token for the Home Assistant REST API. Required for HA integration. |

### Voice

| Variable | Required | Default | Description |
|---|---|---|---|
| `NOVA_VOICE_ROOM_DEFAULTS` | No | `""` | Comma-separated `room_name:UserName` pairs for voice room defaults. |

### Observability (OpenObserve)

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENOBSERVE_URL` | No | `""` | OpenObserve API base URL. |
| `OPENOBSERVE_ORG` | No | `default` | OpenObserve organization name. |
| `OPENOBSERVE_USER` | No | `""` | OpenObserve user email. |
| `OPENOBSERVE_PASSWORD` | No | - | OpenObserve user password. |

### Incident Intake (Forgejo + Ops-Bridge)

| Variable | Required | Default | Description |
|---|---|---|---|
| `FORGEJO_URL` | No | `https://git.7rb.nl` | Base URL of the Forgejo instance. |
| `FORGEJO_REPO` | No | `ruben/nova` | Repository path for issue creation (owner/repo format). |
| `FORGEJO_TOKEN` | No | `""` | Forgejo personal access token with issue read/write on the repository. |
| `BRIDGE_TOKEN` | No | `""` | Shared secret for `ops-bridge` webhook authentication. Must match the token configured as `X-Bridge-Token` header in OpenObserve alerts. Set to an arbitrary secret string. |

### Scheduled Maintenance Agent

| Variable | Required | Default | Description |
|---|---|---|---|
| `MAINTENANCE_ENABLED` | No | `true` | Master toggle for the scheduled maintenance agent. |
| `MAINTENANCE_DEP_CHECK_ENABLED` | No | `true` | Run dependency freshness checks. |
| `MAINTENANCE_LOG_ANOMALY_ENABLED` | No | `true` | Run log anomaly detection. |
| `MAINTENANCE_BACKUP_VERIFY_ENABLED` | No | `true` | Verify backup file integrity. |
| `MAINTENANCE_TREND_REPORT_ENABLED` | No | `true` | Generate trend reports. |
| `BACKUP_DUMP_DIR` | No | `/backups/postgres` | Directory path for PostgreSQL dump files. |
| `BACKUP_DUMP_PATTERN` | No | `nova-*.sql` | Glob pattern matching backup dump files. |

---

## Ops Configuration (`ops/config.env`)

The ops loop (deploy, heal, promote) reads from `ops/config.env` (template at
`ops/config.env.example`). These variables control CI/CD behavior and are separate from the
runtime environment.

| Variable | Required | Default | Description |
|---|---|---|---|
| `COOLIFY_URL` | No | `http://coolify.local:8000` | Coolify instance API URL. |
| `COOLIFY_API_TOKEN` | No | - | Coolify API token (Coolify → Keys & Tokens). |
| `NOVA_SERVICES` | No | - | Comma-separated `name:uuid` pairs for deployable services (fallback when `STAGING_SERVICES` or `PROD_SERVICES` not set). |
| `STAGING_SERVICES` | No | - | Comma-separated `name:uuid` pairs for the staging stack. |
| `PROD_SERVICES` | No | - | Comma-separated `name:uuid` pairs for the production stack. |
| `NOVA_HEALTH_CHECKS` | No | - | Comma-separated `name:url` pairs verified after deploy. |
| `STAGING_HEALTH_URL` | No | `http://nova-staging.local:8081/health` | Health endpoint for staging verification during `promote.sh`. |
| `DEPLOY_TIMEOUT_SECONDS` | No | `600` | Max wait time for a Coolify deployment to complete. |
| `HEALTH_RETRIES` | No | `10` | Number of health-check poll attempts after deploy. |
| `HEALTH_INTERVAL_SECONDS` | No | `15` | Seconds between health-check polls. |
| `LOG_TAIL_LINES` | No | `200` | Container log lines captured into incidents. |
| `HEAL_ENABLED` | No | `true` | Enable self-healing via Claude Code. |
| `HEAL_MAX_ATTEMPTS` | No | `2` | Heal → redeploy cycles per pipeline run. |
| `HEAL_BRANCH_PREFIX` | No | `nova/heal` | Branch prefix for generated fix branches. |
| `HEAL_AUTO_PUSH` | No | `false` | Push fix branches to trigger automated redeploy. |
| `HEAL_PUSH_TO_MAIN` | No | `false` | Push fixes directly to main (requires `HEAL_AUTO_PUSH=true`). Fully autonomous loop. |
| `CLAUDE_MODEL` | No | `""` | Claude model override (empty = Claude Code default). |
| `CLAUDE_MAX_TURNS` | No | `40` | Maximum turns for Claude Code headless sessions. |

---

## Config File Format

Nova uses environment variables exclusively — there is no JSON, YAML, or TOML config file.
All configuration is loaded from the environment (via `.env` file in Docker or directly in
the OS environment). The Python `Settings` class in `services/nova-core/app/config.py` defines
the full schema with defaults.

### `.env` File (Runtime)

The primary runtime config file. Copy `.env.example` to `.env` and fill in secrets.
Referenced by:
- `docker-compose.yml` (all services via `env_file: .env`)
- `services/nova-core/app/config.py` (via `SettingsConfigDict(env_file=".env")`)

### `.env.staging` File (Model Benchmarking)

Used by the staging stack for model evaluation. Copy `.env.staging.example` to `.env.staging`.
Key differences from production:
- `NOVA_ENV=staging`
- `POSTGRES_DB=nova_staging` (separate database, same Postgres instance)
- `NOVA_TRACING_ENABLED=true`
- Services bind on port `8081` instead of `8080`

Referenced by `docker-compose.staging.yml` via `env_file: .env.staging`.

### `ops/config.env` File (CI/CD)

Used by ops scripts (`deploy.sh`, `promote.sh`, etc.). Copy `ops/config.env.example` to
`ops/config.env`. Contains Coolify API credentials, service UUIDs, and self-healing
configuration. Not used by the runtime services.

---

## Required vs Optional Settings

### Startup-Critical (Required)

These variables must be set for Nova to start successfully:

| Variable | Validation | Error if missing |
|---|---|---|
| `POSTGRES_PASSWORD` | Must be non-empty for database connectivity | Database connection failure at startup. Postgres service will use whatever is passed; the default `""` will cause connection errors from `nova-core`. |

All other variables have defaults. However, many **feature-gated** variables are effectively
required for their respective features to function:

| Feature | Required Variables |
|---|---|
| WhatsApp messaging | `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN` |
| Telegram bot | `TELEGRAM_BOT_TOKEN`, `NOVA_TELEGRAM_ENABLED=true` |
| Microsoft Graph email | `MSGRAPH_TENANT_ID`, `MSGRAPH_CLIENT_ID`, `MSGRAPH_CLIENT_SECRET`, `MSGRAPH_SHARED_MAILBOX` |
| CalDAV calendar | `CALDAV_USERNAME`, `CALDAV_PASSWORD` |
| Home Assistant | `NOVA_HA_TOKEN` (used in `services/nova-core/app/tools/home_assistant.py`; returns empty results without it) |
| Forgejo incident tracking | `FORGEJO_TOKEN` |
| Ops-bridge webhook | `BRIDGE_TOKEN` |
| Self-healing (ops) | `COOLIFY_API_TOKEN`, `COOLIFY_URL` |
| Observation/Observability | `OPENOBSERVE_PASSWORD` |

### Optional with Defaults

All non-Required variables have sensible defaults defined in
`services/nova-core/app/config.py`. See the [Environment Variables](#environment-variables)
table above for the default of each variable.

---

## Per-Environment Overrides

### Development

Copy `.env.example` to `.env`, set `NOVA_ENV=development`, and adjust values for local
development. No additional `.env.development` file is used.

Typical dev overrides:
- Point `POSTGRES_HOST` / `OLLAMA_BASE_URL` at locally running services
- Set all tokens to placeholder values (features gracefully degrade)
- Keep `NOVA_LOG_LEVEL=DEBUG` for verbose output

### Staging

Uses a separate `.env.staging` file. The staging stack runs alongside production on the
same VM, sharing the Postgres and Ollama instances but using a separate database
(`nova_staging`) and port (`8081`). The staging environment is intended for model
evaluation — different `NOVA_MODEL` values can be tested against the production baseline
without affecting production traffic.

Key staging behavior:
- `NOVA_ENV=staging`
- `POSTGRES_DB=nova_staging`
- Port binding `8081:8080`
- `NOVA_TRACING_ENABLED=true` (enables trace-based model comparison in OpenObserve)

<!-- VERIFY: actual staging deploy trigger — is it manual docker compose up or orchestrated by Coolify -->
<!-- VERIFY: actual model comparison process in OpenObserve — query and metric names -->

### Production

Uses `.env` with `NOVA_ENV` unset (defaults to `development`) — production deployment is
expected to explicitly set `NOVA_ENV` to `production` via the Coolify environment variable
overlay. Secrets (passwords, tokens) are injected by Coolify and never stored in the `.env`
file stored on disk in production.

<!-- VERIFY: exact Coolify env variable overlay mechanism for production secrets -->
