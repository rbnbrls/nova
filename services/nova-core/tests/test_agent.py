import pytest
from unittest.mock import AsyncMock, patch
from app.agent import run_agent
from app.llm import ChatResult
from app.tools.base import tool, TOOLS


@pytest.mark.asyncio
async def test_run_agent_no_tool_calls():
    # Test agent loop with a direct reply (no tool calls)
    mock_reply = {"role": "assistant", "content": "Hello Ruben! How can I help you?"}
    with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat, \
         patch("app.agent.get_user_memories", new_callable=AsyncMock) as mock_mem:
        mock_mem.return_value = ""
        mock_chat.return_value = ChatResult(message=mock_reply)
        resp = await run_agent("hi", user="Ruben")
        assert resp == "Hello Ruben! How can I help you?"
        mock_chat.assert_called_once()


@pytest.mark.asyncio
async def test_run_agent_with_tool_call():
    # Register a temporary tool for agent to call
    try:
        @tool(
            name="test_agent_tool",
            description="Agent test tool.",
            parameters={
                "type": "object",
                "properties": {
                    "val": {"type": "string"}
                },
                "required": ["val"]
            }
        )
        async def agent_tool(val: str) -> str:
            return f"tool_result_{val}"

        # Setup mock responses for two turns:
        # 1. First turn returns a tool call request.
        # 2. Second turn returns the final text response.
        mock_turn1 = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "type": "function",
                    "id": "call_123",
                    "function": {
                        "name": "test_agent_tool",
                        "arguments": '{"val": "hello"}'
                    }
                }
            ]
        }
        mock_turn2 = {
            "role": "assistant",
            "content": "All done!"
        }

        with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat, \
             patch("app.agent.get_user_memories", new_callable=AsyncMock) as mock_mem:
            mock_mem.return_value = ""
            mock_chat.side_effect = [ChatResult(message=mock_turn1), ChatResult(message=mock_turn2)]
            resp = await run_agent("run the tool", user="Ruben")
            assert resp == "All done!"
            assert mock_chat.call_count == 2

    finally:
        TOOLS.pop("test_agent_tool", None)


def test_chat_completions_user_query_parameter():
    from fastapi.testclient import TestClient
    from app.main import app
    from unittest.mock import AsyncMock, patch

    client = TestClient(app)
    
    # Mock run_agent to capture user
    with patch("app.main.run_agent", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "Mocked reply"
        
        # 1. Query parameter specified
        resp = client.post(
            "/v1/chat/completions?user=Meral",
            json={"messages": [{"role": "user", "content": "Hello"}], "user": "Ruben"}
        )
        assert resp.status_code == 200
        mock_run.assert_called_once_with("Hello", user="Meral", history=[])
        mock_run.reset_mock()
        
        # 2. Body user specified, no query parameter
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}], "user": "Ruben"}
        )
        assert resp.status_code == 200
        mock_run.assert_called_once_with("Hello", user="Ruben", history=[])
        mock_run.reset_mock()
        
        # 3. No user specified
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]}
        )
        assert resp.status_code == 200
        mock_run.assert_called_once_with("Hello", user="household", history=[])


@pytest.mark.asyncio
async def test_run_agent_respects_iteration_budget():
    from app.config import settings

    mock_turn = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "type": "function",
                "id": "call_loop",
                "function": {
                    "name": "test_agent_tool",
                    "arguments": '{"val": "x"}'
                }
            }
        ]
    }

    try:
        @tool(
            name="test_agent_tool",
            description="Dummy tool.",
            parameters={
                "type": "object",
                "properties": {"val": {"type": "string"}},
                "required": ["val"],
            }
        )
        async def dummy_tool(val: str) -> str:
            return "done"

        original = settings.nova_max_iterations
        settings.nova_max_iterations = 3

        with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat, \
             patch("app.agent.get_user_memories", new_callable=AsyncMock) as mock_mem:
            mock_mem.return_value = ""
            mock_chat.return_value = ChatResult(message=mock_turn)
            resp = await run_agent("loop", user="Ruben")
            assert "got stuck" in resp.lower()

        settings.nova_max_iterations = original
    finally:
        TOOLS.pop("test_agent_tool", None)

