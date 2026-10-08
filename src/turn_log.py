"""Opt-in copies of chat turns, stored outside the git checkout."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

_MAX_TEXT = 80_000


def log_directory() -> Path:
    override = os.environ.get("ODYSSEUS_TURN_LOG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "state" / "odysseus" / "turn-logs"


def logging_enabled() -> bool:
    flag = os.environ.get("ODYSSEUS_TURN_LOG", "").strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    if flag in {"1", "true", "on", "yes"}:
        return True
    try:
        from src.settings import get_setting
        return bool(get_setting("turn_log_enabled", False))
    except Exception:
        return False


def _clip(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    if len(value) <= _MAX_TEXT:
        return value
    return value[:_MAX_TEXT] + "\n[truncated]"


def _append(filename: str, record: dict) -> None:
    directory = log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def record_turn(
    *,
    kind: str,
    session_id,
    model: str,
    messages,
    response: str,
    tool_events,
    offered_tools,
) -> None:
    if not logging_enabled():
        return
    clipped_messages = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        clipped_messages.append({
            "role": message.get("role"),
            "content": _clip(message.get("content")),
            "tool_calls": message.get("tool_calls"),
        })
    clipped_events = []
    for event in tool_events or []:
        if not isinstance(event, dict):
            continue
        copied = dict(event)
        if "output" in copied:
            copied["output"] = _clip(copied.get("output"))
        if "command" in copied:
            copied["command"] = _clip(copied.get("command"))
        clipped_events.append(copied)
    _append("turns.jsonl", {
        "at": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "session_id": session_id,
        "model": model,
        "offered_tools": list(offered_tools or []),
        "messages": clipped_messages,
        "tool_events": clipped_events,
        "response": _clip(response),
    })


def record_flag(*, session_id: str, message_id: str) -> None:
    _append("flags.jsonl", {
        "at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id or "",
        "message_id": message_id or "",
    })
