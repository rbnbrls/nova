---
phase: quick-voice-input
plan: 01
subsystem: ui
tags: [web-speech-api, speech-recognition, dashboard, voice-input]

requires:
  - phase: 39-add-a-input-field-for-users-to-chat-with-nova-on-the-static-
    provides: dashboard chat panel with /dashboard/chat endpoint and handleChatSubmit()
provides:
  - Press-and-hold voice input mic button in the Ask Nova chat row
  - Browser-side speech-to-text transcription via Web Speech API
affects: []

tech-stack:
  added: []
  patterns: [press-and-hold-to-record, graceful-degradation-via-feature-detect]

key-files:
  created: []
  modified:
    - services/nova-core/static/index.html
    - services/nova-core/static/style.css
    - services/nova-core/static/app.js
    - services/nova-core/tests/test_dashboard.py

key-decisions:
  - "Web Speech API (SpeechRecognition) for browser-side transcription — nova-core has no Whisper/STT backend"
  - "Press-and-hold pattern (not toggle) per user's 'click and hold to send' wording"
  - "Transcript flows through existing /dashboard/chat endpoint — no backend changes"

patterns-established:
  - "Feature-detect + graceful degradation: mic button starts disabled, enabled only when SpeechRecognition exists"
  - "Single reusable recognition instance per session with try/catch around start()/stop()"

requirements-completed:
  - QUICK-VOICE-INPUT-01

coverage:
  - id: D1
    description: "Mic button with id chat-btn-mic in the Ask Nova chat input row"
    requirement: "QUICK-VOICE-INPUT-01"
    verification:
      - kind: unit
        ref: "services/nova-core/tests/test_dashboard.py#test_dashboard_html_has_mic_button"
        status: pass
    human_judgment: false
  - id: D2
    description: "Press-and-hold SpeechRecognition wiring with recording visual state and graceful degradation"
    requirement: "QUICK-VOICE-INPUT-01"
    verification:
      - kind: unit
        ref: "services/nova-core/tests/test_dashboard.py (9 passed)"
        status: pass
      - kind: other
        ref: "node --check services/nova-core/static/app.js"
        status: pass
    human_judgment: true
    rationale: "Browser speech recognition behavior (hold-to-record, transcript submission, recording visual) requires manual verification in a Chromium/Safari browser with microphone access"

duration: ~15min
completed: 2026-07-13
status: complete
---

# Quick Task 260713-otb: Voice Input Button Summary

**Press-and-hold mic button in the Ask Nova chat row using browser Web Speech API for speech-to-text, funneling transcripts through the existing /dashboard/chat endpoint**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added mic button (🎤) to the Ask Nova chat input row, placed before the text input
- Wired press-and-hold SpeechRecognition with mouse + touch + pointer event support for cross-device use
- Red pulsing recording visual state while the mic button is held
- Graceful degradation: mic button stays disabled on browsers without SpeechRecognition support; typing/Send unaffected
- Transcript submitted through existing handleChatSubmit() on release — no backend changes required

## Task Commits

Each task was committed atomically (TDD: test first, then implementation):

1. **Task 1: Add voice input button UI + mic button HTML test** - `9bee3ba` (test) + `43557ff` (feat)
2. **Task 2: Wire press-and-hold SpeechRecognition + CSS recording state** - `65091f3` (feat)

## Files Created/Modified
- `services/nova-core/static/index.html` - Added mic button element to chat-input-row
- `services/nova-core/static/app.js` - Voice input IIFE with SpeechRecognition lifecycle, press-and-hold handlers, recording state management
- `services/nova-core/static/style.css` - Mic button styling with hover, disabled, and recording (red pulsing) states
- `services/nova-core/tests/test_dashboard.py` - New test asserting mic button id is present in dashboard HTML

## Decisions Made
- Used Web Speech API (SpeechRecognition) for browser-side transcription — nova-core has no transcription backend (Whisper/STT absent), so MediaRecorder audio upload would require a new service and exceed quick-task scope
- Press-and-hold pattern (not toggle) matches the user's "click and hold to send" wording
- Single reusable recognition instance per session (Web Speech API only allows one active recognition at a time)
- voiceInFlight flag prevents starting recognition while a chat submission is already in flight
- recognition.onerror + onend defensively reset recording UI state

## Deviations from Plan

None - plan executed exactly as written

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. Voice input uses the browser's built-in Web Speech API (available in Chromium and Safari). No microphone permission configuration needed beyond the standard browser prompt.

## Next Phase Readiness
- Voice input is complete and functional on supporting browsers
- Manual verification recommended: open the LAN dashboard in Chromium/Safari, hold the mic button, speak, release — transcribed text should be sent and Nova should reply

---
*Quick Task: 260713-otb*
*Completed: 2026-07-13*
