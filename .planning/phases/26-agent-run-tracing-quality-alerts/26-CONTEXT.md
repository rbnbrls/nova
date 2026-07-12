# Phase 26 Context: Agent-Run Tracing & Quality Alerts

## Source
ROADMAP.md Phase 26 goal + success criteria.

## Decisions
- Structured trace: JSON payload with channel, user, latency_ms, token_count, tool_calls, errors, iteration_count
- Ship to OpenObserve via HTTP API (existing ops-bridge pattern)
- Tag "got stuck" exits (max iterations exceeded) as alert-worthy
- Quality alerts flow through ops-bridge → Forgejo issue (same as crash alert path from Phase 9)
- OpenObserve dashboard for p95 latency and tool-error rate
- Configurable via settings with a toggle to disable tracing
