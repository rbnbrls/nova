"""Nightly log-anomaly review stub.

Will be implemented in Plan 29-02: queries OpenObserve for error spikes
and unusual patterns, filing structured issues with redacted log excerpts.
"""
from __future__ import annotations

import logging

log = logging.getLogger("nova-core")


async def run_log_anomaly_review() -> None:
    """Review log patterns for anomalies via OpenObserve.

    Currently a stub — logs and returns.
    """
    log.info("[MAINT] log-anomaly review not yet implemented")
