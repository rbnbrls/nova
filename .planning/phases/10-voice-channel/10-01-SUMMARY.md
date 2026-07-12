# Phase 10 — Plan 01 Summary: Voice Channel Tests

## Shipped

Created `services/nova-core/tests/test_voice.py` with 8 tests covering the HA proxy endpoint contract and graceful error degradation for the voice channel.

### Files Created

- `services/nova-core/tests/test_voice.py` — 2 test classes, 8 tests total

### Test Coverage

**Class `TestHAProxyEndpoint`** (4 tests):
- `test_voice_query_basic` — voice query returns 200 with correct ChatCompletionResponse structure
- `test_voice_query_user_attribution` — `?user=Ruben` query param is honored by run_agent
- `test_voice_query_default_user_fallback` — no user param defaults to "household"
- `test_voice_query_conversation_history` — multi-turn history is passed correctly to run_agent

**Class `TestVoiceErrorHandling`** (4 tests):
- `test_voice_llm_unavailable_returns_friendly_fallback` — Exception from run_agent → 200 with audio-friendly message
- `test_voice_llm_timeout_returns_friendly_fallback` — TimeoutError → 200 with friendly fallback
- `test_voice_ha_downstream_unreachable` — httpx.HTTPStatusError → 200 with friendly fallback
- `test_voice_empty_message_handling` — empty message content → 200, run_agent called with ""

### Key Decisions

- **Test patterns match existing conventions**: uses `AsyncMock`, `patch`, `TestClient(app)` — same as test_agent.py
- **No implementation files modified**: per accept-as-is constraint — tests only
- **Friendly fallback message**: matches existing string from main.py — "Nova is having trouble right now, please try again later."

## Success Criteria

1. ✅ `test_voice.py` exists with 8 tests
2. ✅ HA proxy endpoint tests verify the Assist ↔ Nova contract
3. ✅ Error handling tests verify graceful degradation
4. ✅ No implementation code modified

## Self-Check: PASSED
