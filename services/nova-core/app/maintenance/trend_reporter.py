"""Weekly disk/VRAM trend report.

Collects system metrics (disk usage, GPU/VRAM stats, Postgres DB size)
via stdlib and subprocess, compares against prior readings from an
existing Forgejo issue, and files a weekly trend report.

Threshold alerts are generated for:
- Disk usage >80% (WARNING) / >90% (CRITICAL)
- VRAM usage >85% (WARNING) / >95% (CRITICAL)
- GPU temperature >80°C (WARNING)
- Week-over-week delta >10% (highlighted)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.db import get_pool
from app.forgejo import ForgejoClient

log = logging.getLogger("nova-core")

# Thresholds (module-level constants, tunable)
DISK_WARN_PCT = 80
DISK_CRIT_PCT = 90
VRAM_WARN_PCT = 85
VRAM_CRIT_PCT = 95
GPU_TEMP_WARN = 80
DELTA_ALERT_PCT = 10

_SUBPROCESS_TIMEOUT = 30  # seconds


# ------------------------------------------------------------------
# Subprocess helper
# ------------------------------------------------------------------


async def _run_cmd(*args: str) -> tuple[int, str, str]:
    """Run an external command asynchronously with a timeout."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=_SUBPROCESS_TIMEOUT,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "", f"TIMEOUT after {_SUBPROCESS_TIMEOUT}s"

    return (
        proc.returncode or 0,
        stdout_bytes.decode(errors="replace") if stdout_bytes else "",
        stderr_bytes.decode(errors="replace") if stderr_bytes else "",
    )


# ------------------------------------------------------------------
# Metrics collection
# ------------------------------------------------------------------


def _get_disk_usage(path: str = "/") -> dict[str, Any]:
    """Collect disk usage statistics via shutil."""
    try:
        usage = shutil.disk_usage(path)
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        free_gb = usage.free / (1024**3)
        pct = (usage.used / usage.total) * 100
        return {
            "total_gb": round(total_gb, 1),
            "used_gb": round(used_gb, 1),
            "free_gb": round(free_gb, 1),
            "pct": round(pct, 1),
        }
    except Exception as e:
        log.warning("[MAINT] trend: disk usage failed: %s", e)
        return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "pct": 0}


async def _get_gpu_metrics() -> dict[str, Any]:
    """Collect GPU/VRAM metrics via nvidia-smi subprocess."""
    try:
        ret, stdout, stderr = await _run_cmd(
            "nvidia-smi",
            "--query-gpu=memory.total,memory.used,temperature.gpu,utilization.gpu",
            "--format=csv,noheader,nounits",
        )
        if ret != 0 or not stdout.strip():
            log.warning("[MAINT] trend: nvidia-smi failed: %s", stderr[:200])
            return {
                "vram_total_mb": "N/A",
                "vram_used_mb": "N/A",
                "vram_pct": "N/A",
                "gpu_temp_c": "N/A",
                "gpu_util_pct": "N/A",
            }

        parts = [p.strip() for p in stdout.strip().split(",")]
        if len(parts) >= 4:
            vram_total = int(parts[0]) if parts[0].isdigit() else 0
            vram_used = int(parts[1]) if parts[1].isdigit() else 0
            gpu_temp = int(parts[2]) if parts[2].isdigit() else 0
            gpu_util = int(parts[3]) if parts[3].isdigit() else 0
            vram_pct = (vram_used / vram_total * 100) if vram_total > 0 else 0
            return {
                "vram_total_mb": vram_total,
                "vram_used_mb": vram_used,
                "vram_pct": round(vram_pct, 1),
                "gpu_temp_c": gpu_temp,
                "gpu_util_pct": gpu_util,
            }
    except FileNotFoundError:
        log.warning("[MAINT] trend: nvidia-smi not found (no GPU?)")
    except Exception as e:
        log.warning("[MAINT] trend: GPU metrics error: %s", e)

    return {
        "vram_total_mb": "N/A",
        "vram_used_mb": "N/A",
        "vram_pct": "N/A",
        "gpu_temp_c": "N/A",
        "gpu_util_pct": "N/A",
    }


async def _get_postgres_size() -> str:
    """Query Postgres database size."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            size_bytes = await conn.fetchval("SELECT pg_database_size('nova')")
            if size_bytes:
                size_gb = size_bytes / (1024**3)
                return f"{size_gb:.1f} GB"
    except Exception as e:
        log.warning("[MAINT] trend: Postgres size query failed: %s", e)
    return "N/A"


def _assess_thresholds(
    disk_pct: float,
    vram_pct: float | str,
    gpu_temp: float | str,
) -> tuple[str, list[str]]:
    """Assess metric thresholds and return (status, alerts)."""
    alerts: list[str] = []

    # Disk
    if disk_pct >= DISK_CRIT_PCT:
        alerts.append(f"🔴 CRITICAL: Disk usage {disk_pct}% ≥ {DISK_CRIT_PCT}%")
    elif disk_pct >= DISK_WARN_PCT:
        alerts.append(f"🟡 WARNING: Disk usage {disk_pct}% ≥ {DISK_WARN_PCT}%")

    # VRAM
    if isinstance(vram_pct, (int, float)):
        if vram_pct >= VRAM_CRIT_PCT:
            alerts.append(f"🔴 CRITICAL: VRAM usage {vram_pct}% ≥ {VRAM_CRIT_PCT}%")
        elif vram_pct >= VRAM_WARN_PCT:
            alerts.append(f"🟡 WARNING: VRAM usage {vram_pct}% ≥ {VRAM_WARN_PCT}%")

    # GPU temp
    if isinstance(gpu_temp, (int, float)):
        if gpu_temp >= GPU_TEMP_WARN:
            alerts.append(f"🔴 WARNING: GPU temperature {gpu_temp}°C ≥ {GPU_TEMP_WARN}°C")

    if not alerts:
        return "✅ OK", []
    return "⚠️ WARNING" if len(alerts) <= 2 else "🚨 CRITICAL", alerts


# ------------------------------------------------------------------
# Trend comparison
# ------------------------------------------------------------------


def _parse_previous_readings(issue_body: str) -> dict[str, Any] | None:
    """Parse previous trend data from an HTML comment in the issue body."""
    match = re.search(r"<!-- trend-data:\s*(\{.+?\})\s*-->", issue_body, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _build_trend_data(current: dict[str, Any]) -> str:
    """Build the machine-parseable trend data HTML comment."""
    data = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "metrics": {
            "disk_pct": current.get("disk", {}).get("pct"),
            "disk_used_gb": current.get("disk", {}).get("used_gb"),
            "vram_pct": current.get("gpu", {}).get("vram_pct"),
            "vram_used_mb": current.get("gpu", {}).get("vram_used_mb"),
            "gpu_temp_c": current.get("gpu", {}).get("gpu_temp_c"),
            "pg_size_gb": current.get("pg_size"),
        },
    }
    return f"<!-- trend-data: {json.dumps(data)} -->"


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


async def run_trend_report() -> None:
    """Weekly system trend report generation.

    Full flow documented in PLAN.md § Task 2.
    """
    if not settings.maintenance_trend_report_enabled:
        log.debug("[MAINT] trend report disabled via config toggle")
        return

    has_forgejo = bool(settings.forgejo_token)
    if not has_forgejo:
        log.warning(
            "[MAINT] trend report: FORGEJO_TOKEN not set — findings logged locally only"
        )

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Collect metrics
    disk = _get_disk_usage("/")
    docker_disk = _get_disk_usage("/var/lib/docker") if os.path.isdir("/var/lib/docker") else {}
    gpu = await _get_gpu_metrics()
    pg_size = await _get_postgres_size()

    # Assess threshold alerts
    status, alerts = _assess_thresholds(
        disk.get("pct", 0),
        gpu.get("vram_pct", "N/A"),
        gpu.get("gpu_temp_c", "N/A"),
    )

    current: dict[str, Any] = {
        "disk": disk,
        "docker_disk": docker_disk,
        "gpu": gpu,
        "pg_size": pg_size,
    }

    if not has_forgejo:
        log.info(
            "[MAINT] trend report: %s — disk: %s%% used, VRAM: %s (no Forgejo token)",
            status, disk.get("pct"), gpu.get("vram_pct"),
        )
        return

    # Build issue body
    body = _build_report_body(current, status, alerts, date_str)

    client = ForgejoClient(
        settings.forgejo_url, settings.forgejo_repo, settings.forgejo_token,
    )

    # Check for existing open trend issue
    existing = await client.open_issues_by_label("trend")

    trend_data_comment = _build_trend_data(current)

    if existing:
        issue = existing[0]
        existing_body = issue.get("body", "")
        prior_data = _parse_previous_readings(existing_body)

        if prior_data:
            delta_section = _build_delta_section(current, prior_data)
            comment_body = f"## Week of {date_str}\n\n{delta_section}\n\n{trend_data_comment}"
        else:
            comment_body = f"## Week of {date_str}\n\n{body}\n\n{trend_data_comment}"

        await client.comment_issue(issue["number"], comment_body)
        log.info("[MAINT] trend report: appended to existing issue #%d", issue["number"])
    else:
        title = f"[maintenance] system trend report ({date_str})"
        full_body = f"{body}\n\n{trend_data_comment}"
        issue_number = await client.create_issue(
            title=title, body=full_body, labels=["maintenance", "trend"],
        )
        log.info("[MAINT] trend report: new issue #%d created", issue_number)


def _build_report_body(
    current: dict[str, Any],
    status: str,
    alerts: list[str],
    date_str: str,
) -> str:
    """Build the Forgejo issue body."""
    disk = current["disk"]
    docker_disk = current.get("docker_disk", {})
    gpu = current["gpu"]
    pg_size = current["pg_size"]

    lines: list[str] = [
        f"## System Trend Report — {status}",
        "",
        f"**Date:** {date_str}",
        "",
    ]

    if alerts:
        lines.append("### ⚠️ Alerts")
        for a in alerts:
            lines.append(f"- {a}")
        lines.append("")

    lines.append("### Disk Usage")
    lines.append("")
    lines.append(f"| Mount | Total (GB) | Used (GB) | Free (GB) | Used % |")
    lines.append(f"|-------|-----------|----------|-----------|--------|")
    lines.append(
        f"| `/` | {disk.get('total_gb', 'N/A')} | {disk.get('used_gb', 'N/A')} "
        f"| {disk.get('free_gb', 'N/A')} | {disk.get('pct', 'N/A')}% |"
    )
    if docker_disk:
        lines.append(
            f"| `/var/lib/docker` | {docker_disk.get('total_gb', 'N/A')} | {docker_disk.get('used_gb', 'N/A')} "
            f"| {docker_disk.get('free_gb', 'N/A')} | {docker_disk.get('pct', 'N/A')}% |"
        )
    lines.append("")

    lines.append("### GPU / VRAM")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| VRAM Total | {gpu.get('vram_total_mb', 'N/A')} MB |")
    lines.append(f"| VRAM Used | {gpu.get('vram_used_mb', 'N/A')} MB |")
    lines.append(f"| VRAM Used % | {gpu.get('vram_pct', 'N/A')}% |")
    lines.append(f"| GPU Temp | {gpu.get('gpu_temp_c', 'N/A')} °C |")
    lines.append(f"| GPU Util | {gpu.get('gpu_util_pct', 'N/A')}% |")
    lines.append("")

    lines.append(f"### Postgres Database Size")
    lines.append("")
    lines.append(f"| Database | Size |")
    lines.append(f"|----------|------|")
    lines.append(f"| `nova` | {pg_size} |")

    return "\n".join(lines)


def _build_delta_section(
    current: dict[str, Any],
    prior_data: dict[str, Any],
) -> str:
    """Build a delta-comparison section comparing current metrics to prior readings."""
    prior_metrics = prior_data.get("metrics", {})
    lines: list[str] = [
        "### 📊 Week-over-Week Changes",
        "",
        "| Metric | Current | Previous | Delta | Δ% |",
        "|--------|---------|----------|-------|-----|",
    ]

    comparisons: list[tuple[str, Any, Any]] = [
        ("Disk Usage %", current.get("disk", {}).get("pct"), prior_metrics.get("disk_pct")),
        ("Disk Used (GB)", current.get("disk", {}).get("used_gb"), prior_metrics.get("disk_used_gb")),
        ("VRAM Used %", current.get("gpu", {}).get("vram_pct"), prior_metrics.get("vram_pct")),
        ("GPU Temp (°C)", current.get("gpu", {}).get("gpu_temp_c"), prior_metrics.get("gpu_temp_c")),
        ("Postgres Size", current.get("pg_size"), prior_metrics.get("pg_size_gb")),
    ]

    for name, cur, prev in comparisons:
        if cur is None:
            cur_display = "N/A"
        elif isinstance(cur, str):
            cur_display = cur
        else:
            cur_display = str(cur)

        if prev is None:
            prev_display = "N/A"
            delta = "N/A"
            delta_pct = "N/A"
        else:
            if isinstance(prev, (int, float)) and isinstance(cur, (int, float)) and prev != 0:
                delta_val = cur - prev
                delta_pct_val = (delta_val / prev) * 100
                delta = f"{delta_val:+.1f}"
                delta_pct = f"{delta_pct_val:+.1f}%"
                if isinstance(prev, str):
                    prev_display = prev
                else:
                    prev_display = str(prev)
                if isinstance(cur, str):
                    cur_display = cur
                else:
                    cur_display = str(cur)

                # Flag significant changes
                if abs(delta_pct_val) >= DELTA_ALERT_PCT:
                    delta_pct += " ⚠️"
            else:
                delta = "N/A"
                delta_pct = "N/A"
                if isinstance(prev, str):
                    prev_display = prev
                else:
                    prev_display = str(prev)

        lines.append(f"| {name} | {cur_display} | {prev_display} | {delta} | {delta_pct} |")

    return "\n".join(lines)
