# Phase 19 Context: Channel Adapter Pattern & Multi-Channel Schema

## Source
ROADMAP.md SCs are detailed and self-explanatory.

## Decisions
- All 6 SCs are well-defined. Most schema elements may already exist from prior phases — verify and ensure compliance.
- WhatsApp adapter already follows ChannelAdapter-like patterns; formalize the ABC.
- `channels/` package: move WhatsApp into it, create dispatcher.py and webhook_router.py skeletons.
