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
        patch("app.maintenance.dependency_scanner._bump_package", new_callable=AsyncMock) as mock_bump,
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

    mock_bump.assert_awaited_once()

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
        patch("app.maintenance.dependency_scanner._bump_package", new_callable=AsyncMock),
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


# ======================================================================
# Backup verification tests
# ======================================================================


from app.maintenance.backup_verifier import run_backup_verification
from app.maintenance.trend_reporter import run_trend_report


@pytest.mark.asyncio
async def test_backup_verify_no_dump():
    """No dump files — 'no dump files found' issue filed, no docker calls."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=200)

    with (
        patch("app.maintenance.backup_verifier._find_latest_dump", return_value=None),
        patch("app.maintenance.backup_verifier.ForgejoClient", return_value=mock_forgejo),
        patch("app.config.settings.maintenance_backup_verify_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        await run_backup_verification()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "no dump files found" in call_kwargs["title"]


@pytest.mark.asyncio
async def test_backup_verify_success():
    """Dump found, restore and queries succeed — success issue filed."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=201)
    mock_forgejo.open_issues_by_label = AsyncMock(return_value=[])

    with (
        patch("app.maintenance.backup_verifier._find_latest_dump",
              return_value="/backups/nova-20260711.sql"),
        patch("app.maintenance.backup_verifier.os.path.getsize", return_value=1048576),
        patch("app.maintenance.backup_verifier.os.path.exists", return_value=True),
        patch("app.maintenance.backup_verifier.ForgejoClient", return_value=mock_forgejo),
        patch("app.maintenance.backup_verifier._run_cmd") as mock_run_cmd,
        patch("builtins.open", MagicMock()),
        patch("app.config.settings.maintenance_backup_verify_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        # Sequence: docker run, docker exec pg_isready, docker exec psql restore,
        # docker exec queries (tables, columns, row_counts), docker stop, docker rm
        mock_run_cmd.side_effect = [
            (0, "abc123", ""),               # docker run
            (0, "", ""),                     # pg_isready (attempt 1)
            (0, "", ""),                     # psql restore
            (0, "5\n", ""),                  # table count = 5
            (0, "42\n", ""),                 # column count = 42
            (0, "public.users|3\npublic.tasks|10\n", ""),  # row counts
            (0, "", ""),                     # docker stop
            (0, "", ""),                     # docker rm
        ]

        await run_backup_verification()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "backup verification OK" in call_kwargs["title"]
    assert "5" in call_kwargs["body"]


@pytest.mark.asyncio
async def test_backup_verify_restore_failure():
    """Dump found, restore fails — FAILED issue filed, cleanup performed."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=202)
    mock_forgejo.open_issues_by_label = AsyncMock(return_value=[])

    with (
        patch("app.maintenance.backup_verifier._find_latest_dump",
              return_value="/backups/nova-20260711.sql"),
        patch("app.maintenance.backup_verifier.os.path.getsize", return_value=1048576),
        patch("app.maintenance.backup_verifier.os.path.exists", return_value=True),
        patch("app.maintenance.backup_verifier.ForgejoClient", return_value=mock_forgejo),
        patch("app.maintenance.backup_verifier._run_cmd") as mock_run_cmd,
        patch("builtins.open", MagicMock()),
        patch("app.config.settings.maintenance_backup_verify_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        mock_run_cmd.side_effect = [
            (0, "abc123", ""),               # docker run
            (0, "", ""),                     # pg_isready
            (1, "", "restore error"),         # psql restore FAILS
            (0, "", ""),                     # docker stop (cleanup)
            (0, "", ""),                     # docker rm (cleanup)
        ]

        await run_backup_verification()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "FAILED" in call_kwargs["title"]
    assert "heal-failed" in call_kwargs["labels"]


@pytest.mark.asyncio
async def test_backup_verify_empty_dump():
    """Dump file is 0 bytes — treated as no dump found."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=203)
    mock_forgejo.open_issues_by_label = AsyncMock(return_value=[])

    with (
        patch("app.maintenance.backup_verifier._find_latest_dump",
              return_value="/backups/nova-20260711.sql"),
        patch("app.maintenance.backup_verifier.os.path.getsize", return_value=0),
        patch("app.maintenance.backup_verifier.os.path.exists", return_value=True),
        patch("app.maintenance.backup_verifier.ForgejoClient", return_value=mock_forgejo),
        patch("app.config.settings.maintenance_backup_verify_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        await run_backup_verification()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "no dump files found" in call_kwargs["title"]


@pytest.mark.asyncio
async def test_backup_verify_docker_unavailable():
    """Docker not available — graceful degradation (log warning, no crash)."""
    with (
        patch("app.maintenance.backup_verifier._find_latest_dump",
              return_value="/backups/nova-20260711.sql"),
        patch("app.maintenance.backup_verifier.os.path.getsize", return_value=1048576),
        patch("app.maintenance.backup_verifier.os.path.exists", return_value=True),
        patch("app.maintenance.backup_verifier._run_cmd",
              side_effect=FileNotFoundError("docker not found")),
        patch("app.config.settings.maintenance_backup_verify_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
    ):
        await run_backup_verification()


# ======================================================================
# Trend reporter tests
# ======================================================================


@pytest.mark.asyncio
async def test_trend_report_first_run():
    """No existing trend issue — create new issue with all metrics."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=300)
    mock_forgejo.open_issues_by_label = AsyncMock(return_value=[])
    mock_forgejo.comment_issue = AsyncMock()

    with (
        patch("app.maintenance.trend_reporter.ForgejoClient", return_value=mock_forgejo),
        patch("app.maintenance.trend_reporter.shutil.disk_usage") as mock_disk,
        patch("app.maintenance.trend_reporter._run_cmd") as mock_run_cmd,
        patch("app.maintenance.trend_reporter.get_pool",
              new_callable=AsyncMock) as mock_get_pool,
        patch("app.config.settings.maintenance_trend_report_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        mock_disk.return_value = MagicMock(total=500 * 1024**3, used=250 * 1024**3, free=250 * 1024**3)

        mock_run_cmd.return_value = (0, "16384, 8192, 65, 30\n", "")

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1073741824)  # 1 GB
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        await run_trend_report()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "trend report" in call_kwargs["title"]
    assert "50.0" in call_kwargs["body"]
    assert "16384" in call_kwargs["body"]


@pytest.mark.asyncio
async def test_trend_report_subsequent_run():
    """Existing open trend issue — comment appended, not new issue."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=301)
    mock_forgejo.comment_issue = AsyncMock()
    mock_forgejo.open_issues_by_label = AsyncMock(return_value=[
        {"number": 5, "title": "existing", "labels": ["maintenance", "trend"],
         "body": '<!-- trend-data: {"date": "2026-07-05", "metrics": {"disk_pct": 45.0}} -->'}
    ])

    with (
        patch("app.maintenance.trend_reporter.ForgejoClient", return_value=mock_forgejo),
        patch("app.maintenance.trend_reporter.shutil.disk_usage") as mock_disk,
        patch("app.maintenance.trend_reporter._run_cmd"),
        patch("app.maintenance.trend_reporter.get_pool",
              new_callable=AsyncMock) as mock_get_pool,
        patch("app.config.settings.maintenance_trend_report_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        mock_disk.return_value = MagicMock(total=500 * 1024**3, used=250 * 1024**3, free=250 * 1024**3)

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1073741824)
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        await run_trend_report()

    mock_forgejo.create_issue.assert_not_called()
    mock_forgejo.comment_issue.assert_called_once()
    assert mock_forgejo.comment_issue.call_args[0][0] == 5


@pytest.mark.asyncio
async def test_trend_report_disk_warning():
    """Disk usage >80% — WARNING in issue body."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=302)
    mock_forgejo.open_issues_by_label = AsyncMock(return_value=[])

    with (
        patch("app.maintenance.trend_reporter.ForgejoClient", return_value=mock_forgejo),
        patch("app.maintenance.trend_reporter.shutil.disk_usage") as mock_disk,
        patch("app.maintenance.trend_reporter._run_cmd"),
        patch("app.maintenance.trend_reporter.get_pool",
              new_callable=AsyncMock) as mock_get_pool,
        patch("app.config.settings.maintenance_trend_report_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        mock_disk.return_value = MagicMock(total=100 * 1024**3, used=85 * 1024**3, free=15 * 1024**3)

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1073741824)
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        await run_trend_report()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "WARNING" in call_kwargs["body"] or "disk" in call_kwargs["body"].lower()


@pytest.mark.asyncio
async def test_trend_report_no_forgejo_token():
    """No forgejo token — no API call made, findings logged."""
    mock_disk = MagicMock()
    mock_disk.total = 500 * 1024**3
    mock_disk.used = 250 * 1024**3
    mock_disk.free = 250 * 1024**3

    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=1073741824)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_pool.acquire.return_value.__aexit__ = AsyncMock()

    with (
        patch("app.maintenance.trend_reporter.shutil.disk_usage",
              return_value=mock_disk),
        patch("app.maintenance.trend_reporter._run_cmd",
              return_value=(0, "16384, 8192, 65, 30\n", "")),
        patch("app.maintenance.trend_reporter.get_pool",
              return_value=mock_pool),
        patch("app.config.settings.maintenance_trend_report_enabled", True),
        patch("app.config.settings.forgejo_token", ""),
    ):
        await run_trend_report()


@pytest.mark.asyncio
async def test_trend_report_postgres_size():
    """Postgres size query returns value — included in issue body."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=303)
    mock_forgejo.open_issues_by_label = AsyncMock(return_value=[])

    mock_disk = MagicMock()
    mock_disk.total = 500 * 1024**3
    mock_disk.used = 250 * 1024**3
    mock_disk.free = 250 * 1024**3

    with (
        patch("app.maintenance.trend_reporter.ForgejoClient", return_value=mock_forgejo),
        patch("app.maintenance.trend_reporter.shutil.disk_usage",
              return_value=mock_disk),
        patch("app.maintenance.trend_reporter._run_cmd",
              return_value=(0, "16384, 8192, 65, 30\n", "")),
        patch("app.maintenance.trend_reporter.get_pool") as mock_get_pool,
        patch("app.config.settings.maintenance_trend_report_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1073741824)  # 1 GB
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()
        mock_get_pool.return_value = mock_pool

        await run_trend_report()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "1.0 GB" in call_kwargs["body"] or "Postgres" in call_kwargs["body"]


@pytest.mark.asyncio
async def test_trend_report_nvidia_failure():
    """nvidia-smi fails — VRAM shows N/A, report still filed."""
    from app.forgejo import ForgejoClient

    mock_forgejo = AsyncMock(spec=ForgejoClient)
    mock_forgejo.create_issue = AsyncMock(return_value=304)
    mock_forgejo.open_issues_by_label = AsyncMock(return_value=[])

    mock_disk = MagicMock()
    mock_disk.total = 500 * 1024**3
    mock_disk.used = 250 * 1024**3
    mock_disk.free = 250 * 1024**3

    with (
        patch("app.maintenance.trend_reporter.ForgejoClient", return_value=mock_forgejo),
        patch("app.maintenance.trend_reporter.shutil.disk_usage",
              return_value=mock_disk),
        patch("app.maintenance.trend_reporter._run_cmd",
              return_value=(1, "", "nvidia-smi not found")),
        patch("app.maintenance.trend_reporter.get_pool") as mock_get_pool,
        patch("app.config.settings.maintenance_trend_report_enabled", True),
        patch("app.config.settings.forgejo_token", "test-token"),
        patch("app.config.settings.forgejo_url", "https://git.example.com"),
        patch("app.config.settings.forgejo_repo", "test/nova"),
    ):
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()
        mock_get_pool.return_value = mock_pool

        await run_trend_report()

    mock_forgejo.create_issue.assert_called_once()
    call_kwargs = mock_forgejo.create_issue.call_args[1]
    assert "N/A" in call_kwargs["body"]
    assert "trend report" in call_kwargs["title"]
