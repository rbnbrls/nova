"""Nightly backup verification stub.

Will be implemented in Plan 29-03: restores the latest Postgres dump into
a temporary scratch container and runs a SELECT query to verify integrity.
"""
from __future__ import annotations

import logging

log = logging.getLogger("nova-core")


async def run_backup_verification() -> None:
    """Verify the latest Postgres backup dump.

    Currently a stub — logs and returns.
    """
    log.info("[MAINT] backup verification not yet implemented")
