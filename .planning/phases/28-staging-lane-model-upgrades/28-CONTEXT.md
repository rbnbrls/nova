# Phase 28 Context: Staging Lane & Model Upgrades

## Source
ROADMAP.md SCs are self-explanatory.

## Decisions
- Second compose profile: `docker-compose.staging.yml` with `nova-staging` service
- Separate DB schema (different Postgres database or schema)
- Same GPU shared between staging and production models
- Coolify deploys to staging first; manual promotion to prod
- Promotion gate: tests green + evals above threshold (Phase 7 eval suite)
- Use Phase 26 tracing for before/after model benchmarks
