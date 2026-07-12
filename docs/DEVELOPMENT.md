<!-- generated-by: gsd-doc-writer -->

# Development

## Local setup

1. **Fork and clone** the repository:
   ```bash
   git clone https://github.com/ruben/nova.git  <!-- VERIFY: repo URL is https://github.com/ruben/nova -->
   cd nova
   ```

2. **Install Python 3.12+**. The services target Python 3.12 (see Dockerfiles and `pyproject.toml`). The test script also supports Python 3.13 if available.

3. **Create a virtual environment** for development:
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

4. **Install dependencies** for both services:
   ```bash
   pip install -r services/nova-core/requirements.txt
   pip install -r services/ops-bridge/requirements.txt
   ```

5. **Copy environment files** and fill in the blanks:
   ```bash
   cp .env.example .env
   cp ops/config.env.example ops/config.env
   ```
   Edit `.env` and `ops/config.env` with your local values. At minimum, set `POSTGRES_PASSWORD` in `.env` and `COOLIFY_API_TOKEN` + service UUIDs in `ops/config.env`. For a full list of variables, see [CONFIGURATION.md](CONFIGURATION.md).

6. **Set up the database** (Postgres with pgvector):
   ```bash
   docker compose up -d postgres
   ```
   Nova Core runs Alembic migrations automatically on startup. To run them manually:
   ```bash
   cd services/nova-core
   DATABASE_URL=postgresql://nova:change-me@localhost:5432/nova alembic upgrade head
   ```

7. **Run Nova Core** for the first time:
   ```bash
   cd services/nova-core
   PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
   ```
   Open `http://localhost:8080/health` — you should see `{"status": "ok", "ollama_ready": false}` if Ollama is not running locally.

8. **Set up pre-commit hooks** (recommended):
   ```bash
   pip install pre-commit
   pre-commit install
   ```

If you prefer Docker for the full stack (Nova Core, Postgres, Ollama, Caddy, etc.):
```bash
docker compose up -d
```

## Build commands

Nova has no `package.json` or formal build scripts — the project is Python-based and relies on the `ops/` scripts and direct commands.

| Command | Description |
|---|---|
| `python -m pytest services/nova-core/tests` | Run nova-core test suite |
| `python -m pytest services/ops-bridge/tests` | Run ops-bridge test suite |
| `ruff check services/` | Lint all Python code |
| `ruff format services/` | Auto-format all Python code |
| `mypy services/nova-core/app/ services/ops-bridge/app.py` | Run type checking |
| `ops/run-tests.sh` | Full CI suite — creates test venv, runs tests, lint, and type checks |
| `ops/deploy.sh` | Deploy to staging (or `--prod` for production, `--all` for both) |
| `ops/pipeline.sh` | Closed loop: deploy → observe → triage/heal → redeploy |
| `ops/promote.sh` | Promote staging to production (health check + test gate + deploy) |
| `ops/observe.sh` | Poll health endpoints, file Forgejo issues on failure |
| `ops/heal.sh <incident-file>` | Feed incident report to Claude Code for automated diagnosis/fix |
| `ops/triage.sh` | Consume open auto-heal issues and attempt fixes |
| `docker compose up -d` | Start full stack locally via Docker |
| `docker compose build` | Rebuild service Docker images |

**Developer loop**: The fastest inner loop for nova-core changes is running the service directly with uvicorn's `--reload` flag (no Docker rebuild needed):
```bash
cd services/nova-core && PYTHONPATH=. uvicorn app.main:app --reload
```

The static dashboard frontend lives in `services/nova-core/static/` — changes to HTML, CSS, or JS files take effect immediately on page reload.

## Code style

- **Formatting**: [Ruff](https://docs.astral.sh/ruff/) (configured in `pyproject.toml`) — double quotes, 100-char line length, Python 3.12 target. Run with `ruff format services/`.
- **Linting**: Ruff with rules `F`, `E`, `W` (pyflakes + pycodestyle). Run with `ruff check services/`.
- **Type checking**: [mypy](https://mypy-lang.org/) (configured in `pyproject.toml` and `.pre-commit-config.yaml`) with `strict_optional`, `disallow_untyped_defs = false`, `ignore_missing_imports = true`. Run with `mypy services/nova-core/app/ services/ops-bridge/app.py`.
- **Pre-commit hooks** (`.pre-commit-config.yaml`): trailing whitespace removal, end-of-file newlines, YAML validation, large file check, Ruff fix + format, and mypy. These run automatically on `git commit` if installed.
- **Shell scripts**: Ops scripts under `ops/` use `#!/usr/bin/env bash` with `set -euo pipefail`. Follow the conventions in `ops/lib.sh` for logging (`log`, `die`, `require`) and Coolify API calls (`coolify_api`, `for_each_pair`).

## Branch conventions

No formal branch naming convention is documented. Common patterns observed in the codebase:

- `nova/heal-<timestamp>` — automated fix branches from the self-healing pipeline (see `ops/heal.sh`)
- Commit messages use [Conventional Commits](https://www.conventionalcommits.org/) style: `feat(...)`, `fix(...)`, `chore(...)`, `docs(...)`

The default branch is `main` (or `master`<!-- VERIFY: default branch name is `main` -->).

## PR process

No CI/CD pipeline or pull request template is checked into the repository. The project is self-hosted and deploys via Coolify, not GitHub Actions. When contributing:

1. **Create a feature branch** from the default branch.
2. **Run the full test suite** before opening a PR: `ops/run-tests.sh`.
3. **Self-review** your changes — check for secrets in `.env` files (they should stay in `.env.example` only), confirm no new dependencies were added without updating `requirements.txt`, and verify that `ruff check` and `mypy` pass.
4. **Write a descriptive commit message** following the Conventional Commits format (e.g., `feat(agent): add grocery list parsing`).
5. **Open a pull request** against the default branch. Include a summary of what changed, why, and whether any configuration or environment variable changes are needed.

For production deployment, use the `ops/promote.sh` script which gates on staging health + test suite pass before deploying to production.
