# Phase 27 Context: User-Feedback → Incident Loop

## Source
ROADMAP.md SCs are self-explanatory.

## Decisions
- Feedback detection: match "that was wrong" / "that's incorrect" patterns + WhatsApp 👎 reaction
- Use Phase 26 tracer data for context (last N turns, tool calls, model response)
- File via ForgejoClient from Phase 29
- Tag issues as `type: feedback`
