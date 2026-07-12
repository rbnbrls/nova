# Phase 20 Context: Telegram Bot Foundation

## Source
ROADMAP.md SCs are detailed and self-explanatory.

## Decisions
- Follow WhatsApp channel patterns closely (webhook → verify → dedup → agent loop → reply)
- New channels/telegram.py as TelegramAdapter (implements ChannelAdapter from Phase 19)
- Webhook path: POST /webhooks/telegram
- Feature flag: settings.nova_telegram_enabled (default False)
- Dedup via existing processed_telegram_updates table
- HTML parse mode for outbound, chunk at paragraph boundaries if >4096 chars
- Commands: /help, /tasks, /settings
