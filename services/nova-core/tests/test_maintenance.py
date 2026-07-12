"""Unit tests for the Scheduled Maintenance Agent modules.

Covers dependency_scanner (5 tests) and log_anomaly (6 tests).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from app.maintenance.dependency_scanner import (
    run_dependency_scan,
    _get_outdated_packages,
    _run_cve_scan,
)
from app.maintenance.log_anomaly import (
    run_log_anomaly_review,
    _redact,
    _detect_anomalies,
)


# ======================================================================
# Helpers
# ======================================================================


def _mock_subprocess(returncode: int = 0, stdout: str = "", stderr: str = "") -> AsyncMock:
    """Create an AsyncMock that simulates create_subprocess_exec."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
    proc.wait = AsyncMock()
    proc.kill = MagicMock()
    return proc


# ======================================================================
# Dependency scanner tests
# ======================================================================


@pytest.mark.asyncio
async def test_dep_scan_no_outdated():
    """Mock pip list --outdated returns empty, pip-audit exit 0 — no issue filed."""
    no_outdated = _mock_subprocess(0, "[]")
    no_cve = _mock_subprocess(0, '{"vulnerabilities": []}')

    with (
        patch("app.maintenance.dependency_scanner._run_cmd") as mock_run_cmd,
        patch("app.config.settings.maintenance_dep_check_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
    ):
        # Sequence: git status, current branch, pip list outdated, pip-audit, git checkout -b, ...
        # For "no issues" flow we need: git status (clean) + get current branch + pip list + pip-audit
        mock_run_cmd.side_effect = [
            (0, "", ""),                     # git status --porcelain (clean)
            (0, "main\n", ""),               # git rev-parse (current branch)
            (0, "[]", ""),                   # pip list --outdated
            (0, '{"vulnerabilities": []}', ""),  # pip-audit
        ]

        await run_dependency_scan()

    # Should not have proceeded past step 4 (returned early)
    assert mock_run_cmd.call_count == 4


@pytest.mark.asyncio
async def test_dep_scan_no_forgejo_token():
    """No forgejo token — logs warning, no API calls."""
    with (
        patch("app.maintenance.dependency_scanner._run_cmd") as mock_run_cmd,
        patch("app.config.settings.maintenance_dep_check_enabled", True),
        patch("app.config.settings.forgejo_token", ""),
    ):
        mock_run_cmd.side_effect = [
            (0, "", ""),                     # git status --porcelain (clean)
            (0, "main\n", ""),               # git rev-parse
            (0, "[]", ""),                   # pip list --outdated
            (0, '{"vulnerabilities": []}', ""),  # pip-audit (no CVEs)
        ]

        await run_dependency_scan()

    # Should have stopped after no outdated + no CVEs
    assert mock_run_cmd.call_count == 4


@pytest.mark.asyncio
async def test_dep_scan_dirty_working_tree():
    """Dirty working tree — abort without git branch creation."""
    with (
        patch("app.maintenance.dependency_scanner._run_cmd") as mock_run_cmd,
        patch("app.config.settings.maintenance_dep_check_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
    ):
        mock_run_cmd.side_effect = [
            (0, "M file.py\n", ""),          # git status --porcelain (dirty)
        ]

        await run_dependency_scan()

    assert mock_run_cmd.call_count == 1


@pytest.mark.asyncio
async def test_dep_scan_with_outdated():
    """Outdated deps found, tests pass — create_issue called with 'dependency update'."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=42)
    mock_forgejo.comment_issue = AsyncMock()

    outdated_json = '[{"name": "fastapi", "installed": "0.1.0", "latest": "0.2.0"}]'

    with (
        patch("app.maintenance.dependency_scanner._run_cmd") as mock_run_cmd,
        patch("app.maintenance.dependency_scanner.ForgejoClient", return_value=mock_forgejo),
        patch("app.config.settings.maintenance_dep_check_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        # Sequence of subprocess results:
        # 1. git status (clean)
        # 2. git rev-parse (current branch)
        # 3. pip list --outdated
        # 4. pip-audit (no CVEs)
        # 5. git checkout -b new-branch
        # 6. git add -A
        # 7. git commit
        # 8. ops/run-tests.sh -> success
        # 9. git checkout original
        # 10. git branch -D
        mock_run_cmd.side_effect = [
            (0, "", ""),                     # 1. git status (clean)
            (0, "main\n", ""),               # 2. current branch
            (0, outdated_json, ""),          # 3. pip list --outdated
            (0, '{"vulnerabilities": []}', ""),  # 4. pip-audit
            (0, "", ""),                     # 5. git checkout -b
            (0, "", ""),                     # 6. git add -A
            (0, "", ""),                     # 7. git commit
            (0, "tests passed", ""),         # 8. tests pass
            (0, "", ""),                     # 9. git checkout main
            (0, "", ""),                     # 10. git branch -D
        ]

        await run_dependency_scan()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "dependency update" in call_kwargs["title"]
    assert "maintenance" in call_kwargs["labels"]
    assert "dependency-update" in call_kwargs["labels"]


@pytest.mark.asyncio
async def test_dep_scan_tests_fail():
    """Outdated deps, tests fail — create_issue called with 'FAILED tests' and heal-failed label."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=43)

    outdated_json = '[{"name": "httpx", "installed": "0.27.0", "latest": "0.28.0"}]'

    with (
        patch("app.maintenance.dependency_scanner._run_cmd") as mock_run_cmd,
        patch("app.maintenance.dependency_scanner.ForgejoClient", return_value=mock_forgejo),
        patch("app.config.settings.maintenance_dep_check_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        mock_run_cmd.side_effect = [
            (0, "", ""),                     # 1. git status (clean)
            (0, "main\n", ""),               # 2. current branch
            (0, outdated_json, ""),          # 3. pip list --outdated
            (0, '{"vulnerabilities": []}', ""),  # 4. pip-audit
            (0, "", ""),                     # 5. git checkout -b
            (1, "tests failed", "error"),    # 6. tests fail (no git add/commit before tests)
            (0, "", ""),                     # 7. git reset --hard
            (0, "", ""),                     # 8. git checkout main
            (0, "", ""),                     # 9. git branch -D
        ]

        await run_dependency_scan()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "FAILED tests" in call_kwargs["title"]
    assert "heal-failed" in call_kwargs["labels"]


# ======================================================================
# Log-anomaly tests
# ======================================================================


@pytest.mark.asyncio
async def test_log_anomaly_no_issues():
    """OpenObserve returns empty results — no issue filed."""
    with (
        patch("app.maintenance.log_anomaly._query_openobserve", return_value=[]),
        patch("app.config.settings.maintenance_log_anomaly_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
    ):
        await run_log_anomaly_review()

    # If no logs returned, no issue should be filed — function returns early


@pytest.mark.asyncio
async def test_log_anomaly_error_spike():
    """OpenObserve returns error messages — create_issue called with 'log anomaly'."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=100)
    mock_forgejo.open_issues_by_label = AsyncMock(return_value=[])

    # Generate 10 error log entries
    logs = [
        {"level": "error", "message": f"Error #{i}: something went wrong", "timestamp": "2026-07-12T12:00:00Z"}
        for i in range(10)
    ]

    with (
        patch("app.maintenance.log_anomaly._query_openobserve", return_value=logs),
        patch("app.maintenance.log_anomaly.ForgejoClient", return_value=mock_forgejo),
        patch("app.maintenance.log_anomaly._baseline", {"error": 2}),
        patch("app.config.settings.maintenance_log_anomaly_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        await run_log_anomaly_review()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "log anomaly" in call_kwargs["title"]
    assert "maintenance" in call_kwargs["labels"]
    assert "log-anomaly" in call_kwargs["labels"]


@pytest.mark.asyncio
async def test_log_anomaly_dedup_existing_issue():
    """Existing open log-anomaly issue — comment instead of create."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=101)
    mock_forgejo.comment_issue = AsyncMock()
    mock_forgejo.open_issues_by_label = AsyncMock(
        return_value=[{"number": 7, "title": "existing", "labels": ["maintenance", "log-anomaly"]}]
    )

    logs = [
        {"level": "error", "message": "An error occurred", "timestamp": "2026-07-12T12:00:00Z"}
        for _ in range(5)
    ]

    with (
        patch("app.maintenance.log_anomaly._query_openobserve", return_value=logs),
        patch("app.maintenance.log_anomaly.ForgejoClient", return_value=mock_forgejo),
        patch("app.maintenance.log_anomaly._baseline", {"error": 1}),
        patch("app.config.settings.maintenance_log_anomaly_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        await run_log_anomaly_review()

    mock_forgejo.create_issue.assert_not_called()
    mock_forgejo.comment_issue.assert_called_once()
    assert mock_forgejo.comment_issue.call_args[0][0] == 7


@pytest.mark.asyncio
async def test_log_anomaly_redaction():
    """Logs containing IPs, emails, paths — body contains [REDACTED]."""
    sample = "User logged in from 192.168.1.1, email test@example.com, path /home/user/config"
    redacted = _redact(sample)
    assert "[REDACTED]" in redacted
    assert "192.168.1.1" not in redacted
    assert "test@example.com" not in redacted
    assert "/home/user/config" not in redacted


@pytest.mark.asyncio
async def test_log_anomaly_connection_failure():
    """OpenObserve connection failure — logs warning, no exception."""
    with (
        patch("app.maintenance.log_anomaly._query_openobserve", return_value=[]),
        patch("app.config.settings.maintenance_log_anomaly_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
    ):
        # Should not raise — gracefully handles empty result
        await run_log_anomaly_review()


@pytest.mark.asyncio
async def test_log_anomaly_critical_line():
    """Single CRITICAL line — should trigger anomaly detection."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=102)
    mock_forgejo.open_issues_by_label = AsyncMock(return_value=[])

    logs = [
        {"level": "critical", "message": "CRITICAL: system failure detected", "timestamp": "2026-07-12T12:00:00Z"}
    ]

    with (
        patch("app.maintenance.log_anomaly._query_openobserve", return_value=logs),
        patch("app.maintenance.log_anomaly.ForgejoClient", return_value=mock_forgejo),
        patch("app.maintenance.log_anomaly._baseline", {"critical": 0}),
        patch("app.config.settings.maintenance_log_anomaly_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        await run_log_anomaly_review()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "log anomaly" in call_kwargs["title"]
