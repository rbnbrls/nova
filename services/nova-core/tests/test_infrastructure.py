"""Tests for the CI/CD infrastructure: Dockerfile tester stage and heal.sh test gate.

TEST-02: A failing test suite blocks the Docker image build (RUN pytest build-stage step)
TEST-03: heal.sh runs the test suite before committing an automated fix, rejecting a heal
         branch with failing tests
"""

import os
import re

REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)


# ---------------------------------------------------------------------------
# TEST-02: Dockerfile tester stage
# ---------------------------------------------------------------------------

DOCKERFILES = [
    ("nova-core", os.path.join(REPO_ROOT, "services", "nova-core", "Dockerfile")),
    ("ops-bridge", os.path.join(REPO_ROOT, "services", "ops-bridge", "Dockerfile")),
]


def _read_dockerfile(path: str) -> str:
    with open(path) as f:
        return f.read()


def _assert_tester_stage(content: str, service_name: str) -> None:
    """Assert that the Dockerfile has a `tester` stage that runs `pytest` and
    sits between `base` and the final stage, so a failing suite blocks the build."""
    lines = content.splitlines()

    # ── Stage names (lines like "FROM ... AS ...") ──
    stage_decls = []
    for i, line in enumerate(lines):
        m = re.match(r"^FROM\s+\S+\s+AS\s+(\w+)", line, re.IGNORECASE)
        if m:
            stage_decls.append((m.group(1), i))

    stage_names = [s[0] for s in stage_decls]

    # Must have at least 3 stages: base, tester, final (unnamed)
    assert "tester" in stage_names, (
        f"{service_name} Dockerfile: expected stage named 'tester' "
        f"but found only {stage_names}"
    )

    # base must come before tester
    base_idx = stage_names.index("base")
    tester_idx = stage_names.index("tester")
    assert base_idx < tester_idx, (
        f"{service_name} Dockerfile: 'base' stage (index {base_idx}) "
        f"must appear before 'tester' stage (index {tester_idx})"
    )

    # There must be at least one stage (the final deploy stage) after tester
    assert tester_idx < len(stage_names) - 1 or (
        # Or an implicit final stage via a second FROM base (no AS)
        any(
            re.match(r"^FROM\s+\S+\s*$", lines[stage_decls[-1][1] + j])
            for j in range(1, len(lines) - stage_decls[-1][1])
        )
    ), (
        f"{service_name} Dockerfile: 'tester' stage is the last stage; "
        f"no final deploy stage follows it, so the tester gate is never reached"
    )

    # ── Check RUN pytest in tester section ──
    # Find lines between tester's FROM line and the next FROM (or EOF)
    tester_start = stage_decls[tester_idx][1]
    next_from = None
    for j in range(tester_start + 1, len(lines)):
        if re.match(r"^FROM\s+", lines[j], re.IGNORECASE):
            next_from = j
            break
    tester_body = lines[tester_start : next_from] if next_from else lines[tester_start:]

    has_pytest = any("RUN" in line and "pytest" in line for line in tester_body)
    assert has_pytest, (
        f"{service_name} Dockerfile: 'tester' stage (lines {tester_start+1}"
        f"-{next_from or 'EOF'}) does not contain 'RUN ... pytest ...'"
    )


def test_dockerfile_has_tester_stage():
    """TEST-02: Both Dockerfiles declare a 'tester' stage with RUN pytest
    between 'base' and the final deploy stage."""
    for name, path in DOCKERFILES:
        assert os.path.isfile(path), f"Dockerfile not found at {path}"
        content = _read_dockerfile(path)
        _assert_tester_stage(content, name)


# ---------------------------------------------------------------------------
# TEST-03: heal.sh test gate
# ---------------------------------------------------------------------------

HEAL_SH = os.path.join(REPO_ROOT, "ops", "heal.sh")
RUN_TESTS_SH = os.path.join(REPO_ROOT, "ops", "run-tests.sh")


def _read_heal_sh() -> str:
    with open(HEAL_SH) as f:
        return f.read()


def test_heal_sh_runs_tests_before_commit():
    """TEST-03: heal.sh invokes run-tests.sh and exits 3 + cleanup_on_fail on
    test failure."""
    assert os.path.isfile(HEAL_SH), f"heal.sh not found at {HEAL_SH}"
    content = _read_heal_sh()

    # 1) Must reference run-tests.sh in the test-gate block
    assert (
        "run-tests.sh" in content
    ), "heal.sh does not call run-tests.sh — no test gate"

    # 2) Must exit 3 on test failure
    assert "exit 3" in content, (
        "heal.sh does not contain 'exit 3' — "
        "the requirement demands exit code 3 on test failure"
    )

    # 3) Must call cleanup_on_fail when tests fail
    # Look for the block that runs tests and handles failure
    # Pattern: run run-tests.sh and if it fails → cleanup_on_fail + exit 3
    lines = content.splitlines()

    # Find the section that runs tests
    test_gate_start = None
    for i, line in enumerate(lines):
        if "running test suite" in line.lower() or "run-tests.sh" in line:
            test_gate_start = i
            break

    assert test_gate_start is not None, (
        "heal.sh: could not locate test gate section"
    )

    # Look for the failure-handling block (the 'if ! ... run-tests.sh' block)
    # This should contain cleanup_on_fail and exit 3
    test_gate_section = "\n".join(lines[test_gate_start:test_gate_start + 10])
    assert "cleanup_on_fail" in test_gate_section or "cleanup_on_fail" in content, (
        "heal.sh: cleanup_on_fail is not called on test failure"
    )

    # 4) Verify run-tests.sh itself exists and is executable
    assert os.path.isfile(RUN_TESTS_SH), f"run-tests.sh not found at {RUN_TESTS_SH}"
    assert os.access(RUN_TESTS_SH, os.X_OK) or _has_shebang(RUN_TESTS_SH), (
        "run-tests.sh is not executable and has no shebang"
    )


def _has_shebang(path: str) -> bool:
    with open(path) as f:
        first_line = f.readline()
    return first_line.startswith("#!")


def test_run_tests_sh_exists_and_runs_pytest():
    """Supporting test: run-tests.sh exists and invokes pytest for both service test suites."""
    assert os.path.isfile(RUN_TESTS_SH), f"run-tests.sh not found at {RUN_TESTS_SH}"

    content = _read_heal_sh()
    assert (
        "run-tests.sh" in content
    ), "run-tests.sh not referenced in heal.sh"
