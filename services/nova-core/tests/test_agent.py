import asyncio

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
        mock_run.assert_called_once_with("Hello", user="Meral", history=[], channel="api")
        mock_run.reset_mock()
        
        # 2. Body user specified, no query parameter
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}], "user": "Ruben"}
        )
        assert resp.status_code == 200
        mock_run.assert_called_once_with("Hello", user="Ruben", history=[], channel="api")
        mock_run.reset_mock()
        
        # 3. No user specified
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]}
        )
        assert resp.status_code == 200
        mock_run.assert_called_once_with("Hello", user="household", history=[], channel="api")


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


@pytest.mark.asyncio
async def test_per_iteration_timing_captured():
    """Verify per-iteration timing is collected for LLM and tool calls."""
    try:
        @tool(
            name="test_timing_tool",
            description="Timing test tool.",
            parameters={
                "type": "object",
                "properties": {"val": {"type": "string"}},
                "required": ["val"],
            }
        )
        async def timing_tool(val: str) -> str:
            return "done"

        mock_turn1 = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "type": "function", "id": "call_1",
                "function": {"name": "test_timing_tool", "arguments": '{"val": "x"}'}
            }]
        }
        mock_turn2 = {"role": "assistant", "content": "Done!"}

        with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat, \
             patch("app.agent.get_user_memories", new_callable=AsyncMock) as mock_mem, \
             patch("app.agent.push_progress", new_callable=AsyncMock) as mock_push, \
             patch("app.agent.insert_agent_traces", new_callable=AsyncMock) as mock_insert, \
             patch("app.agent.check_and_alert_slowness", new_callable=AsyncMock) as mock_check:
            mock_mem.return_value = ""
            mock_chat.side_effect = [
                ChatResult(message=mock_turn1, prompt_tokens=50, completion_tokens=20),
                ChatResult(message=mock_turn2, prompt_tokens=30, completion_tokens=10),
            ]
            resp = await run_agent("timing test", user="Ruben")
            assert resp == "Done!"

            # Allow fire-and-forget tasks to complete
            await asyncio.sleep(0)

            # Verify push_progress was called for llm and tool steps
            llm_calls = [c for c in mock_push.call_args_list if c[0][0] == "llm"]
            tool_calls = [c for c in mock_push.call_args_list if c[0][0] == "test_timing_tool"]
            assert len(llm_calls) >= 1, "push_progress should be called for LLM step"
            assert len(tool_calls) >= 1, "push_progress should be called for tool step"
            # elapsed_s should be a non-negative float (0 for instant mock, >0 in reality)
            assert llm_calls[0][0][1] >= 0, "LLM elapsed_s should be non-negative"

            # Verify insert_agent_traces was called with enriched trace
            assert mock_insert.called, "insert_agent_traces should be called"
            trace_arg = mock_insert.call_args[0][0]
            assert isinstance(trace_arg.turn_id, str) and trace_arg.turn_id != ""
            assert len(trace_arg.iterations) >= 1

            # Verify timing values in the iteration (0 for instant mock calls)
            it = trace_arg.iterations[0]
            assert it["iteration_num"] == 1
            assert it["llm_time_ms"] >= 0
            assert it["tool_time_ms"] >= 0
            assert it["tool_name"] == "test_timing_tool"
    finally:
        TOOLS.pop("test_timing_tool", None)


@pytest.mark.asyncio
async def test_agent_emits_progress_events():
    """Verify progress events are emitted for each step type."""
    try:
        @tool(
            name="test_progress_tool",
            description="Progress test tool.",
            parameters={
                "type": "object",
                "properties": {"val": {"type": "string"}},
                "required": ["val"],
            }
        )
        async def progress_tool(val: str) -> str:
            return "done"

        mock_turn1 = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "type": "function", "id": "call_p",
                "function": {"name": "test_progress_tool", "arguments": '{"val": "x"}'}
            }]
        }
        mock_turn2 = {"role": "assistant", "content": "Progress done"}

        with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat, \
             patch("app.agent.get_user_memories", new_callable=AsyncMock) as mock_mem, \
             patch("app.agent.push_progress", new_callable=AsyncMock) as mock_push, \
             patch("app.agent.insert_agent_traces", new_callable=AsyncMock), \
             patch("app.agent.check_and_alert_slowness", new_callable=AsyncMock):
            mock_mem.return_value = ""
            mock_chat.side_effect = [
                ChatResult(message=mock_turn1, prompt_tokens=10, completion_tokens=5),
                ChatResult(message=mock_turn2, prompt_tokens=10, completion_tokens=5),
            ]
            resp = await run_agent("progress test", user="Ruben")
            assert resp == "Progress done"
            await asyncio.sleep(0)

            # Collect all step names passed to push_progress
            step_names = [c[0][0] for c in mock_push.call_args_list]
            # Should include both "llm" and the tool name
            assert "llm" in step_names
            assert "test_progress_tool" in step_names
    finally:
        TOOLS.pop("test_progress_tool", None)


@pytest.mark.asyncio
async def test_agent_calls_insert_agent_traces_on_success():
    """Verify insert_agent_traces is called after a successful turn."""
    mock_reply = {"role": "assistant", "content": "Hello from traces test!"}

    with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat, \
         patch("app.agent.get_user_memories", new_callable=AsyncMock) as mock_mem, \
         patch("app.agent.push_progress", new_callable=AsyncMock), \
         patch("app.agent.insert_agent_traces", new_callable=AsyncMock) as mock_insert, \
         patch("app.agent.check_and_alert_slowness", new_callable=AsyncMock) as mock_check:
        mock_mem.return_value = ""
        mock_chat.return_value = ChatResult(message=mock_reply, prompt_tokens=42, completion_tokens=10)
        resp = await run_agent("insert test", user="Ruben")
        assert resp == "Hello from traces test!"
        await asyncio.sleep(0)

        # Verify insert_agent_traces was called with proper fields
        assert mock_insert.called
        trace_arg = mock_insert.call_args[0][0]
        assert trace_arg.channel == "api"
        assert trace_arg.user == "Ruben"
        assert trace_arg.turn_id != ""
        assert trace_arg.iteration_count == 1
        assert trace_arg.latency_ms >= 0
        assert trace_arg.token_count == 52  # 42 + 10
        assert len(trace_arg.iterations) == 1

        # Verify check_and_alert_slowness was also called
        assert mock_check.called

