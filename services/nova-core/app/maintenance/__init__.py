"""Scheduled maintenance job modules.

This subpackage contains stub modules for four maintenance jobs that will
be implemented in Plans 29-02 and 29-03:

- dependency_scanner:   Nightly dependency/CVE bump check
- log_anomaly:          Nightly log-anomaly review via OpenObserve
- backup_verifier:      Nightly Postgres dump verification via scratch container
- trend_reporter:       Weekly disk/VRAM trend report
"""
from __future__ import annotations

from . import dependency_scanner  # noqa: F401
from . import log_anomaly  # noqa: F401
from . import backup_verifier  # noqa: F401
from . import trend_reporter  # noqa: F401
