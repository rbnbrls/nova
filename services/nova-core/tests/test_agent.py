import pytest
from unittest.mock import AsyncMock, patch
from app.agent import run_agent
from app.tools.base import tool, TOOLS


@pytest.mark.asyncio
async def test_run_agent_no_tool_calls():
    # Test agent loop with a direct reply (no tool calls)
    mock_reply = {"role": "assistant", "content": "Hello Ruben! How can I help you?"}
    with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_reply
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

        with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.side_effect = [mock_turn1, mock_turn2]
            resp = await run_agent("run the tool", user="Ruben")
            assert resp == "All done!"
            assert mock_chat.call_count == 2

    finally:
        TOOLS.pop("test_agent_tool", None)
