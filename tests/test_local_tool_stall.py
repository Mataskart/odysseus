from src.agent_loop import _is_local_tool_stall, _sanitize_local_tool_history


def test_local_history_sanitizer_removes_only_short_narration_turns():
    history = [
        {"role": "user", "content": "Check VRAM"},
        {"role": "assistant", "content": "Let me check the current VRAM."},
        {"role": "assistant", "content": "I'll check", "tool_calls": [{"id": "c1"}]},
        {"role": "assistant", "content": "I will explain this in detail. " * 12},
        {"role": "assistant", "content": "Here is the answer."},
    ]

    sanitized = _sanitize_local_tool_history(history)

    assert [message.get("content") for message in sanitized] == [
        "Check VRAM",
        "I'll check",
        "I will explain this in detail. " * 12,
        "Here is the answer.",
    ]
    assert history[1]["content"] == "Let me check the current VRAM."


def test_local_tool_stall_requires_stop_narration_and_offered_tools():
    assert _is_local_tool_stall("Let me check VRAM now.", "stop", 2, [])
    assert not _is_local_tool_stall("Let me check VRAM now.", "length", 2, [])
    assert not _is_local_tool_stall("Let me check VRAM now.", "stop", 0, [])
    assert not _is_local_tool_stall("Let me check VRAM now.", "stop", 2, [{"id": "c1"}])
    assert not _is_local_tool_stall("The GPU uses 4 GB.", "stop", 2, [])


def test_closing_remarks_and_completed_work_are_not_stalls():
    assert not _is_local_tool_stall("Your GPU is at 45C. I'll keep an eye on it.", "stop", 2, [])
    assert not _is_local_tool_stall("Done. I've saved the note. I will remind you tomorrow.", "stop", 2, [])
    assert not _is_local_tool_stall("Let me check the logs. They show no errors since noon.", "stop", 2, [])
    assert _sanitize_local_tool_history([
        {"role": "assistant", "content": "Sure, I'll remember that."},
    ]) == [{"role": "assistant", "content": "Sure, I'll remember that."}]
