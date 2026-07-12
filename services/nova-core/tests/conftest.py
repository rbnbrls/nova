import sys
from os.path import abspath, dirname, join

# Ensure app directory is in Python path for test execution
sys.path.insert(0, abspath(join(dirname(__file__), "..")))

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def _mock_user_memories():
    """Mock get_user_memories to avoid DB dependency in unit tests."""
    with patch("app.agent.get_user_memories", new_callable=AsyncMock) as m:
        m.return_value = ""
        yield
