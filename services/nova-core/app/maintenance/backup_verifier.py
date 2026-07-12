"""Nightly backup verification.

Finds the latest Postgres dump in the configured backup directory,
spins up an ephemeral scratch Postgres container, restores the dump,
runs verification queries (table count, row counts), cleans up the
scratch container, and files a success/failure Forgejo issue.

All Docker operations use ``asyncio.create_subprocess_exec`` with
timeouts.  The scratch container is always removed (even on failure).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone

from app.config import settings
from app.forgejo import ForgejoClient

log = logging.getLogger("nova-core")

_SUBPROCESS_TIMEOUT = 120  # seconds
_CONTAINER_IMAGE = "postgres:16-alpine"


# ------------------------------------------------------------------
# Subprocess helpers
# ------------------------------------------------------------------


async def _run_cmd(*args: str, stdin: str | None = None) -> tuple[int, str, str]:
    """Run an external command asynchronously with a timeout."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(input=stdin.encode() if stdin else None),
            timeout=_SUBPROCESS_TIMEOUT,
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
# Core flow
# ------------------------------------------------------------------


async def run_backup_verification() -> None:
    """Nightly verification of the latest Postgres backup dump.

    Full flow documented in PLAN.md § Task 1.
    """
    if not settings.maintenance_backup_verify_enabled:
        log.debug("[MAINT] backup verification disabled via config toggle")
        return

    has_forgejo = bool(settings.forgejo_token)
    if not has_forgejo:
        log.warning(
            "[MAINT] backup verify: FORGEJO_TOKEN not set — findings logged locally only"
        )

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    container_name = f"nova-backup-verify-{timestamp}"

    # 1. Find latest dump file
    dump_path = await _find_latest_dump()
    if dump_path is None:
        log.warning("[MAINT] backup verify: no dump files found in %s", settings.backup_dump_dir)
        if has_forgejo:
            client = ForgejoClient(
                settings.forgejo_url, settings.forgejo_repo, settings.forgejo_token,
            )
            await client.create_issue(
                title=f"[maintenance] backup verification: no dump files found ({date_str})",
                body=(
                    f"## Backup Verification — No Dump Files\n\n"
                    f"**Date:** {date_str}\n"
                    f"**Directory:** `{settings.backup_dump_dir}`\n"
                    f"**Pattern:** `{settings.backup_dump_pattern}`\n\n"
                    f"No dump files matching the configured pattern were found."
                ),
                labels=["maintenance", "backup"],
            )
        return

    dump_size = os.path.getsize(dump_path) if os.path.exists(dump_path) else 0
    if dump_size == 0:
        log.warning("[MAINT] backup verify: dump file %s is empty", dump_path)
        if has_forgejo:
            client = ForgejoClient(
                settings.forgejo_url, settings.forgejo_repo, settings.forgejo_token,
            )
            await client.create_issue(
                title=f"[maintenance] backup verification: no dump files found ({date_str})",
                body=(
                    f"## Backup Verification — Empty Dump File\n\n"
                    f"**Date:** {date_str}\n"
                    f"**File:** `{dump_path}`\n\n"
                    f"The dump file exists but is 0 bytes."
                ),
                labels=["maintenance", "backup"],
            )
        return

    log.info("[MAINT] backup verify: found dump %s (%.1f MB)", dump_path, dump_size / 1e6)

    # 2. Create scratch Postgres container
    try:
        ret, stdout, stderr = await _run_cmd(
            "docker", "run", "-d",
            "--name", container_name,
            "-e", "POSTGRES_PASSWORD=verify",
            _CONTAINER_IMAGE,
        )
        if ret != 0:
            log.warning("[MAINT] backup verify: docker run failed: %s", stderr[:300])
            # Try removing stale container first
            await _run_cmd("docker", "rm", "-f", container_name)
            ret2, _, stderr2 = await _run_cmd(
                "docker", "run", "-d",
                "--name", container_name,
                "-e", "POSTGRES_PASSWORD=verify",
                _CONTAINER_IMAGE,
            )
            if ret2 != 0:
                raise RuntimeError(f"docker run failed after retry: {stderr2[:300]}")
    except FileNotFoundError:
        log.warning("[MAINT] backup verify: docker not available — aborting")
        return

    try:
        # 3. Wait for container healthy
        healthy = await _wait_for_postgres(container_name)
        if not healthy:
            raise RuntimeError("scratch container did not become healthy in time")

        # 4. Restore dump
        restore_ok = await _restore_dump(container_name, dump_path)
        if not restore_ok:
            raise RuntimeError("dump restore failed")

        # 5. Run verification queries
        tables = await _run_query(container_name, "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        columns = await _run_query(container_name, "SELECT count(*) FROM information_schema.columns")
        row_counts = await _run_query(
            container_name,
            "SELECT schemaname || '.' || tablename, n_live_tup::text FROM pg_stat_user_tables ORDER BY n_live_tup DESC",
        )

        table_count = int(tables.strip()) if tables.strip().isdigit() else 0
        column_count = int(columns.strip()) if columns.strip().isdigit() else 0

        # Parse row counts
        rows_parsed: list[tuple[str, int]] = []
        for line in row_counts.strip().split("\n"):
            line = line.strip()
            if "|" in line:
                parts = line.split("|")
                if len(parts) >= 2:
                    name = parts[0].strip()
                    try:
                        count = int(parts[1].strip())
                        rows_parsed.append((name, count))
                    except ValueError:
                        pass

        success = table_count > 0

        if success:
            log.info(
                "[MAINT] backup verify: SUCCESS — %d tables, %d columns",
                table_count, column_count,
            )
        else:
            log.warning("[MAINT] backup verify: FAILURE — 0 tables in restored dump")

        # 6, 7. Cleanup + file issue
        await _cleanup_container(container_name)

        await _file_verification_result(
            dump_path, dump_size, table_count, column_count,
            rows_parsed, success, date_str, has_forgejo,
        )

    except Exception as e:
        log.warning("[MAINT] backup verify: error: %s", e)
        await _cleanup_container(container_name)
        if has_forgejo:
            client = ForgejoClient(
                settings.forgejo_url, settings.forgejo_repo, settings.forgejo_token,
            )
            await client.create_issue(
                title=f"[maintenance] backup verification FAILED ({date_str})",
                body=(
                    f"## Backup Verification — FAILED\n\n"
                    f"**Date:** {date_str}\n"
                    f"**Dump:** `{dump_path}`\n"
                    f"**Error:** `{e}`"
                ),
                labels=["maintenance", "backup", "heal-failed"],
            )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _find_latest_dump() -> str | None:
    """Find the most recent dump file in the backup directory."""
    dump_dir = settings.backup_dump_dir
    pattern = settings.backup_dump_pattern

    if not os.path.isdir(dump_dir):
        log.warning("[MAINT] backup verify: backup directory %s does not exist", dump_dir)
        return None

    # Convert glob-style pattern to simple list filter
    candidates: list[str] = []
    for fname in os.listdir(dump_dir):
        if _matches_pattern(fname, pattern):
            full_path = os.path.join(dump_dir, fname)
            if os.path.isfile(full_path):
                candidates.append(full_path)

    if not candidates:
        return None

    # Sort by mtime, newest first
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def _matches_pattern(filename: str, pattern: str) -> bool:
    """Simple wildcard match (supports * and ?)."""
    regex_parts = []
    for chunk in re.split(r"(\*|\?)", pattern):
        if chunk == "*":
            regex_parts.append(".*")
        elif chunk == "?":
            regex_parts.append(".")
        else:
            regex_parts.append(re.escape(chunk))
    return bool(re.fullmatch("".join(regex_parts), filename))


async def _wait_for_postgres(container_name: str, max_attempts: int = 30, delay: int = 1) -> bool:
    """Poll pg_isready until the container is healthy."""
    for attempt in range(max_attempts):
        ret, stdout, _ = await _run_cmd(
            "docker", "exec", container_name,
            "pg_isready", "-U", "postgres",
        )
        if ret == 0:
            return True
        await asyncio.sleep(delay)
    return False


async def _restore_dump(container_name: str, dump_path: str) -> bool:
    """Restore a dump file into the scratch container via psql."""
    with open(dump_path, "r") as f:
        dump_content = f.read()

    ret, stdout, stderr = await _run_cmd(
        "docker", "exec", "-i", container_name,
        "psql", "-U", "postgres",
        stdin=dump_content,
    )
    if ret != 0:
        log.warning("[MAINT] backup verify: restore failed: %s", stderr[:300])
        return False
    return True


async def _run_query(container_name: str, query: str) -> str:
    """Run a SQL query against the scratch Postgres container."""
    ret, stdout, stderr = await _run_cmd(
        "docker", "exec", "-i", container_name,
        "psql", "-U", "postgres", "-t", "-c", query,
    )
    if ret != 0:
        log.warning("[MAINT] backup verify: query failed: %s", stderr[:200])
        return ""
    return stdout


async def _cleanup_container(container_name: str) -> None:
    """Stop and remove the scratch container."""
    await _run_cmd("docker", "stop", "--time", "10", container_name)
    await _run_cmd("docker", "rm", "-f", container_name)
    log.debug("[MAINT] backup verify: container %s removed", container_name)


async def _file_verification_result(
    dump_path: str,
    dump_size: int,
    table_count: int,
    column_count: int,
    rows_parsed: list[tuple[str, int]],
    success: bool,
    date_str: str,
    has_forgejo: bool,
) -> None:
    """File the verification result as a Forgejo issue."""
    if not has_forgejo:
        status = "SUCCESS" if success else "FAILURE"
        log.info("[MAINT] backup verify: %s (no Forgejo token)", status)
        return

    client = ForgejoClient(
        settings.forgejo_url, settings.forgejo_repo, settings.forgejo_token,
    )

    body_lines = [
        f"## Backup Verification — {'OK' if success else 'FAILED'}",
        "",
        f"**Date:** {date_str}",
        f"**Dump file:** `{dump_path}`",
        f"**Dump size:** {dump_size / 1e6:.1f} MB",
        f"**Tables restored:** {table_count}",
        f"**Total columns:** {column_count}",
        "",
    ]

    if rows_parsed:
        body_lines.append("### Row Counts per Table")
        body_lines.append("")
        body_lines.append("| Table | Row Count |")
        body_lines.append("|-------|-----------|")
        for name, count in rows_parsed:
            body_lines.append(f"| {name} | {count} |")
        body_lines.append("")

    if success:
        title = f"[maintenance] backup verification OK ({date_str})"
        labels = ["maintenance", "backup"]
    else:
        title = f"[maintenance] backup verification FAILED ({date_str})"
        labels = ["maintenance", "backup", "heal-failed"]

    # Check for existing open backup issue
    existing = await client.open_issues_by_label("backup")
    if existing:
        issue = existing[0]
        await client.comment_issue(issue["number"], "\n".join(body_lines))
        log.info("[MAINT] backup verify: commented on existing issue #%d", issue["number"])
    else:
        issue_number = await client.create_issue(title=title, body="\n".join(body_lines), labels=labels)
        log.info("[MAINT] backup verify: new issue #%d created", issue_number)
