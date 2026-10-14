"""The MTP drafter passed to --model-draft must match the selected GGUF's snapshot."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SERVE = (Path(__file__).resolve().parent.parent / "static/js/cookbookServe.js").read_text(encoding="utf-8")
HELPERS = ("_ggufFilesForModel", "_isDrafterGguf", "_inSameSnapshot", "_drafterGgufFiles", "_runnableGgufFiles")


def _function_source(name):
    match = re.search(rf"^function {name}\(.*?^}}\n", SERVE, re.S | re.M)
    assert match, name
    return match.group(0)


def _run(expression, model):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = "\n".join(_function_source(name) for name in HELPERS)
    script += f"\nconst model = {json.dumps(model)};\nconsole.log(JSON.stringify({expression}));"
    return json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)


def _file(rel_path, role="model"):
    return {"rel_path": rel_path, "name": rel_path.split("/")[-1], "role": role}


def test_drafter_comes_from_the_selected_snapshot_and_prefers_quantized():
    model = {"gguf_files": [
        _file("aaa/model-Q4_K_M.gguf"),
        _file("aaa/mtp-Q8_0.gguf", "drafter"),
        _file("bbb/model-Q4_K_M.gguf"),
        _file("bbb/mtp-BF16.gguf", "drafter"),
        _file("bbb/mtp-Q8_0.gguf", "drafter"),
        _file("bbb/MTP/mtp-F16.gguf", "drafter"),
    ]}
    chosen = _run("_drafterGgufFiles(model, 'bbb/model-Q4_K_M.gguf').map(f => f.rel_path)", model)
    assert chosen == ["bbb/mtp-Q8_0.gguf", "bbb/mtp-BF16.gguf", "bbb/MTP/mtp-F16.gguf"]


def test_no_drafter_when_selected_snapshot_has_none():
    model = {"gguf_files": [_file("aaa/mtp-Q8_0.gguf", "drafter"), _file("bbb/model-Q4_K_M.gguf")]}
    assert _run("_drafterGgufFiles(model, 'bbb/model-Q4_K_M.gguf')", model) == []


def test_drafter_and_projector_are_never_runnable_main_models():
    model = {"gguf_files": [_file("aaa/mtp-Q8_0.gguf", "unknown"), _file("aaa/mmproj-F16.gguf", "projector")]}
    assert _run("_runnableGgufFiles(model)", model) == []
