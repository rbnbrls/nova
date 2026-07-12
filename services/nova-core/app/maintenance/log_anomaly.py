"""Nightly log-anomaly reviewer.

Queries OpenObserve for log patterns over the last 24 hours, applies
simple heuristic anomaly detection (error counts, CRITICAL/FATAL lines,
traceback patterns), redacts sensitive data, and files (or comments on)
Forgejo issues with findings.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from app.config import settings
from app.forgejo import ForgejoClient

log = logging.getLogger("nova-core")

# Heuristic thresholds (tunable module-level constants)
MIN_ERROR_COUNT = 3          # minimum occurrences to report
SPIKE_RATIO = 2.0            # alert if count > 2x baseline
CRITICAL_KEYWORDS = [        # case-insensitive patterns
    "traceback",
    "exception",
    "unhandled",
    "panic",
]

# Redaction patterns
_REDACT_IP = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")
_REDACT_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_REDACT_PATH = re.compile(r"(/Users/\w+|/home/\w+|/app/\S+)")


# ------------------------------------------------------------------
# Redaction
# ------------------------------------------------------------------


def _redact(text: str) -> str:
    """Redact sensitive data from log lines."""
    text = _REDACT_IP.sub("[REDACTED]", text)
    text = _REDACT_EMAIL.sub("[REDACTED]", text)
    text = _REDACT_PATH.sub("[REDACTED]", text)
    return text


def _redact_samples(samples: list[str]) -> list[str]:
    """Redact a list of log samples, truncating each to 200 chars."""
    result: list[str] = []
    for line in samples:
        truncated = line[:200]
        result.append(_redact(truncated))
    return result


# ------------------------------------------------------------------
# OpenObserve query
# ------------------------------------------------------------------


async def _query_openobserve() -> list[dict[str, Any]]:
    """Query OpenObserve for log data over the last 24 hours.

    Returns a list of log entry dicts with at least ``level``, ``message``,
    and ``timestamp`` keys.  Returns empty list if OpenObserve is not
    configured or unreachable.
    """
    base_url = os.environ.get("OPENOBSERVE_URL", "").rstrip("/")
    org = os.environ.get("OPENOBSERVE_ORG", "default")

    if not base_url:
        log.warning("[MAINT] log-anomaly: OPENOBSERVE_URL not set — skipping")
        return []

    user = os.environ.get("OPENOBSERVE_USER", "")
    password = os.environ.get("OPENOBSERVE_PASSWORD", "")

    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(hours=24)).isoformat()
    window_end = now.isoformat()
    prev_start = (now - timedelta(hours=48)).isoformat()
    prev_end = (now - timedelta(hours=24)).isoformat()

    search_url = f"{base_url}/api/{org}/_search"
    auth_creds = (user, password) if user and password else None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Fetch logs from last 24h
            resp = await client.post(
                search_url,
                json={
                    "query": {
                        "sql": (
                            f"SELECT level, message, timestamp "
                            f"FROM \"default\" "
                            f"WHERE timestamp >= '{window_start}' "
                            f"AND timestamp <= '{window_end}' "
                            f"ORDER BY timestamp DESC "
                            f"LIMIT 5000"
                        ),
                    },
                },
                auth=auth_creds,
            )
            if resp.status_code != 200:
                log.warning(
                    "[MAINT] log-anomaly: OpenObserve query failed: %s %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return []

            data = resp.json()
            hits = data.get("hits", data.get("results", []))

            # Also fetch baseline (prior 24h) for count comparison
            baseline_resp = await client.post(
                search_url,
                json={
                    "query": {
                        "sql": (
                            f"SELECT level, count(*) as cnt "
                            f"FROM \"default\" "
                            f"WHERE timestamp >= '{prev_start}' "
                            f"AND timestamp <= '{prev_end}' "
                            f"GROUP BY level"
                        ),
                    },
                },
                auth=auth_creds,
            )
            baseline_counts: dict[str, int] = {}
            if baseline_resp.status_code == 200:
                baseline_data = baseline_resp.json()
                for row in baseline_data.get("hits", baseline_data.get("results", [])):
                    level = row.get("level", "").lower()
                    count = int(row.get("cnt", 0))
                    baseline_counts[level] = count

            return _normalize_logs(hits, baseline_counts)

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        log.warning("[MAINT] log-anomaly: OpenObserve connection failed: %s", e)
        return []
    except Exception as e:
        log.warning("[MAINT] log-anomaly: OpenObserve query error: %s", e)
        return []


def _normalize_logs(
    hits: list[dict[str, Any]],
    baseline_counts: dict[str, int],
) -> list[dict[str, Any]]:
    """Normalize OpenObserve results into a uniform format with level/message/timestamp.

    Attaches baseline counts as metadata.
    """
    logs: list[dict[str, Any]] = []
    for hit in hits:
        level = (hit.get("level") or "").lower()
        message = hit.get("message") or hit.get("log") or ""
        timestamp = hit.get("timestamp") or ""
        logs.append({
            "level": level,
            "message": str(message),
            "timestamp": str(timestamp),
        })

    # Attach baseline info as module-level metadata for the anomaly detector
    _baseline = baseline_counts
    return logs


_baseline: dict[str, int] = {}


# ------------------------------------------------------------------
# Anomaly detection (heuristics)
# ------------------------------------------------------------------


def _detect_anomalies(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply heuristic anomaly detection to log entries.

    Returns a list of anomaly dicts with keys:
      - pattern: short description
      - level: log level
      - count: occurrences in window
      - baseline_count: occurrences in prior window
      - spike_ratio: count / baseline (or ``None`` if baseline was 0)
      - samples: list of (redacted) sample log lines
    """
    if not logs:
        return []

    # Count by level
    level_counts: dict[str, int] = {}
    for entry in logs:
        level = entry["level"] or "info"
        level_counts[level] = level_counts.get(level, 0) + 1

    # Collect sample lines per level
    level_samples: dict[str, list[str]] = {}
    for entry in logs:
        level = entry["level"] or "info"
        msg = entry["message"]
        if level not in level_samples:
            level_samples[level] = []
        if len(level_samples[level]) < 10:
            level_samples[level].append(msg)

    anomalies: list[dict[str, Any]] = []

    # Check error-level count
    for level in ("error", "critical", "fatal"):
        count = level_counts.get(level, 0)
        base = _baseline.get(level, 0)
        ratio = (count / base) if base > 0 else None

        if level == "error" and count < MIN_ERROR_COUNT:
            continue  # errors need minimum count

        if count > 0:
            anomalies.append({
                "pattern": f"{level.upper()}-level messages",
                "level": level,
                "count": count,
                "baseline_count": base,
                "spike_ratio": round(ratio, 1) if ratio else None,
                "samples": _redact_samples(level_samples.get(level, [])[:5]),
            })

    # Check for CRITICAL/FATAL keywords in any level
    keyword_lines: list[str] = []
    for entry in logs:
        msg = entry["message"].lower()
        if any(kw in msg for kw in CRITICAL_KEYWORDS):
            truncated = entry["message"][:200]
            keyword_lines.append(truncated)
        if len(keyword_lines) >= 10:
            break

    if keyword_lines:
        anomalies.append({
            "pattern": "Keyword-triggered lines (traceback/exception/unhandled/panic)",
            "level": "any",
            "count": len(keyword_lines),
            "baseline_count": None,
            "spike_ratio": None,
            "samples": _redact_samples(keyword_lines),
        })

    return anomalies


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


async def run_log_anomaly_review() -> None:
    """Nightly review of log patterns for anomalies.

    Queries OpenObserve, applies heuristics, and files/updates a
    Forgejo issue if anomalies are found.
    """
    if not settings.maintenance_log_anomaly_enabled:
        log.debug("[MAINT] log-anomaly disabled via config toggle")
        return

    has_forgejo = bool(settings.forgejo_token)
    if not has_forgejo:
        log.warning(
            "[MAINT] log-anomaly: FORGEJO_TOKEN not set — findings logged locally only"
        )

    # Query OpenObserve
    logs = await _query_openobserve()
    if not logs:
        log.info("[MAINT] log-anomaly: no logs returned — nothing to review")
        return

    # Detect anomalies
    anomalies = _detect_anomalies(logs)

    if not anomalies:
        log.info("[MAINT] log-anomaly: no anomalies detected")
        return

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not has_forgejo:
        log.warning(
            "[MAINT] log-anomaly: %d anomaly pattern(s) detected "
            "(no Forgejo token — see above)", len(anomalies),
        )
        return

    # Build issue body
    body = _build_anomaly_body(anomalies)
    title = f"[maintenance] log anomaly: {len(anomalies)} pattern(s) ({date_str})"

    client = ForgejoClient(
        settings.forgejo_url,
        settings.forgejo_repo,
        settings.forgejo_token,
    )

    # Check for existing open log-anomaly issue
    existing = await client.open_issues_by_label("log-anomaly")
    maintenance_tagged = [i for i in existing if "maintenance" in str(i.get("labels", [])) or True]

    if maintenance_tagged:
        # Comment on existing issue
        existing_issue = maintenance_tagged[0]
        await client.comment_issue(
            existing_issue["number"],
            f"## Update {date_str}\n\n{body}",
        )
        log.info(
            "[MAINT] log-anomaly: commented on existing issue #%d",
            existing_issue["number"],
        )
    else:
        # Create new issue
        issue_number = await client.create_issue(
            title=title,
            body=body,
            labels=["maintenance", "log-anomaly"],
        )
        log.info("[MAINT] log-anomaly: new issue #%d created", issue_number)


def _build_anomaly_body(anomalies: list[dict[str, Any]]) -> str:
    """Build Forgejo issue body from anomaly list."""
    lines: list[str] = [
        "## Log Anomaly Review",
        "",
        f"**Review window:** Last 24 hours",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "### Summary",
        "",
        "| Pattern | Level | Count (24h) | Baseline | Spike Ratio |",
        "|---------|-------|-------------|----------|-------------|",
    ]

    for a in anomalies:
        baseline_str = str(a["baseline_count"]) if a["baseline_count"] is not None else "N/A"
        spike_str = str(a["spike_ratio"]) if a["spike_ratio"] is not None else "N/A"
        lines.append(
            f"| {a['pattern']} | {a['level']} | {a['count']} "
            f"| {baseline_str} | {spike_str} |"
        )

    lines.append("")

    for i, a in enumerate(anomalies, 1):
        lines.append(f"### Anomaly {i}: {a['pattern']}")
        lines.append("")
        if a["samples"]:
            lines.append("Sample log lines (redacted):")
            lines.append("")
            lines.append("```")
            for s in a["samples"]:
                lines.append(s)
            lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append("_Log excerpts are redacted for sensitive data (IPs, emails, paths)._")

    return "\n".join(lines)
