"""Multi-channel identity resolution via channel_identities table.

Skeleton only. Phase 15 replaces with real resolver that maps
(channel, channel_id) → household user name, replacing the
WhatsApp-only identity.py functions.
"""
from __future__ import annotations

# TODO(Phase 15): Implement resolve(channel, channel_id) -> str
# that queries the channel_identities table and returns the
# household user name. Update last_active_channel atomically
# on every inbound message. Remove dependency on app/identity.py.
