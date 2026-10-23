#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PERSIST="${ODYSSEUS_PERSIST_DIR:?Set ODYSSEUS_PERSIST_DIR to your persistent disk directory}"
mkdir -p "$PERSIST/hf" "$PERSIST/out"
export HF_HOME="$PERSIST/hf"

python3 -m venv --system-site-packages "$PERSIST/training-venv"
PYTHON="$PERSIST/training-venv/bin/python"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install --upgrade unsloth unsloth_zoo 'transformers>=5.2,<6' datasets accelerate
"$PYTHON" -m pip check
"$PYTHON" -m pip freeze > "$PERSIST/training-environment.txt"
"$PYTHON" "$ROOT/train_lora.py" --check --prepared "$PERSIST/prepared" --allow-overlength-exclusions

"$PYTHON" - "$ROOT" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from train_lora import MODEL, REVISION
from huggingface_hub import snapshot_download
snapshot_download(MODEL, revision=REVISION)
PY

printf 'Environment ready. Run the two-step smoke test from RUNBOOK.md first.\n'
printf 'Prepared data: %s/prepared\nPython: %s\n' "$PERSIST" "$PYTHON"
