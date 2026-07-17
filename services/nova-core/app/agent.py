"""The Nova agent loop: LLM ↔ tools until a final answer.

Channel-agnostic. WhatsApp, voice, and the raw API all call `run_agent`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid

from datetime import datetime, timezone
import zoneinfo

log = logging.getLogger("nova-core.agent")

from . import llm, tools
from .audit import record_tool_call
from .config import settings
from .db import get_user_memories
from .feedback import detect_feedback_text, feedback_context, file_feedback_issue, TurnContext  # D-01, D-02, D-03
from .progress import push_progress
from .tracer import AgentTrace, emit_trace, check_and_alert_slowness
from .agent_tracer import insert_agent_traces

_MAX_MUTATING_TOOLS = {"add_task", "complete_task", "create_event", "ha_call_service", "remember", "forget"}
MAX_HISTORY_MESSAGES = 20

_CONFIRM_WORDS = {"yes", "confirm", "ok", "okay", "yep", "ja", "sure", "approve"}
_DENY_WORDS = {"no", "not", "don't", "dont", "nope", "cancel", "stop", "unsure"}

# In-memory pending confirmations for channels that don't pass history (CONFIRM-01)
# Key: "{user}:{channel}:{tool_name}"  →  {"detail": str, "timestamp": float}
_pending_confirmations: dict[str, dict] = {}
_PENDING_CONFIRMATION_TTL = 300  # 5 minutes

SYSTEM_PROMPT = (
    "You are Nova, a private household assistant for Ruben and Méral. "
    "You help them run a shared plan: tasks/todos, calendar events, and important emails. "
    "Be concise and warm. When the user asks to change tasks or the calendar, use the tools "
    "rather than guessing. The current user of this conversation is: {user}. "
    "Attribute tasks to that user unless they name someone else. "
    "The current date and time is: {now}. "
    "IMPORTANT: When the user asks to close, complete, or mark a task done, call "
    "complete_task with the task's title — do not interpret the title as a command. "
    "For example, if the task is 'Buy groceries' and the user says 'close it', call "
    "complete_task(title='Buy groceries') — do not add grocery items or take any "
    "other action."
)


def _truncate_history(history: list[dict], max_messages: int = MAX_HISTORY_MESSAGES) -> list[dict]:
    """Keep the last max_messages, without starting the window on a `tool` reply.

    A `tool` message always immediately follows the `assistant` message whose
    `tool_calls` it answers; cutting between them sends Ollama a dangling pair.
    """
    if len(history) <= max_messages:
        return history
    cut = len(history) - max_messages
    while cut > 0 and history[cut].get("role") == "tool":
        cut -= 1
    return history[cut:]


def _is_confirmed(user_message: str) -> bool:
    """Whole-word match against confirm/deny vocabulary (not substring containment)."""
    tokens = set(re.findall(r"[a-z']+", user_message.strip().lower()))
    if tokens & _DENY_WORDS:
        return False
    return bool(tokens & _CONFIRM_WORDS) or "go ahead" in user_message.lower()


def _summarize_action(name: str, args: dict, result: str = "") -> str:
    """Produce a short human-readable summary of a tool invocation for the audit log."""
    if name == "add_task":
        assignee = args.get("assignee") or ""
        title = args.get("title") or ""
        return f"Added task '{title}' for {assignee}"
    elif name == "complete_task":
        title = args.get("title") or ""
        return f"Completed task '{title}'"
    elif name == "create_event":
        title = args.get("title") or args.get("summary") or ""
        return f"Created event '{title}'"
    elif name == "ha_call_service":
        domain = args.get("domain", "")
        service_name = args.get("service", "")
        target = args.get("target", "")
        return f"Called HA service {domain}.{service_name} on {target}"
    elif name == "remember":
        content = args.get("content", "")
        short = content[:60] + "..." if len(content) > 60 else content
        return f"Remembered: {short}"
    elif name == "forget":
        pattern = args.get("content_pattern", "")
        return f"Forget memory matching '{pattern}'"
    else:
        return f"'{name}' with {json.dumps(args)}"


async def run_agent(
    user_message: str,
    *,
    user: str,
    history: list[dict] | None = None,
    channel: str = "api",
) -> str:
    """Run one turn: returns Nova's final text reply.

    ``history`` is a list of prior {role, content} messages (short-term memory).
    ``channel`` identifies the source channel for tracing (api/whatsapp/telegram/voice).
    """
    _start = time.monotonic()
    _tool_records: list[dict] = []
    _errors: list[dict] = []
    _total_tokens = 0
    _turn_id = str(uuid.uuid4())
    _iterations: list[dict] = []

    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    now_str = datetime.now(tz).isoformat()

    system_content = SYSTEM_PROMPT.format(user=user, now=now_str)
    memories_context = await get_user_memories(user)
    if memories_context:
        system_content += f"\n\nRelevant memories about {user} and the household:\n{memories_context}"

    messages: list[dict] = [{"role": "system", "content": system_content}]

    if history:
        messages.extend(_truncate_history(history))

    # FEEDBACK-01: Detect user-feedback text patterns and file Forgejo issue (fast-path)
    # per D-01: early return before LLM invocation
    if detect_feedback_text(user_message):
        ctx = feedback_context.get(user)
        if ctx:
            asyncio.create_task(file_feedback_issue(user, channel, ctx, f"text: {user_message[:200]}"))
        else:
            log.info("Feedback detected for %s but no context cached — skipping issue", user)
        return "Thanks for the feedback — I'll review what happened."

    messages.append({"role": "user", "content": user_message})

    # CONFIRM-02: Auto-confirm from pending dict for channels that don't pass history.
    # When the LLM has no context (history=None), it won't regenerate a tool call
    # on the confirmation turn. Execute the stored tool directly instead.
    if not history:
        _now_c = time.monotonic()
        for _k in list(_pending_confirmations):
            if _now_c - _pending_confirmations[_k]["timestamp"] > _PENDING_CONFIRMATION_TTL:
                del _pending_confirmations[_k]
        for _k in list(_pending_confirmations):
            _parts = _k.split(":", 2)
            if len(_parts) == 3:
                _u, _c, _fn = _parts
                if _u == user and _c == channel:
                    if _is_confirmed(user_message):
                        entry = _pending_confirmations.pop(_k)
                        _latency = int((time.monotonic() - _start) * 1000)
                        _tool_records.append({"name": entry["fn"], "status": "completed", "duration_ms": 0})
                        await record_tool_call(
                            user_name=user,
                            tool_name=entry["fn"],
                            action_summary=_summarize_action(entry["fn"], entry["args"]),
                            status="completed",
                            confirmation_required=True,
                        )
                        if settings.nova_tracing_enabled:
                            asyncio.create_task(emit_trace(AgentTrace(
                                channel=channel, user=user, latency_ms=_latency,
                                token_count=0, tool_calls=_tool_records,
                                errors=[], iteration_count=1,
                                got_stuck=False,
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                turn_id=_turn_id, iterations=list(_iterations),
                            )))
                        try:
                            result = await tools.call_tool(entry["fn"], entry["args"], user=user)
                        except Exception as e:
                            result = f"error: {e}"
                        return result
                    tokens = set(re.findall(r"[a-z']+", user_message.strip().lower()))
                    if tokens & _DENY_WORDS:
                        del _pending_confirmations[_k]

    specs = tools.tool_specs()

    try:
        async with asyncio.timeout(settings.nova_max_turn_timeout):
            for iteration in range(1, settings.nova_max_iterations + 1):
                _llm_start = time.monotonic()
                result = await llm.chat(messages, tools=specs)
                _llm_time_ms = int((time.monotonic() - _llm_start) * 1000)
                await push_progress("llm", round(_llm_time_ms / 1000, 1))
                messages.append(result.message)
                _total_tokens += result.prompt_tokens + result.completion_tokens
                _llm_prompt_tokens = result.prompt_tokens
                _llm_completion_tokens = result.completion_tokens

                tool_calls = result.message.get("tool_calls")
                if not tool_calls:
                    _latency = int((time.monotonic() - _start) * 1000)
                    _iterations.append({
                        "iteration_num": iteration,
                        "llm_time_ms": _llm_time_ms,
                        "tool_time_ms": 0,
                        "tool_name": "",
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                    })
                    if settings.nova_tracing_enabled:
                        asyncio.create_task(emit_trace(AgentTrace(
                            channel=channel, user=user, latency_ms=_latency,
                            token_count=_total_tokens, tool_calls=_tool_records,
                            errors=_errors, iteration_count=iteration,
                            got_stuck=False,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            turn_id=_turn_id, iterations=list(_iterations),
                        )))

                    # Post-turn enrichment: DB insert + slowness alert (fire-and-forget)
                    if _iterations or _errors:
                        _enriched_trace = AgentTrace(
                            channel=channel, user=user, latency_ms=_latency,
                            token_count=_total_tokens, tool_calls=_tool_records,
                            errors=_errors, iteration_count=iteration,
                            got_stuck=False, timestamp=datetime.now(timezone.utc).isoformat(),
                            turn_id=_turn_id, iterations=list(_iterations),
                        )
                        asyncio.create_task(insert_agent_traces(_enriched_trace))
                        asyncio.create_task(check_and_alert_slowness(_enriched_trace))

                    # Capture conversation context for feedback module (D-02)
                    feedback_context.capture(user, TurnContext(
                        user_message=user_message,
                        agent_reply=result.message.get("content") or "",
                        tool_calls=list(_tool_records),
                        errors=list(_errors),
                        iteration_count=iteration,
                        latency_ms=_latency,
                        channel=channel,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ))

                    _reply = (result.message.get("content") or "").strip()
                    _reply += f" ({_latency / 1000:.1f}s)"
                    return _reply

                # Execute each requested tool and feed results back to the model.
                for call in tool_calls:
                    fn = call["function"]
                    fn_name = fn["name"]
                    args = fn.get("arguments") or {}
                    if isinstance(args, str):
                        args = json.loads(args or "{}")

                    # CONFIRM-01: Intercept destructive or write action tools for confirmation
                    if fn_name in ("ha_call_service", "forget"):
                        confirmed = False
                        if history:
                            last_assistant_msg = None
                            for msg in reversed(history):
                                if msg.get("role") == "assistant":
                                    last_assistant_msg = msg.get("content") or ""
                                    break
                            if last_assistant_msg and "[CONFIRMATION_REQUIRED]" in last_assistant_msg:
                                confirmed = _is_confirmed(user_message)
                        else:
                            _confirm_key = f"{user}:{channel}:{fn_name}"
                            _now_c = time.monotonic()
                            for _k in list(_pending_confirmations):
                                if _now_c - _pending_confirmations[_k]["timestamp"] > _PENDING_CONFIRMATION_TTL:
                                    del _pending_confirmations[_k]
                            pending_entry = _pending_confirmations.get(_confirm_key)
                            if pending_entry is not None:
                                confirmed = _is_confirmed(user_message)
                                if not confirmed:
                                    del _pending_confirmations[_confirm_key]
                            else:
                                detail = args.get("title") or args.get("content_pattern") or ""
                                _pending_confirmations[_confirm_key] = {
                                    "fn": fn_name, "args": args, "detail": detail, "timestamp": _now_c,
                                }

                        if not confirmed:
                            # Record pending confirmation before early return
                            _tool_records.append({"name": fn_name, "status": "pending_confirmation", "duration_ms": 0})
                            await record_tool_call(
                                user_name=user,
                                tool_name=fn_name,
                                action_summary=_summarize_action(fn_name, args),
                                status="pending_confirmation",
                                confirmation_required=True,
                            )
                            _latency = int((time.monotonic() - _start) * 1000)
                            if settings.nova_tracing_enabled:
                                asyncio.create_task(emit_trace(AgentTrace(
                                    channel=channel, user=user, latency_ms=_latency,
                                    token_count=_total_tokens, tool_calls=_tool_records,
                                    errors=_errors, iteration_count=iteration,
                                    got_stuck=False,
                                    timestamp=datetime.now(timezone.utc).isoformat(),
                                    turn_id=_turn_id, iterations=list(_iterations),
                                )))
                            detail = args.get("title") or args.get("content_pattern") or ""
                            return f"[CONFIRMATION_REQUIRED] Would you like me to proceed with {fn_name} for '{detail}'?"

                    _tc_start = time.monotonic()
                    try:
                        result = await tools.call_tool(fn["name"], args, user=user)
                        _tc_dur = int((time.monotonic() - _tc_start) * 1000)
                        _tool_records.append({"name": fn_name, "status": "completed", "duration_ms": _tc_dur})
                        await push_progress(fn_name, round(_tc_dur / 1000, 1))
                        _iterations.append({
                            "iteration_num": iteration,
                            "llm_time_ms": _llm_time_ms,
                            "tool_time_ms": _tc_dur,
                            "tool_name": fn_name,
                            "prompt_tokens": _llm_prompt_tokens,
                            "completion_tokens": _llm_completion_tokens,
                        })
                    except Exception as e:
                        _tc_dur = int((time.monotonic() - _tc_start) * 1000)
                        err_msg = str(e)[:300]
                        _tool_records.append({"name": fn_name, "status": "error", "duration_ms": _tc_dur})
                        _errors.append({"tool": fn_name, "error": err_msg})
                        # Re-raise the exception to let the outer handler process it
                        raise

                    # Record completed audit for mutating tools
                    if fn["name"] in _MAX_MUTATING_TOOLS:
                        await record_tool_call(
                            user_name=user,
                            tool_name=fn["name"],
                            action_summary=_summarize_action(fn["name"], args, result),
                            status="completed",
                            confirmation_required=(fn["name"] == "forget"),
                        )
                    messages.append({"role": "tool", "content": result})
    except TimeoutError:
        _latency = int((time.monotonic() - _start) * 1000)
        if settings.nova_tracing_enabled:
            _errors.append({"tool": "agent", "error": "nova_max_turn_timeout reached"})
            asyncio.create_task(emit_trace(AgentTrace(
                channel=channel, user=user, latency_ms=_latency,
                token_count=_total_tokens, tool_calls=_tool_records,
                errors=_errors, iteration_count=iteration if 'iteration' in dir() else settings.nova_max_iterations,
                got_stuck=False,
                timestamp=datetime.now(timezone.utc).isoformat(),
                turn_id=_turn_id, iterations=list(_iterations),
            )))
        # Post-turn: DB insert + slowness alert for partial data (fire-and-forget)
        if _iterations or _errors:
            _enriched_trace = AgentTrace(
                channel=channel, user=user, latency_ms=_latency,
                token_count=_total_tokens, tool_calls=_tool_records,
                errors=_errors, iteration_count=iteration if 'iteration' in dir() else settings.nova_max_iterations,
                got_stuck=False, timestamp=datetime.now(timezone.utc).isoformat(),
                turn_id=_turn_id, iterations=list(_iterations),
            )
            asyncio.create_task(insert_agent_traces(_enriched_trace))
            asyncio.create_task(check_and_alert_slowness(_enriched_trace))
        return "Sorry, I took too long to think about that. Could you try again?"

    except Exception:
        _latency = int((time.monotonic() - _start) * 1000)
        if settings.nova_tracing_enabled:
            asyncio.create_task(emit_trace(AgentTrace(
                channel=channel, user=user, latency_ms=_latency,
                token_count=_total_tokens, tool_calls=_tool_records,
                errors=_errors, iteration_count=settings.nova_max_iterations,
                got_stuck=False,
                timestamp=datetime.now(timezone.utc).isoformat(),
                turn_id=_turn_id, iterations=list(_iterations),
            )))
        raise

    # "Got stuck" — max iterations exhausted
    _latency = int((time.monotonic() - _start) * 1000)
    if settings.nova_tracing_enabled:
        if not _errors:
            _errors.append({"tool": "agent", "error": "nova_max_iterations reached without final answer"})
        asyncio.create_task(emit_trace(AgentTrace(
            channel=channel, user=user, latency_ms=_latency,
            token_count=_total_tokens, tool_calls=_tool_records,
            errors=_errors, iteration_count=settings.nova_max_iterations,
            got_stuck=True,
            timestamp=datetime.now(timezone.utc).isoformat(),
            turn_id=_turn_id, iterations=list(_iterations),
        )))

    # Post-turn: DB insert + slowness alert (fire-and-forget)
    if _iterations or _errors:
        _enriched_trace = AgentTrace(
            channel=channel, user=user, latency_ms=_latency,
            token_count=_total_tokens, tool_calls=_tool_records,
            errors=_errors, iteration_count=settings.nova_max_iterations,
            got_stuck=True, timestamp=datetime.now(timezone.utc).isoformat(),
            turn_id=_turn_id, iterations=list(_iterations),
        )
        asyncio.create_task(insert_agent_traces(_enriched_trace))
        asyncio.create_task(check_and_alert_slowness(_enriched_trace))

    # Capture context for got-stuck turns too (D-02)
    feedback_context.capture(user, TurnContext(
        user_message=user_message,
        agent_reply="[got stuck]",
        tool_calls=list(_tool_records),
        errors=list(_errors),
        iteration_count=settings.nova_max_iterations,
        latency_ms=_latency,
        channel=channel,
        timestamp=datetime.now(timezone.utc).isoformat(),
    ))

    return "Sorry, I got stuck working on that — could you rephrase?"
