#!/usr/bin/env bash
# Install the training environment and download base weights.
# Point HF_HOME and the output directory at the host's persistent disk
# before running. Deleting the Hostinger instance drops anything else.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PERSIST="${ODYSSEUS_PERSIST_DIR:-$PWD/persist}"
mkdir -p "$PERSIST/hf" "$PERSIST/out" "$PERSIST/data"
export HF_HOME="$PERSIST/hf"
export HUGGINGFACE_HUB_CACHE="$PERSIST/hf/hub"

python3 -m pip install --upgrade pip
python3 -m pip install "unsloth" "trl" "datasets" "huggingface_hub"

python3 - <<'PY'
from huggingface_hub import snapshot_download
import os
dest = os.environ["HUGGINGFACE_HUB_CACHE"]
for repo in ("unsloth/gemma-4-26B-A4B-it", "unsloth/Qwen3.6-35B-A3B"):
    print("downloading", repo)
    snapshot_download(repo, cache_dir=dest)
PY

cp "$ROOT/seed_tasks.jsonl" "$ROOT/eval_prompts.jsonl" "$ROOT/train_lora.py" "$PERSIST/data/"
echo "Ready. Train with:"
echo "  python3 $ROOT/train_lora.py --family gemma --dataset $PERSIST/data/seed_tasks.jsonl --output $PERSIST/out/gemma"
echo "Copy $PERSIST/out off the instance before you delete it."
