# Phase 37 Context: Paper & Photo Intake

## Source
ROADMAP.md Phase 37 goal + success criteria.

## Decisions

### Vision Model
- Use existing Ollama with a vision-capable model (e.g., llava)
- No separate OCR pipeline — vision model handles both text extraction and scene understanding
- All processing stays on local GPU — no cloud API calls

### Processing Flow
1. User sends WhatsApp photo to Nova
2. Nova downloads the image from Meta servers
3. Image sent to vision model for analysis
4. Model extracts: dates, tasks, events, content summary
5. Proposed actions presented to user for confirmation (extends Phase 8 confirmation pattern)
6. User confirms → task/event created via existing tools

### WhatsApp Inbound
- Reuse existing WhatsApp webhook handler for image messages
- Image format: WhatsApp sends media ID, Nova fetches via Meta API
- Supported formats: JPEG, PNG (what WhatsApp sends)

### Confirmation
- Extend Phase 8 confirmation gate: new tool `process_photo` triggers confirmation
- Proposed action shown as structured preview: "[Calendar Event] School Meeting on Sep 5 at 10am" / "[Task] Submit permission slip by Aug 20"
- User confirms or rejects the extracted actions

## Deferred Ideas
- Warranty receipt filing (SC #2) — deferred to future iteration; Phase 37 focuses on letter/document intake with event+task extraction
