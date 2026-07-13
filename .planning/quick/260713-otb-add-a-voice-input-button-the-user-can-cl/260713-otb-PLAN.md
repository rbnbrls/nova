---
phase: quick-voice-input
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - services/nova-core/static/index.html
  - services/nova-core/static/style.css
  - services/nova-core/static/app.js
  - services/nova-core/tests/test_dashboard.py
autonomous: true
requirements:
  - QUICK-VOICE-INPUT-01
must_haves:
  truths:
    - A microphone button is visible next to the "Ask Nova" Send button on the dashboard
    - Pressing and holding the mic button starts browser-based speech recognition
    - Releasing the mic button stops recognition and submits the transcribed text to /dashboard/chat
    - A "recording" visual state is visible while the mic button is held
    - On unsupported browsers the mic button is hidden or disabled gracefully
    - Sending a transcribed voice message produces the same reply AI flow as typing the text
  artifacts:
    - services/nova-core/static/index.html chat-input row contains a mic button
    - Voice-input JS module in services/nova-core/static/app.js
    - Mic button CSS + recording state in services/nova-core/static/style.css
    - Dashboard test asserting the mic button id is present in the chat panel HTML
  key_links:
    - mic button mousedown → recognition.start() → mic button mouseup → recognition.stop() → handleChatSubmit()
    - recognition result → chat-input value → existing /dashboard/chat POST path
---

<objective>
Add a press-and-hold voice input button to the dashboard "Ask Nova" chat row. The button uses the browser's Web Speech API (SpeechRecognition) to transcribe speech to text while held, then submits the transcribed text through the existing `/dashboard/chat` endpoint on release.

Purpose: Let Ruben & Méral send voice messages to Nova from the LAN dashboard without typing on the household interface.
Output: Modified dashboard HTML/CSS/JS + one automated test.
</objective>

<execution_context>
@/Users/ruben/.config/opencode/gsd-core/workflows/execute-plan.md
@/Users/ruben/.config/opencode/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@services/nova-core/static/index.html
@services/nova-core/static/app.js
@services/nova-core/static/style.css

The dashboard "Ask Nova" chat panel was added in Phase 39 (see `.planning/phases/39-add-a-input-field-for-users-to-chat-with-nova-on-the-static-/39-01-SUMMARY.md`). The chat-input-row at `index.html:160-163` holds a text input and Send button. `handleChatSubmit()` in `app.js:754` posts `{user, message}` to `/dashboard/chat`. This plan reuses that exact endpoint — voice messages become transcribed text at the wire level, so NO backend changes are required. Browser dictation uses the OS/Web speech engine (Web Speech API), which is supported in Chromium and Safari — the dashboard is LAN-only on home devices, so this is acceptable. There is NO existing Whisper/transcription service in nova-core, so a MediaRecorder audio-upload approach would require a new transcription backend; the Web Speech API approach keeps this a focused quick task.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add voice input button UI + mic button HTML test</name>
  <files>services/nova-core/static/index.html, services/nova-core/tests/test_dashboard.py</files>
  <behavior>
    - Test: dashboard HTML contains the mic button with id chat-btn-mic inside the chat panel (mirrors the existing test_dashboard_html_has_chat_panel test pattern in test_dashboard.py).
  </behavior>
  <action>
Add a mic button to the chat-input-row in services/nova-core/static/index.html (around line 160-163), placed BEFORE the text input. Element: `<button class="btn btn-mic" id="chat-btn-mic" type="button" title="Hold to speak" aria-label="Hold to speak to Nova" disabled>🎤</button>`. The initial `disabled` attribute is removed at runtime by JS only when the Web Speech API is supported; this preserves graceful degradation.

In services/nova-core/tests/test_dashboard.py add a new test near the existing test_dashboard_html_has_chat_panel test. Pattern: load index.html text (the existing tests already read the file via a helper or Path), assert `"id=\"chat-btn-mic\"" in html` AND `"chat-panel"` is still present. Reuse whatever file-read helper the existing dashboard HTML test uses — do not introduce a new file-loading mechanism.

Do NOT add backend code — voice messages flow through the existing /dashboard/chat POST endpoint. Do NOT use MediaRecorder or audio file upload; the Web Speech API (SpeechRecognition) performs transcription in the browser.

Reference decision: voice-input uses browser-side transcription via the Web Speech API per project quick-task scope (no nova-core transcription backend exists).
  </action>
  <verify>
    <automated>cd services/nova-core && python -m pytest tests/test_dashboard.py -k "mic" -x</automated>
  </verify>
  <done>The dashboard chat input row contains a mic button with id chat-btn-mic, and a unit test asserts its presence in the rendered HTML.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire press-and-hold SpeechRecognition + CSS recording state</name>
  <files>services/nova-core/static/app.js, services/nova-core/static/style.css</files>
  <behavior>
    - Holding (mousedown + touchstart) the mic button starts recognition; on release (mouseup/leave/touchend) it stops recognition.
    - When recognition yields a final transcript, the transcript is placed into #chat-input and handleChatSubmit() is invoked.
    - While held, mic button gains CSS class `recording` (and a visible recording indicator); on release the class is removed even if recognition errors out.
    - On browsers without SpeechRecognition support, the mic button remains disabled and typing/Send still functions normally.
  </behavior>
  <action>
In services/nova-core/static/app.js, after the existing Phase 39 chat block (around line 847, before the Settings Modal section), add a voice-input block under a `// --- Voice Input (quick task) ---` comment. Implement:

1. Feature-detect: `const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;` If absent, leave the mic button disabled and return early — typing/Send path is unaffected.
2. Enable the mic button (`btnMic.disabled = false`) only when SpeechRecognition exists.
3. Create one reusable `recognition` instance per session (do NOT recreate on every press — Web Speech API only allows one active recognition at a time): `continuous=false`, `interimResults=false`, `lang='en-US'`. Conflicting browser locale is acceptable for v1 since the dashboard targets Ruben & Méral who speak English; do NOT add a language picker — that is out of scope.
4. Hold-to-record handlers — attach BOTH pointer events and touch fallback for cross-device support on the household dashboard (the dashboard may be opened on a phone or tablet):
   - On `mousedown`/`touchstart`/`pointerdown` on the mic button: prevent default, add `recording` CSS class to the button, set `chatInput.disabled = true`, set `chatBtnSend.disabled = true`, and call `recognition.start()` inside a try/catch (recognition may throw if started twice in quick succession — swallow and log via console.warn only).
   - On `mouseup`/`mouseleave`/`touchend`/`pointerup`/`pointercancel`: remove `recording` class, re-enable chatInput and chatBtnSend (unless `chatInFlight` is true — respect the existing concurrent-send guard), and call `recognition.stop()` inside try/catch.
   - Use a module-scoped `voiceInFlight` flag to avoid starting recognition while a chat submission is already in flight.
5. recognition.onresult: take `event.results[event.results.length-1][0].transcript`, trim, place into `chatInput.value`. Do NOT auto-submit on result — wait for the user to release the button. Submit is invoked from the release handler after a non-empty transcript is captured.
   - In the release handler: if `chatInput.value` is non-empty after recognition, call `handleChatSubmit()`. If empty, simply re-enable inputs and clear the recording state.
6. recognition.onerror: log to console.warn, clear the recording class, re-enable inputs (respecting chatInFlight), show `showChatError('Voice input failed. Try again or type your message.')`.
7. recognition.onend: ensure the recording class is cleared and inputs re-enabled (defensive cleanup in case onerror/onresult did not fire).

In services/nova-core/static/style.css, append a chat mic block under the existing chat styles (after the chat-error rules around line 944). Styles:
   - `.chat-input-row .btn-mic` — square aspect (`width: 2.6rem; height: 2.6rem; padding: 0; font-size: 1.1rem; display: inline-flex; align-items: center; justify-content: center;`), background `rgba(255,255,255,0.05)`, border `1px solid rgba(255,255,255,0.1)`, color `var(--text-primary)`, cursor pointer, transition `background-color 0.15s, transform 0.1s`.
   - `.chat-input-row .btn-mic:hover:not(:disabled)` — `background: rgba(139, 92, 246, 0.15); border-color: var(--border-hover);`
   - `.chat-input-row .btn-mic:disabled` — `opacity: 0.4; cursor: not-allowed;`
   - `.chat-input-row .btn-mic.recording` — `background: var(--warning-color); border-color: var(--warning-color); color: #fff; animation: pulse 1s ease-in-out infinite;` (red pulsing dot visual so it is obvious the mic is live).
   - `.chat-input-row` should keep its existing `gap: 0.75rem` so the mic + input + send layout stays balanced.

Keep all changes additive — do NOT modify existing chat handlers, escapeHtml, user-tab logic, or settings modal code. Voice input only adds a new input modality that funnels into the existing send path.

Reference decision: press-and-hold pattern (not toggle) per the user's quick-task description "click and hold to send voice messages". Web Speech API chosen because nova-core has no transcription backend (Whisper/others) and the dashboard is LAN-only on home browsers that ship SpeechRecognition.
  </action>
  <verify>
    <automated>cd services/nova-core && python -m pytest tests/test_dashboard.py -x && node --check static/app.js</automated>
  </verify>
  <done>Pressing and holding the mic button starts browser speech recognition with a red pulsing recording state; releasing it submits the transcribed text to /dashboard/chat through handleChatSubmit. On unsupported browsers the mic button stays disabled and typing/Send still works. All existing dashboard tests still pass and app.js parses without syntax errors.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser → nova-core /dashboard/chat | Transcribed text crosses from untrusted browser input into the existing chat endpoint (already XSS-escaped by Phase 39 escapeHtml() at app.js:794-812) |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-quick-voice-01 | Spoofing | SpeechRecognition transcript source | low | accept | Browser/OS provides transcription; no credential boundary crossed. Transcript is treated as user input on the same trust level as typed text. |
| T-quick-voice-02 | Tampering | Mic button state / recording flag | low | accept | Pure client-side UI state; no server-authoritative meaning. |
| T-quick-voice-03 | Information Disclosure | Microphone transcription | medium | mitigate | Transcription happens entirely in-browser via Web Speech API; no audio leaves the device. Voice transcript flows only to the local /dashboard/chat on the LAN nova-core instance. |
| T-quick-voice-04 | Repudiation | Voice messages vs typed messages | low | accept | Both modalities land in the same chat channel with channel='dashboard'; no separate audit needed at quick-task scope. |
| T-quick-voice-05 | Denial of Service | Rapid mic button mashing starting/stopping recognition | medium | mitigate | Single reusable recognition instance with try/catch around start()/stop(); voiceInFlight guard prevents starting recognition while a chat submission is in flight; recognition.onerror + onend defensively reset the recording UI state. |
</threat_model>

<verification>
- All Phase 39 dashboard tests still pass: `cd services/nova-core && python -m pytest tests/test_dashboard.py -x`
- New mic test passes: `-k "mic"` filter
- `node --check services/nova-core/static/app.js` reports no syntax errors
- Manual (not automated here): on a Chromium/Safari browser, open the LAN dashboard, hold the mic button → recording state appears → speak → release → transcribed text is sent and Nova replies
</verification>

<success_criteria>
- Mic button visible in the "Ask Nova" chat row on supporting browsers
- Press-and-hold starts browser speech recognition with a red pulsing recording visual
- On release, transcribed text is submitted through /dashboard/chat and Nova's reply renders in the chat reply area
- On browsers without SpeechRecognition, the mic button is disabled and the existing typing + Send flow is unaffected
- All existing dashboard tests pass and one new mic-button HTML assertion passes
</success_criteria>

<output>
Create `.planning/quick/260713-otb-add-a-voice-input-button-the-user-can-cl/260713-otb-SUMMARY.md` when done
</output>