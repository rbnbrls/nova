"""WhatsApp adapter — backward-compat re-export.

This module now re-exports from channels/whatsapp for backward compatibility.
New code should import from channels.whatsapp directly.
"""
from __future__ import annotations

# Preserved direct imports — these keep app.whatsapp.run_agent,
# app.whatsapp.get_pool, and app.whatsapp.user_from_whatsapp available
# for existing test patches (test_scheduler, test_webhooks, test_dnd).
from .agent import run_agent
from .db import get_pool
from .identity import user_from_whatsapp

# Re-export the two public API functions from the new module.
from .channels.whatsapp import send_whatsapp_message, process_incoming_whatsapp
