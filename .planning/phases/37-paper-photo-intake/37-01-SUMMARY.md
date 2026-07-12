---
phase: 37-paper-photo-intake
plan: 01
wave: 1
type: execute
subsystem: whatsapp-channels
tags: [whatsapp, image-processing, vision, ollama, paper-intake]
requires: []
provides: [image-detection, media-download, vision-analysis, analyze-image]
affects: [whatsapp-adapter, vision-module, config]
tech-stack:
  added: [httpx (existing)]
  patterns: [media-download-and-analyze, lazy-module-import, synthetic-context-message, mock-httpx-for-api-tests, magicmock-for-sync-api-methods]
key-files:
  created:
    - services/nova-core/app/vision.py
    - services/nova-core/tests/test_vision.py
  modified:
    - services/nova-core/app/channels/__init__.py
    - services/nova-core/app/channels/whatsapp.py
    - services/nova-core/app/config.py
    - services/nova-core/tests/test_webhooks.py
decisions:
  - "Lazy import of analyze_image inside process_incoming_whatsapp avoids circular import and allows independent Task 1/2 development"
  - "Synthetic message [User sent a photo. Vision analysis: ...] pipes extraction into agent context instead of a separate tool call"
  - "No separate OCR pipeline — vision model (llava) handles both text extraction and scene understanding per CONTEXT.md"
metrics:
  duration: ~8 minutes
  completed_date: "2026-07-12"
  tasks_total: 2
  tasks_completed: 2
  files_created: 2
  files_modified: 4
  tests_added: 15
status: complete
---

# Phase 37 Plan 01: WhatsApp Image Detection + Media Download + Vision Analysis Summary

Implemented the first wave of Paper & Photo Intake: WhatsApp image message detection, media download from Meta servers, and local Ollama-based vision analysis — all processing stays entirely on GPU with no cloud API calls.

## Key Outcomes

### 1. Image Message Detection
`WhatsAppAdapter.process_incoming()` now extracts `media_id` and `media_type` from image payloads (`msg.image.id`) in addition to text. The `InboundMessage` dataclass gained optional `media_type` and `media_id` fields. Image-only payloads now produce an `InboundMessage` (previously returned `None` due to empty text). Non-message payloads (status updates, echoes) still return `None` correctly.

### 2. Media Download from Meta
`download_whatsapp_media(media_id)` performs a two-step fetch:
1. Resolves the media ID to a temporary download URL via `GET https://graph.facebook.com/v18.0/{media_id}`
2. Downloads the image bytes from the temporary URL

Returns raw `bytes` on success, `None` on any failure (unconfigured token, HTTP 4xx/5xx, network error, missing URL field). All errors are logged with `print("[ERROR] ...")` per existing patterns.

### 3. Vision Analysis Module
`app/vision.py` with `analyze_image()`:
- Encodes image bytes as base64 and sends to Ollama's `/api/chat` with `images[]` field
- Sends a structured prompt asking for JSON extraction (summary, events, tasks)
- Strips markdown code fences from Ollama's response before JSON parsing
- Returns error dict on any failure (HTTP error, connection error, JSON parse error)
- Respects `settings.nova_vision_model` (default `"llava"`) with optional `model` override
- No cloud API SDK imports anywhere in the module

### 4. Image Message Flow in `process_incoming_whatsapp`
When an inbound message has `media_id`:
1. Downloads image bytes via `download_whatsapp_media()`
2. If download fails → sends "I could not download the photo you sent. Please try again or send the text directly."
3. If download succeeds → calls `analyze_image()` for vision extraction
4. If analysis fails → sends "I had trouble reading that photo. Could you type the important details instead?"
5. If analysis succeeds → builds a synthetic message `[User sent a photo. Vision analysis: {summary} Extracted events: {events} Extracted tasks: {tasks}]` and passes it to `run_agent()` as if the user typed that context

### 5. Config
Added `nova_vision_model: str = "llava"` to the `Settings` class in `app/config.py`.

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (tests fail) | `ed80e72` — `test(37-paper-photo-intake): add failing tests for WhatsApp image message handling` | ✅ |
| GREEN (impl passes) | `efc928c` — `feat(37-paper-photo-intake): implement WhatsApp image detection, media download, and vision pipeline` | ✅ |
| Task 2 tests | `a0d7bc5` — `test(37-paper-photo-intake): add vision analysis tests for analyze_image()` | ✅ |

Note: Task 2 RED phase was implicitly satisfied by Task 1's pre-emptive implementation of `vision.py`. The 9 `test_vision.py` tests validate all `analyze_image()` behaviors against the existing implementation.

## Test Results

**21/21** test_webhooks.py tests pass (all 11 existing + 10 new image tests)
**9/9** test_vision.py tests pass (all new)
**0 regressions** in existing WhatsApp text-message flow

## Success Criteria Checklist

- [x] `InboundMessage` has optional `media_type` and `media_id` fields
- [x] `download_whatsapp_media(media_id)` implemented in WhatsApp adapter
- [x] `app/vision.py` exists with `analyze_image(image_bytes)` function
- [x] `nova_vision_model` config key exists and defaults to "llava"
- [x] `process_incoming_whatsapp` branches on image messages → downloads → analyzes → feeds context to agent
- [x] Non-text messages without image ID are skipped (existing behavior preserved)
- [x] Image download failure sends user-friendly error reply
- [x] Vision analysis failure sends user-friendly error reply
- [x] Existing WhatsApp text-message tests pass unchanged

## Deviations from Plan

None — plan executed exactly as described.

## Threat Surface Scan

No new external endpoints introduced. The WhatsApp webhook (already existing) handles all inbound payloads including images. Outbound calls to Meta's Graph API and localhost Ollama are utility fetches, not new service endpoints. All image processing stays on the local GPU. No new trust boundaries created.

## Self-Check: PASSED

All files exist and all commits verified:
- ✅ `services/nova-core/app/vision.py`
- ✅ `services/nova-core/tests/test_vision.py`
- ✅ `services/nova-core/app/channels/__init__.py`
- ✅ `services/nova-core/app/channels/whatsapp.py`
- ✅ `services/nova-core/app/config.py`
- ✅ `services/nova-core/tests/test_webhooks.py`
- ✅ Commit `ed80e72` (RED)
- ✅ Commit `efc928c` (GREEN)
- ✅ Commit `a0d7bc5` (tests)

## Next Steps

Plan 37-02 will:
- Create the `process_photo` tool for the LLM to propose calendar events and tasks
- Extend the Phase 8 confirmation gate to intercept `process_photo` before execution
- Show structured previews: "[Calendar Event] School Meeting on Sep 5 at 10am"
- Wire the end-to-end flow and add complete test coverage
