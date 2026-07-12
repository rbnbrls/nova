# Phase 21 Context: Multi-Channel Identity & Last-Active Tracking

## Source
ROADMAP.md SCs are self-explanatory.

## Decisions
- Both WhatsApp and Telegram inbound handlers already update last_active_channel — verify and ensure atomicity
- channels/identity.py should provide a unified identity resolver using channel_identities table
- Follow existing patterns from identity.py
