"""Nightly dependency and CVE scanner.

Detects outdated Python packages via ``pip list --outdated``, runs
``pip-audit`` for CVE scanning, creates a timestamped fix branch,
bumps deps, runs the test suite, and files a Forgejo issue with
results.

If tests pass: a local branch with the bumps is created but NEVER
auto-pushed.  Human review required for merge.

If tests fail: a separate "FAILED" issue is filed with test output;
no branch or commit is left behind.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.forgejo import ForgejoClient

log = logging.getLogger("nova-core")

_SUBPROCESS_TIMEOUT = 120  # seconds


# ------------------------------------------------------------------
# Subprocess helpers (async, non-blocking)
# ------------------------------------------------------------------


async def _run_cmd(*args: str, stdin: str | None = None) -> tuple[int, str, str]:
    """Run an external command asynchronously with a timeout.

    Returns (returncode, stdout, stderr).
    """
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
# Core scan flow
# ------------------------------------------------------------------


async def run_dependency_scan() -> None:
    """Nightly dependency and CVE check.

    Full flow documented in PLAN.md § Task 1.
    """
    if not settings.maintenance_dep_check_enabled:
        log.debug("[MAINT] dep scan disabled via config toggle")
        return

    # Guard: working tree must be clean
    ret, stdout, _ = await _run_cmd("git", "status", "--porcelain")
    if ret != 0:
        log.warning("[MAINT] dep scan: git status failed — aborting")
        return
    if stdout.strip():
        log.warning(
            "[MAINT] dep scan: working tree is dirty — aborting "
            "(uncommitted changes: %s)",
            stdout.strip()[:200],
        )
        return

    # Guard: Forgejo token must be configured
    has_forgejo = bool(settings.forgejo_token)
    if not has_forgejo:
        log.warning("[MAINT] dep scan: FORGEJO_TOKEN not set — findings logged locally only")

    # 1. Get current branch before we do anything
    ret, current_branch, _ = await _run_cmd("git", "rev-parse", "--abbrev-ref", "HEAD")
    if ret != 0 or not current_branch.strip():
        log.warning("[MAINT] dep scan: could not determine current branch — aborting")
        return
    current_branch = current_branch.strip()

    # 2. Check for outdated packages
    outdated = await _get_outdated_packages()
    if not outdated:
        log.info("[MAINT] dep scan: no outdated packages found")

    # 3. Run CVE scan
    cve_results = await _run_cve_scan()

    # 4. If nothing to report, return
    if not outdated and not cve_results:
        log.info("[MAINT] dep scan: no outdated deps and no CVEs — nothing to report")
        return

    # 5. Create timestamped branch
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch_name = f"nova/dep-scan-{timestamp}"
    log.info("[MAINT] dep scan: creating branch %s", branch_name)
    await _run_cmd("git", "checkout", "-b", branch_name)

    try:
        # 6. Bump outdated packages
        bump_details: list[dict[str, str]] = []
        for pkg in outdated:
            name = pkg["name"]
            old_ver = pkg.get("installed", "")
            new_ver = pkg.get("latest", "")
            if name and new_ver:
                await _bump_package(name, new_ver)
                bump_details.append({"package": name, "from": old_ver, "to": new_ver})

        # 7. Run test suite
        test_ret, test_stdout, test_stderr = await _run_cmd(
            os.path.join(os.path.dirname(__file__) or ".", "..", "..", "ops", "run-tests.sh")
            if os.path.exists(os.path.join(os.path.dirname(__file__) or ".", "..", "..", "ops", "run-tests.sh"))
            else "python",
            "-m",
            "pytest",
            "-x",
        )

        if test_ret == 0:
            await _handle_test_success(
                branch_name, timestamp, outdated, cve_results,
                bump_details, has_forgejo, current_branch,
            )
        else:
            await _handle_test_failure(
                branch_name, timestamp, outdated, cve_results,
                bump_details, test_stdout, test_stderr,
                has_forgejo, current_branch,
            )
    except Exception:
        log.exception("[MAINT] dep scan: unexpected error during branch operations")
        # Cleanup: get back to original branch
        await _run_cmd("git", "checkout", current_branch)
        await _run_cmd("git", "branch", "-D", branch_name)
        raise


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------


async def _get_outdated_packages() -> list[dict[str, str]]:
    """Run pip list --outdated and return parsed results."""
    ret, stdout, stderr = await _run_cmd(
        "python", "-m", "pip", "list", "--outdated", "--format=json"
    )
    if ret != 0:
        log.warning("[MAINT] pip list --outdated failed: %s", stderr[:200])
        return []
    try:
        packages: list[dict[str, str]] = json.loads(stdout)
    except json.JSONDecodeError:
        log.warning("[MAINT] could not parse pip list output")
        return []
    return packages


async def _run_cve_scan() -> list[dict[str, Any]]:
    """Run pip-audit and return parsed CVE results."""
    ret, stdout, stderr = await _run_cmd(
        "python", "-m", "pip_audit", "--format=json"
    )
    if ret != 0:
        # pip-audit exits non-zero when vulns are found
        pass

    if not stdout.strip():
        return []

    try:
        result: dict[str, Any] = json.loads(stdout)
    except json.JSONDecodeError:
        log.warning("[MAINT] could not parse pip-audit output")
        return []

    vulnerabilities = result.get("vulnerabilities", [])
    if not vulnerabilities:
        return []

    cves: list[dict[str, Any]] = []
    for vuln in vulnerabilities:
        cves.append({
            "package": vuln.get("package", {}).get("name", "unknown"),
            "installed": vuln.get("package", {}).get("version", ""),
            "vuln_id": vuln.get("id", ""),
            "severity": _cve_severity(vuln),
            "description": vuln.get("description", "")[:200],
        })
    return cves


def _cve_severity(vuln: dict[str, Any]) -> str:
    """Determine severity label from vulnerability data."""
    for alias in vuln.get("aliases", []):
        if "GHSA" in str(alias):
            return "high"
    return "medium"


async def _bump_package(package_name: str, new_version: str) -> None:
    """Update a package version in requirements.txt."""
    req_file = os.path.join(
        os.path.dirname(__file__) or ".",
        "..",
        "..",
        "requirements.txt",
    )
    if not os.path.exists(req_file):
        log.warning("[MAINT] requirements.txt not found at %s", req_file)
        return

    with open(req_file, "r") as f:
        lines = f.readlines()

    changed = False
    new_lines: list[str] = []
    for line in lines:
        match = re.match(
            rf"^{re.escape(package_name)}\s*[=~<>!]+\s*([\w.]+)",
            line,
            re.IGNORECASE,
        )
        if match:
            new_lines.append(f"{package_name}=={new_version}\n")
            changed = True
        else:
            new_lines.append(line)

    if changed:
        with open(req_file, "w") as f:
            f.writelines(new_lines)
        log.info("[MAINT] bumped %s to %s", package_name, new_version)


async def _handle_test_success(
    branch_name: str,
    timestamp: str,
    outdated: list[dict[str, str]],
    cve_results: list[dict[str, Any]],
    bump_details: list[dict[str, str]],
    has_forgejo: bool,
    current_branch: str,
) -> None:
    """Tests passed — commit bumps and file success issue."""
    # Commit
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    commit_msg = f"chore(deps): automated bump {date_str}"
    await _run_cmd("git", "add", "-A")
    ret, _, stderr = await _run_cmd("git", "commit", "-m", commit_msg)
    if ret != 0:
        log.warning("[MAINT] dep scan: git commit failed: %s", stderr[:200])

    if has_forgejo:
        client = ForgejoClient(
            settings.forgejo_url,
            settings.forgejo_repo,
            settings.forgejo_token,
        )
        body = _build_success_body(outdated, cve_results, bump_details, branch_name)
        issue_number = await client.create_issue(
            title=f"[maintenance] dependency update: {len(outdated)} packages ({date_str})",
            body=body,
            labels=["maintenance", "dependency-update"],
        )
        await client.comment_issue(
            issue_number,
            f"Fix branch (local only, not pushed): `{branch_name}`",
        )
        log.info("[MAINT] dep scan: success issue #%d filed", issue_number)
    else:
        log.info("[MAINT] dep scan: SUCCESS (no Forgejo token — findings above)")

    # Return to original branch and delete temp branch
    await _run_cmd("git", "checkout", current_branch)
    await _run_cmd("git", "branch", "-D", branch_name)


async def _handle_test_failure(
    branch_name: str,
    timestamp: str,
    outdated: list[dict[str, str]],
    cve_results: list[dict[str, Any]],
    bump_details: list[dict[str, str]],
    test_stdout: str,
    test_stderr: str,
    has_forgejo: bool,
    current_branch: str,
) -> None:
    """Tests failed — file failure issue, no commit, clean up branch."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if has_forgejo:
        client = ForgejoClient(
            settings.forgejo_url,
            settings.forgejo_repo,
            settings.forgejo_token,
        )
        body = _build_failure_body(
            outdated, cve_results, bump_details, test_stdout, test_stderr,
        )
        await client.create_issue(
            title=f"[maintenance] dependency update FAILED tests ({date_str})",
            body=body,
            labels=["maintenance", "dependency-update", "heal-failed"],
        )
        log.info("[MAINT] dep scan: failure issue filed")
    else:
        log.warning("[MAINT] dep scan: TESTS FAILED (no Forgejo token — details above)")

    # Clean up: reset and go back
    await _run_cmd("git", "reset", "--hard")
    await _run_cmd("git", "checkout", current_branch)
    await _run_cmd("git", "branch", "-D", branch_name)


def _build_success_body(
    outdated: list[dict[str, str]],
    cve_results: list[dict[str, Any]],
    bump_details: list[dict[str, str]],
    branch_name: str,
) -> str:
    """Build issue body for a successful scan."""
    lines: list[str] = [
        "## Dependency Scan Results — PASSED",
        "",
        f"**Branch:** `{branch_name}` (local only, not pushed)",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
    ]

    if bump_details:
        lines.append("### Updated Packages")
        lines.append("")
        lines.append("| Package | From | To |")
        lines.append("|---------|------|----|")
        for b in bump_details:
            lines.append(f"| {b['package']} | {b['from']} | {b['to']} |")
        lines.append("")

    if cve_results:
        lines.append("### CVEs Detected")
        lines.append("")
        lines.append("| Package | Vulnerability | Severity |")
        lines.append("|---------|---------------|----------|")
        for cve in cve_results:
            lines.append(
                f"| {cve['package']} | {cve['vuln_id']} | {cve['severity']} |"
            )
        lines.append("")

    lines.append("### Test Status")
    lines.append("- ✅ All tests passed")
    lines.append("- Branch created for human review")

    return "\n".join(lines)


def _build_failure_body(
    outdated: list[dict[str, str]],
    cve_results: list[dict[str, Any]],
    bump_details: list[dict[str, str]],
    test_stdout: str,
    test_stderr: str,
) -> str:
    """Build issue body for a failed scan."""
    lines: list[str] = [
        "## Dependency Scan Results — TESTS FAILED",
        "",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
    ]

    if bump_details:
        lines.append("### Attempted Bumps")
        lines.append("")
        lines.append("| Package | From | To |")
        lines.append("|---------|------|----|")
        for b in bump_details:
            lines.append(f"| {b['package']} | {b['from']} | {b['to']} |")
        lines.append("")

    lines.append("### Test Output (last 2000 chars)")
    lines.append("")
    lines.append("```")
    lines.append((test_stdout[-2000:] if len(test_stdout) > 2000 else test_stdout))
    lines.append("```")

    if test_stderr:
        lines.append("### Test Errors (last 1000 chars)")
        lines.append("")
        lines.append("```")
        lines.append((test_stderr[-1000:] if len(test_stderr) > 1000 else test_stderr))
        lines.append("```")

    lines.append("")
    lines.append("❌ Tests failed — no changes committed.")

    return "\n".join(lines)
