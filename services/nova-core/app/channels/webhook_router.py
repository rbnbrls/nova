"""Channel webhook registration and routing.

Skeleton only. Phase 20 replaces with real webhook router that
registers each channel adapter's webhook routes on the FastAPI app
via the ChannelAdapter.register_webhooks() interface.
"""
from __future__ import annotations

# TODO(Phase 20): Implement register_webhooks(app: FastAPI) that iterates
# over registered adapters and calls adapter.register_webhooks(app).
