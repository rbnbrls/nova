"""Nightly dependency and CVE scanner stub.

Will be implemented in Plan 29-02: checks pyproject.toml / requirements
files for outdated deps and runs pip-audit for CVE scanning.
"""
from __future__ import annotations

import logging

log = logging.getLogger("nova-core")


async def run_dependency_scan() -> None:
    """Check for outdated dependencies and CVEs.

    Currently a stub — logs and returns.
    """
    log.info("[MAINT] dependency scan not yet implemented")
