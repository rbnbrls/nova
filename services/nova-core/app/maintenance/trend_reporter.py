"""Weekly disk/VRAM trend report stub.

Will be implemented in Plan 29-03: collects disk usage and GPU/VRAM metrics,
compares against prior readings, and files a periodic trend report issue.
"""
from __future__ import annotations

import logging

log = logging.getLogger("nova-core")


async def run_trend_report() -> None:
    """Generate and file a disk/VRAM trend report.

    Currently a stub — logs and returns.
    """
    log.info("[MAINT] trend report not yet implemented")
