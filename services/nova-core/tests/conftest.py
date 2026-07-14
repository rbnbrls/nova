import sys
from os.path import abspath, dirname, join

# Ensure app directory is in Python path for test execution
sys.path.insert(0, abspath(join(dirname(__file__), "..")))

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def _mock_db_dependencies():
    """Mock get_user_memories and record_tool_call to avoid DB dependency in unit tests."""
    with patch("app.agent.get_user_memories", new_callable=AsyncMock) as m_mem, \
         patch("app.agent.record_tool_call", new_callable=AsyncMock) as m_audit:
        m_mem.return_value = ""
        yield


# ---------------------------------------------------------------------------
# Phase 41 — Model management test helpers
# ---------------------------------------------------------------------------

SAMPLE_MODELS = [
    {"name": "qwen3:14b", "size": 1234567890, "details": {"parameter_size": "14.7B", "quantization_level": "Q4_K_M"}},
    {"name": "gemma4:12b", "size": 987654321, "details": {"parameter_size": "12.2B", "quantization_level": "Q4_K_M"}},
]


@pytest.fixture
def ollama_mock():
    """Mock the admin_models module used in main.py for model management tests."""
    with patch("app.main.admin_models.list_models", new_callable=AsyncMock) as list_mock, \
         patch("app.main.admin_models.delete_model", new_callable=AsyncMock) as del_mock, \
         patch("app.main.admin_models.load_model", new_callable=AsyncMock) as load_mock, \
         patch("app.main.admin_models.get_all_pull_tasks", new_callable=AsyncMock) as pulls_mock, \
         patch("app.main.admin_models.get_pull_status", new_callable=AsyncMock) as ps_mock:
        list_mock.return_value = SAMPLE_MODELS
        del_mock.return_value = {"status": "deleted"}
        load_mock.return_value = True
        pulls_mock.return_value = []
        ps_mock.return_value = None
        yield {"list": list_mock, "delete": del_mock, "load": load_mock, "pulls": pulls_mock, "pull_status": ps_mock}
