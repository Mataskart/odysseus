"""Check seed and eval JSONL before any GPU time is spent."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED_MESSAGE_ROLES = {"system", "user", "assistant", "tool"}


def load_jsonl(path: Path) -> list:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path.name}:{line_number}: {exc}") from exc
    return rows


def check_messages(path: Path, row: dict) -> None:
    messages = row.get("messages")
    if not isinstance(messages, list) or not messages:
        raise SystemExit(f"{path.name}: {row.get('id')} has no messages")
    for message in messages:
        role = message.get("role")
        if role not in REQUIRED_MESSAGE_ROLES:
            raise SystemExit(f"{path.name}: {row.get('id')} has role {role!r}")
        if "content" not in message:
            raise SystemExit(f"{path.name}: {row.get('id')} message missing content")
        for call in message.get("tool_calls") or []:
            function = (call or {}).get("function") or {}
            name = function.get("name")
            arguments = function.get("arguments")
            if not name or not isinstance(arguments, str):
                raise SystemExit(f"{path.name}: {row.get('id')} tool call needs name and string arguments")
            json.loads(arguments)


def main() -> None:
    seed_path = ROOT / "seed_tasks.jsonl"
    eval_path = ROOT / "eval_prompts.jsonl"
    seed_rows = load_jsonl(seed_path)
    eval_rows = load_jsonl(eval_path)
    seed_ids = set()
    for row in seed_rows:
        if not row.get("id") or row["id"] in seed_ids:
            raise SystemExit(f"duplicate or missing seed id: {row.get('id')}")
        seed_ids.add(row["id"])
        check_messages(seed_path, row)
    eval_ids = set()
    for row in eval_rows:
        if not row.get("id") or row["id"] in eval_ids:
            raise SystemExit(f"duplicate or missing eval id: {row.get('id')}")
        eval_ids.add(row["id"])
        if "prompt" not in row:
            raise SystemExit(f"{row['id']} missing prompt")
        if row["id"] in seed_ids:
            raise SystemExit(f"{row['id']} is in both seed and eval")
    print(f"ok: {len(seed_rows)} seed rows, {len(eval_rows)} eval prompts")


if __name__ == "__main__":
    main()
