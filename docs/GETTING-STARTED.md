<!-- generated-by: gsd-doc-writer -->

# Getting Started with Nova

This guide walks you through setting up Nova — a private, self-hosted AI household assistant — on a Linux server (CPU-only; no GPU required).

## Prerequisites

- **Hardware:** Any Linux server (Nova runs CPU-only — the reference Proxmox VM has no NVIDIA GPU). ~16 GB RAM recommended so Ollama can hold the `qwen3:14b` model.
- **Operating system:** Linux with Docker Engine and the Compose plugin installed.
- **Docker & Docker Compose:** Docker Engine with the Compose plugin. Nova is deployed as a multi-container Docker stack.
- **Git:** To clone the repository.
- **Python >= 3.12:** For local development outside of Docker. The Docker containers include Python automatically.
- **~20 GB disk space:** For the Ollama models, Postgres data, and container images.

## Installation Steps

1. **Clone the repository**
   ```bash
   git clone https://git.7rb.nl/ruben/nova.git
   cd nova
   ```

2. **Create the environment file**
   ```bash
   cp .env.example .env
   ```
   Open `.env` in your editor and fill in the required values. At minimum:
   - Set `POSTGRES_PASSWORD` to a secure password (required — the stack won't start without it).

   All other features (WhatsApp, Telegram, calendar, email) are optional and will gracefully skip until their credentials are configured. See [CONFIGURATION.md](./CONFIGURATION.md) for the full list of environment variables.

3. **Install dependencies (Docker-only, no local tools needed)**
   Nova runs entirely in Docker — no local Python, Node.js, or other runtimes are needed. The `docker compose up` command in step 4 will pull and build everything automatically.

   If you plan to run the Python services locally (without Docker), install from the per-service requirements files:
   ```bash
   pip install -r services/nova-core/requirements.txt
   ```

## First Run

1. **Start the stack**
   ```bash
   docker compose up -d
   ```
   This starts all services: Nova Core (FastAPI, port 8080), Postgres/pgvector, Ollama, Whisper (STT), Piper (TTS), Radicale (CalDAV), Vector (log shipping), ops-bridge, and Caddy (reverse proxy).

2. **Pull the language model into Ollama (first time only)**
   ```bash
   docker compose exec ollama ollama pull qwen3:14b
   ```
   This can take several minutes depending on your internet connection. The model is ~9 GB. You can also pull additional models (e.g., `nomic-embed-text` for embeddings, `llava` for vision).

3. **Verify everything is running**
   ```bash
   # Check health endpoint
   curl -s localhost:8080/health

   # Send a test request to the chat API
   curl -s localhost:8080/v1/chat/completions \
     -H 'content-type: application/json' \
     -d '{"user":"Ruben","messages":[{"role":"user","content":"Hello Nova!"}]}'
   ```
   You should see a `{"status":"ok"}` response from `/health` and a chat completion from the API.

4. **Open the dashboard**
   Visit `http://localhost:8080/dashboard` in your browser for a live view of household tasks, calendar events, and the audit log.

## Common Setup Issues

### "GPU not detected" / very slow responses
Nova runs Ollama on the **CPU** (the Proxmox host has no GPU). First-token latency will be
higher than a GPU setup — that is expected. Verify the model is loaded and serving:
```bash
docker compose exec ollama ollama ps
docker compose exec ollama ollama list
```
Do NOT add `deploy.resources.reservations.devices` GPU blocks to `docker-compose.yml`: with no
NVIDIA driver on the host, ollama/whisper then fail to start (stuck in "Created", Pid=0).

### Model not pulled / service times out
If Nova Core responds with an error about the model not being found, you need to pull the model into Ollama first:
```bash
docker compose exec ollama ollama pull qwen3:14b
```
You can check which models are available in the Ollama container:
```bash
docker compose exec ollama ollama list
```

### Port 8080 already in use
Nova Core binds to port 8080 by default. If another service is using it, either stop the conflicting service or override the port in your `.env` file and adjust the `ports` mapping in `docker-compose.yml`.

### Missing `.env` file
If Docker Compose fails with variable substitution errors, you forgot to create the `.env` file. Run:
```bash
cp .env.example .env
```
Then set `POSTGRES_PASSWORD` to a non-empty value.

### Database migration errors
Alembic migrations run automatically inside the Nova Core container on startup. If migrations fail (e.g., due to a partially initialized database), reset the Postgres data volume:
```bash
docker compose down -v postgres
docker compose up -d
```

## Next Steps

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — Understand Nova's channel-agnostic agent loop, component diagram, and data flow.
- **[CONFIGURATION.md](./CONFIGURATION.md)** — Configure WhatsApp, Telegram, calendar (CalDAV), email (Microsoft Graph), voice, and operational tooling.
- **[README.md](../README.md)** — Project overview, build phases, and repository layout.
- **[docs/roadmap.md](./roadmap.md)** — Full build roadmap with extension tracks.
