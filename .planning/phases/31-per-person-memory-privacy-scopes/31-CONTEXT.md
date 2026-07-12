# Phase 31 Context: Per-Person Memory & Privacy Scopes

## Source
ROADMAP.md Phase 31 goal + success criteria.

## Decisions
- `remember` tool: add `scope` parameter (`private` / `household`), default `private`
- `forget` tool: filter by scope, only forget what requester owns
- Memory retrieval: return requester's memories + household-scope memories
- Private memories never appear in other user's answers or briefing
- Dashboard memory browser: view/edit/delete memories
- Existing memory schema already has user_id FK — scope can be a new column or inferred from existing patterns
- Follow Phase 30 speaker identity for voice attribution
