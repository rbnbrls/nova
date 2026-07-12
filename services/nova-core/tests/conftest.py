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
