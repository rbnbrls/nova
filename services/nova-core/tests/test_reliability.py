from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock, call
import httpx
import pytest
from fastapi.testclient import TestClient

from app import llm
from app.agent import run_agent, _truncate_history
from app.config import settings
from app.main import app


@pytest.mark.asyncio
async def test_llm_chat_retry_on_5xx_success():
    mock_response_500 = MagicMock(spec=httpx.Response)
    mock_response_500.status_code = 500
    mock_response_500.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error",
        request=MagicMock(),
        response=mock_response_500
    )

    mock_response_200 = MagicMock(spec=httpx.Response)
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {"message": {"role": "assistant", "content": "Success!"}}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.side_effect = [
        mock_response_500,
        mock_response_500,
        mock_response_200
    ]

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        
        res = await llm.chat([{"role": "user", "content": "hello"}])
        assert res.message["content"] == "Success!"
        assert mock_client.post.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_has_calls([call(1), call(2)])


@pytest.mark.asyncio
async def test_llm_chat_retry_on_request_error_success():
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    
    mock_response_200 = MagicMock(spec=httpx.Response)
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {"message": {"role": "assistant", "content": "Success!"}}

    mock_client.post.side_effect = [
        httpx.RequestError("Connection failed"),
        mock_response_200
    ]

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        
        res = await llm.chat([{"role": "user", "content": "hello"}])
        assert res.message["content"] == "Success!"
        assert mock_client.post.call_count == 2
        mock_sleep.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_llm_chat_retry_exhausted():
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.side_effect = httpx.RequestError("Connection failed")

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        
        with pytest.raises(httpx.RequestError):
            await llm.chat([{"role": "user", "content": "hello"}])
        assert mock_client.post.call_count == 3
        assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_llm_chat_no_retry_on_4xx():
    mock_response_400 = MagicMock(spec=httpx.Response)
    mock_response_400.status_code = 400
    mock_response_400.raise_for_status.side_effect = httpx.HTTPStatusError(
        "400 Bad Request",
        request=MagicMock(),
        response=mock_response_400
    )

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response_400

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        
        with pytest.raises(httpx.HTTPStatusError):
            await llm.chat([{"role": "user", "content": "hello"}])
        assert mock_client.post.call_count == 1
        mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_llm_chat_logs_retry_warning():
    """Retry logging emits a warning with attempt number and delay for each retry."""
    mock_response_500 = MagicMock(spec=httpx.Response)
    mock_response_500.status_code = 500
    mock_response_500.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error",
        request=MagicMock(),
        response=mock_response_500
    )

    mock_response_200 = MagicMock(spec=httpx.Response)
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {"message": {"role": "assistant", "content": "OK!"}}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.side_effect = [
        mock_response_500,
        mock_response_500,
        mock_response_200,
    ]

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("asyncio.sleep", new_callable=AsyncMock), \
         patch("app.llm.log.warning") as mock_warning:

        res = await llm.chat([{"role": "user", "content": "hello"}])
        assert res.message["content"] == "OK!"
        assert mock_warning.call_count == 2

        # Each call should include attempt number and delay
        first_args = mock_warning.call_args_list[0][0]
        second_args = mock_warning.call_args_list[1][0]
        # Format string: first arg; second positional arg = attempt + 1, third = max_retries, last = delay
        assert first_args[1] == 1  # attempt 1/3
        assert first_args[2] == 3
        assert first_args[-1] == 1  # delay 1s
        assert second_args[1] == 2  # attempt 2/3
        assert second_args[2] == 3
        assert second_args[-1] == 2  # delay 2s


def test_friendly_fallback_on_unhandled_exception():
    client = TestClient(app)
    with patch("app.main.run_agent", side_effect=ValueError("Ollama crashed")):
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}], "user": "Ruben"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"] == "Nova is having trouble right now, please try again later."


@pytest.mark.asyncio
async def test_agent_turn_timeout():
    with patch("app.llm.chat", side_effect=TimeoutError()), \
         patch("app.agent.get_user_memories", new_callable=AsyncMock) as mock_mem:
        mock_mem.return_value = ""
        resp = await run_agent("hello", user="Ruben")
        assert resp == "Sorry, I took too long to think about that. Could you try again?"


@pytest.mark.asyncio
async def test_agent_uses_configurable_timeout():
    """Configurable timeout is honoured: setting a tiny value triggers the
    friendly fallback instead of the hardcoded 60s budget."""
    original = settings.nova_max_turn_timeout
    settings.nova_max_turn_timeout = 0.001

    async def slow_chat(*args, **kwargs):
        await asyncio.sleep(10)
        return {"role": "assistant", "content": "too late"}

    try:
        with patch("app.llm.chat", side_effect=slow_chat), \
             patch("app.agent.get_user_memories", new_callable=AsyncMock) as mock_mem:
            mock_mem.return_value = ""
            resp = await run_agent("hello", user="Ruben")
            assert resp == "Sorry, I took too long to think about that. Could you try again?"
    finally:
        settings.nova_max_turn_timeout = original


@pytest.mark.asyncio
async def test_agent_max_iterations_fallback():
    mock_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "type": "function",
                "id": "call_1",
                "function": {
                    "name": "non_existent_tool",
                    "arguments": "{}"
                }
            }
        ]
    }
    from app.llm import ChatResult
    with patch("app.llm.chat", new_callable=AsyncMock) as mock_chat, \
         patch("app.tools.call_tool", new_callable=AsyncMock) as mock_call_tool, \
         patch("app.agent.get_user_memories", new_callable=AsyncMock) as mock_mem:
        mock_mem.return_value = ""
        mock_chat.return_value = ChatResult(message=mock_reply)
        mock_call_tool.return_value = "error: tool not found"
        
        resp = await run_agent("hello", user="Ruben")
        assert resp == "Sorry, I got stuck working on that — could you rephrase?"
        assert mock_chat.call_count == 6


def test_truncate_history():
    # 1. History shorter than max is untouched
    history_short = [{"role": "user", "content": "hi"}] * 10
    assert _truncate_history(history_short, max_messages=20) == history_short

    # 2. History longer than max is truncated
    history_long = [{"role": "user", "content": f"msg {i}"} for i in range(25)]
    truncated = _truncate_history(history_long, max_messages=20)
    assert len(truncated) == 20
    assert truncated[0]["content"] == "msg 5"

    # 3. Truncation shifts back to not cut off a tool reply from its assistant message
    history = [{"role": "user", "content": f"msg {i}"} for i in range(25)]
    history[4] = {"role": "assistant", "content": "calling tool", "tool_calls": []}
    history[5] = {"role": "tool", "content": "tool result"}
    
    truncated = _truncate_history(history, max_messages=20)
    assert len(truncated) == 21
    assert truncated[0]["role"] == "assistant"
    assert truncated[1]["role"] == "tool"
