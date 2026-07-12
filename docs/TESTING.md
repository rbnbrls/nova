<!-- generated-by: gsd-doc-writer -->

# Testing

## Test framework and setup

Nova uses [pytest](https://docs.pytest.org/) with [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
for all test suites. Async mode is set to `"auto"` in `pyproject.toml`, so `async def` test functions
are automatically detected and scheduled on the event loop.

Both `nova-core` and `ops-bridge` have their own test directories with separate conftest files.
No additional global test setup is required — [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
is used for all external dependency isolation (database, Ollama, HTTP clients), so tests run
without any running services.

Configuration is in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["services/nova-core/tests", "services/ops-bridge/tests"]
```

Test dependencies (`pytest`, `pytest-asyncio`) are not committed to the per-service `requirements.txt`
files. The `ops/run-tests.sh` script installs them into a dedicated test virtualenv
(`.venv-tests/`), keeping runtime dependencies separate from test tooling.

## Running tests

### Full suite (all services + lint + type check)

```bash
ops/run-tests.sh
```

This script:
1. Creates or reuses a test virtualenv at `.venv-tests/` (using Python 3.13 if available, otherwise `python3`).
2. Installs runtime dependencies from both `services/nova-core/requirements.txt` and `services/ops-bridge/requirements.txt`, plus `pytest`, `pytest-asyncio`, `ruff`, and `mypy`.
3. Runs `pytest` for **nova-core** with `PYTHONPATH` set to `services/nova-core/`.
4. Runs `pytest` for **ops-bridge** with `PYTHONPATH` set to `services/ops-bridge/`.
5. Runs `ruff check` on both service directories.
6. Runs `mypy` type checking on `services/nova-core/app/` and `services/ops-bridge/app.py`.

### Run a single service's tests

```bash
# nova-core only
PYTHONPATH=services/nova-core pytest services/nova-core/tests/

# ops-bridge only
PYTHONPATH=services/ops-bridge pytest services/ops-bridge/tests/
```

### Run a specific test file or test function

```bash
# Single file
PYTHONPATH=services/nova-core pytest services/nova-core/tests/test_tasks.py

# Single test function
PYTHONPATH=services/nova-core pytest services/nova-core/tests/test_tasks.py::test_add_task_default_assignee_is_user

# Filter by keyword
PYTHONPATH=services/nova-core pytest services/nova-core/tests/ -k "calendar"
```

### Run with verbose output

```bash
PYTHONPATH=services/nova-core pytest services/nova-core/tests/ -v
```

## Writing new tests

### File naming

Test files must follow the `test_*.py` naming convention and live in the service's `tests/` directory:

- **nova-core**: `services/nova-core/tests/test_<module>.py`
- **ops-bridge**: `services/ops-bridge/tests/test_<module>.py`

Test function names use the `test_` prefix, with descriptive snake_case names
(e.g., `test_create_event_basic`, `test_webhook_missing_token`).

### Test structure

Each test service directory has a `conftest.py` that adds the service root to `sys.path`:

**nova-core** (`services/nova-core/tests/conftest.py`) also registers an autouse fixture
that mocks `app.agent.get_user_memories` to return an empty string, so no database is
needed for unit tests:

```python
@pytest.fixture(autouse=True)
def _mock_user_memories():
    with patch("app.agent.get_user_memories", new_callable=AsyncMock) as m:
        m.return_value = ""
        yield
```

### Async tests

Use `@pytest.mark.asyncio` on async test functions (or rely on `asyncio_mode = "auto"`):

```python
@pytest.mark.asyncio
async def test_run_agent_no_tool_calls():
    mock_reply = {"role": "assistant", "content": "Hello!"}
    with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = ChatResult(message=mock_reply)
        resp = await run_agent("hi", user="Ruben")
        assert resp == "Hello!"
```

### Tool tests

When testing `@tool`-decorated functions, use try/finally blocks to clean up the global
`TOOLS` registry:

```python
@pytest.mark.asyncio
async def test_my_tool():
    try:
        @tool(name="test_tmp", ...)
        async def tmp_func(val: str) -> str:
            return f"result_{val}"
        # ... test body ...
    finally:
        TOOLS.pop("test_tmp", None)
```

### Mocking patterns

- **Database**: Mock `asyncpg.Pool` with `unittest.mock.MagicMock` and `AsyncMock` for `acquire().fetchrow()`.
- **Ollama/LLM**: Patch `app.llm.chat` with `AsyncMock` returning a `ChatResult` struct.
- **HTTP clients**: Use `unittest.mock.patch` on `httpx.AsyncClient`.
- **External APIs**: Mock at the transport layer (e.g., `httpx.AsyncClient.post`) rather than
  the Nova wrapper functions, so the full call chain is exercised.

## Coverage requirements

No coverage thresholds are currently configured. The project does not use `pytest-cov` or
similar coverage tooling. Coverage enforcement happens structurally through two gates:

1. **Dockerfile tester stage** — Both Dockerfiles (`services/nova-core/Dockerfile` and
   `services/ops-bridge/Dockerfile`) include a multi-stage build with a `tester` stage that
   runs `pytest`. A failing test suite blocks the Docker image build entirely.

2. **heal.sh test gate** — The `ops/heal.sh` script (autonomous incident fixing) runs the
   full test suite via `ops/run-tests.sh` before accepting any automated fix. If tests fail
   on the heal branch, the fix is rejected and the heal branch is deleted.

## CI integration

Nova does not use GitHub Actions or an external CI service. Testing is integrated directly
into the deployment pipeline:

| Gate | Where | What runs | Effect on failure |
|---|---|---|---|
| **Docker build** | `services/*/Dockerfile` tester stage | `pytest` for that service | Image build fails; deployment blocked |
| **run-tests.sh** | `ops/run-tests.sh` | `pytest` + `ruff` + `mypy` for all services | Script exits non-zero |
| **heal.sh** | `ops/heal.sh` line 81 | `ops/run-tests.sh` full suite | Fix rejected; heal branch deleted |
| **pipeline.sh** | `ops/pipeline.sh` | Deploy → observe → triage loop | Triggers heal attempt (up to `HEAL_MAX_ATTEMPTS`) |

The closed-loop pipeline design: `ops/pipeline.sh` deploys, `ops/observe.sh` verifies health,
and on failure files a Forgejo issue tagged `auto-heal`. `ops/triage.sh` picks it up and invokes
`ops/heal.sh`, which runs the test suite after applying a fix. Only passing tests allow the fix
to land.
