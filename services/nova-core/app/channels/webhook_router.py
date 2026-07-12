"""Channel webhook registration and routing.

Skeleton only. Phase 14 replaces with real webhook router that
registers Telegram and WhatsApp webhook handlers on the FastAPI app.
"""
from __future__ import annotations

# TODO(Phase 14): Implement register_webhooks(app: FastAPI) that
# attaches channel-specific webhook routes under /webhooks/*.
# Each route verifies the channel auth, then delegates to the
# corresponding ChannelAdapter.process_incoming().
