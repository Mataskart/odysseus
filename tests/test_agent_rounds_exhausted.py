"""Regression: stream_agent_loop emits `rounds_exhausted` only when the round
cap is hit while still working, and NOT on a normal finish.

The decision is a `for/else` in the loop: the `else` runs only if no `break`
fired (break = done / budget / error). A refactor that adds a stray break or
return, or moves the done-break, could silently flip this. See PR #1999 / #1997.
"""

import asyncio
import json

import pytest

import src.agent_loop as al


def _collect(gen):
    async def _run():
        return [c async for c in gen]
    return asyncio.run(_run())


def _types(chunks):
    out = []
    for c in chunks:
        if c.startswith("data: ") and not c.startswith("data: [DONE]"):
            try:
                out.append(json.loads(c[6:]))
            except Exception:
                pass
    return out


def _patch_common(monkeypatch):
    # Skip RAG/tool-index, MCP, and settings lookups; keep the real loop body,
    # _resolve_tool_blocks, and parse_tool_blocks.
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default, raising=False)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(al, "estimate_tokens", lambda *a, **k: 10, raising=False)

    async def _fake_exec(block, *a, **k):
        return (block.tool_type, {"output": "ok", "exit_code": 0})
    monkeypatch.setattr(al, "execute_tool_block", _fake_exec, raising=False)

    async def synthesize(**kwargs):
        return "Stopped repeating the same call."

    monkeypatch.setattr("src.llm_core.llm_call_async", synthesize)


def _run_loop(monkeypatch, round_text, max_rounds=2):
    async def _fake_stream(_candidates, messages, **kwargs):
        yield f'data: {json.dumps({"delta": round_text})}\n\n'
        yield "data: [DONE]\n\n"
    monkeypatch.setattr(al, "stream_llm_with_fallback", _fake_stream, raising=False)

    gen = al.stream_agent_loop(
        "http://x/v1", "m",
        [{"role": "user", "content": "do a long multi-step task"}],
        max_rounds=max_rounds,
        relevant_tools={"bash"},
        _is_teacher_run=True,
    )
    return _types(_collect(gen))


def test_emits_rounds_exhausted_when_cap_hit_mid_task(monkeypatch):
    _patch_common(monkeypatch)
    # Use a system-owned interaction result so this remains a loop-control test:
    # Bash output is workspace-derived and now correctly pauses for exact user
    # approval before a later Bash call.
    events = _run_loop(
        monkeypatch,
        '```update_plan\n{"plan":"- [ ] keep going"}\n```',
        max_rounds=2,
    )
    assert any(e.get("type") == "rounds_exhausted" for e in events), events


def test_no_rounds_exhausted_on_normal_finish(monkeypatch):
    _patch_common(monkeypatch)
    # A plain answer (no tool block) -> done-break on round 1 -> no event.
    events = _run_loop(monkeypatch, "All done, here is your answer.", max_rounds=2)
    assert not any(e.get("type") == "rounds_exhausted" for e in events), events


def test_emits_intent_nudge_exhausted_when_cap_is_exhausted(monkeypatch):
    _patch_common(monkeypatch)

    events = _run_loop(monkeypatch, "Let me check the logs", max_rounds=5)

    guard = next((e for e in events if e.get("type") == "intent_nudge_exhausted"), None)
    assert guard is not None, events
    assert guard["reason"] == "intent_without_action_nudge_cap"
    assert guard["nudges"] == 2


@pytest.mark.parametrize("endpoint", ["http://127.0.0.1:8000/v1", "https://example.com/v1"])
def test_prefaced_promise_retries_and_executes_the_tool(monkeypatch, endpoint):
    _patch_common(monkeypatch)
    monkeypatch.setattr(al, "blocked_tools_for_owner", lambda owner: set())
    monkeypatch.setattr(al, "_build_system_prompt", lambda messages, *a, **k: (messages, []))
    requests = []
    executed = []

    async def execute(block, *args, **kwargs):
        executed.append(block)
        return block.tool_type, {"output": "Profile loaded", "exit_code": 0}

    async def stream(candidates, messages, **kwargs):
        requests.append(list(messages))
        if len(requests) == 1:
            event = {"delta": (
                "Good idea — let me pull the relevant context before suggesting. "
                "Let me look at your user profile skill and the OpenJev repo if it's around."
            )}
        elif len(requests) == 2:
            assert any("Call the tool now" in str(m.get("content"))
                       or "DO IT NOW" in str(m.get("content")) for m in messages)
            event = {"type": "tool_calls", "calls": [{
                "name": "manage_skills",
                "arguments": json.dumps({"action": "view", "name": "user-profile"}),
            }]}
        else:
            event = {"delta": "I read your profile. Here are the suggestions."}
        yield f'data: {json.dumps(event)}\n\n'
        yield 'data: {"type": "finish_reason", "value": "stop"}\n\n'
        yield 'data: [DONE]\n\n'

    monkeypatch.setattr(al, "execute_tool_block", execute)
    monkeypatch.setattr(al, "stream_llm_with_fallback", stream)
    events = _types(_collect(al.stream_agent_loop(
        endpoint, "Qwen3.8-35B",
        [{"role": "user", "content": "Read my user-profile skill and suggest improvements."}],
        relevant_tools={"manage_skills"}, max_rounds=4, log_turns=False, _is_teacher_run=True,
    )))
    assert len(requests) == 3
    assert [block.tool_type for block in executed] == ["manage_skills"], json.dumps(events)
    assert any("I read your profile" in event.get("delta", "") for event in events)
    assert not any(event.get("type") == "rounds_exhausted" for event in events)


def test_prefaced_promise_still_stops_after_nudge_cap(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(al, "_build_system_prompt", lambda messages, *a, **k: (messages, []))
    events = _run_loop(monkeypatch, "Good idea — let me check the logs.", max_rounds=5)
    guard = next(e for e in events if e.get("type") == "intent_nudge_exhausted")
    assert guard["nudges"] == 2


def test_completed_answer_with_let_me_know_does_not_retry(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(al, "_build_system_prompt", lambda messages, *a, **k: (messages, []))
    events = _run_loop(monkeypatch, "The GPU has 6 GB. Let me know if you need more detail.")
    assert not any(event.get("type") in {"agent_step", "intent_nudge_exhausted", "rounds_exhausted"}
                   for event in events)


def test_emits_loop_breaker_triggered_when_loop_breaker_trips(monkeypatch):
    _patch_common(monkeypatch)

    events = _run_loop(
        monkeypatch,
        '```update_plan\n{"plan":"- [ ] keep going"}\n```',
        max_rounds=6,
    )

    guard = next((e for e in events if e.get("type") == "loop_breaker_triggered"), None)
    assert guard is not None, events
    assert guard["reason"] == "loop_breaker_stall"
