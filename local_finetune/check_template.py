"""Render one seed row through the running llama-server chat template.

Uses the server's own template, so a local Gemma or Qwen process is enough.
No weights are loaded here.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def render(base_url: str, messages: list) -> str:
    payload = json.dumps({"messages": messages}).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/apply-template",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    if isinstance(body, dict):
        return body.get("prompt") or body.get("result") or json.dumps(body)
    return str(body)


def main() -> None:
    base_url = os.environ.get("LLAMA_SERVER_URL", "http://127.0.0.1:8000")
    row = json.loads((ROOT / "seed_tasks.jsonl").read_text(encoding="utf-8").splitlines()[0])
    try:
        prompt = render(base_url, row["messages"])
    except Exception as exc:
        raise SystemExit(f"template render failed against {base_url}: {exc}") from exc
    if "Odysseus" not in prompt and "computer" not in prompt.lower():
        raise SystemExit("rendered prompt dropped the user text")
    print(prompt[:1200])
    print("---")
    print(f"ok: rendered {len(prompt)} chars via {base_url}")


if __name__ == "__main__":
    main()
