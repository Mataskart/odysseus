# Odysseus Qwen3.8 training runbook

Updated 2026-10-14. This replaces the old Gemma/Qwen3.6 recipe. No instance has been rented and no model training has been started.

## Checkpoint and method

- Original weights: `empero-ai/Qwen3.8-35B-A3B-Distill`.
- Pinned revision: `bcc2dbe2f21b213625df2dc1a5a690212373af07`.
- This is the Safetensors source named by the existing `empero-ai/Qwen3.8-35B-A3B-Distill-GGUF` model card. Saved Odysseus cookbook settings point to its Q4_K_M quantization. The running server was offline during preparation.
- The Safetensors tokenizer's template SHA256 equals the published GGUF template SHA256: `e84f32a23fdda27689f868aa4a1a5621f41133e51a48d7f3efcbea2839574259`. No generic Qwen template substitution.
- BF16 base, rank-16/alpha-16 language LoRA, learning rate 2e-5, one epoch initially, batch 1, accumulation 4, 32K maximum sequence length, Unsloth checkpointing. Targets include full-attention projections, hybrid linear-attention projections and MLP projections. The trainable-parameter audit refuses vision or non-LoRA weights. Expert support and actual trainable modules are recorded for the remote smoke test; no claim of verified expert coverage before loading on the GPU.
- Native `transformers.Trainer` consumes our precomputed labels with a custom collator. It does not reformat or regenerate masks. Prompt messages, including earlier assistant replies, tool outputs and padding receive -100 labels. Only completion assistant bodies (including serialized tool arguments) and their end markers receive loss. Empty thinking wrappers are preserved exactly as emitted by the checkpoint's template; no hidden reasoning is invented or extracted.
- Do not use full parameter training or 4-bit QLoRA for this recipe.

Sources: [checkpoint](https://huggingface.co/empero-ai/Qwen3.8-35B-A3B-Distill), [existing GGUF](https://huggingface.co/empero-ai/Qwen3.8-35B-A3B-Distill-GGUF), [Unsloth architecture-family guidance](https://unsloth.ai/docs/models/qwen3.5/fine-tune).

## Local tokenizer-only preparation

This downloads tokenizer metadata only, not the 35B model weights. Use a separate environment; do not change Odysseus's application environment.

```sh
python3 -m venv local_finetune/seed_chats/tokenizer_venv
local_finetune/seed_chats/tokenizer_venv/bin/pip install 'transformers==5.19.0'
local_finetune/seed_chats/tokenizer_venv/bin/python local_finetune/train_lora.py --prepare
python3 local_finetune/train_lora.py --check
```

The default input is now the hash-verified curated corpus under `seed_chats/balanced/`. It preserves all 659 effective episodes: **136 train and 523 stored holdout**, of which 217 are reviewed gold and 306 are reserve awaiting verification. Reserve answers are not included in evaluation loss. Original broad-approved personal/native/synthetic source files remain unchanged. No recursive glob, raw conversations or negative candidates enter training.

The prepared bundle has **136 training episodes** (143,096 input tokens; 17,227 supervised tokens) and **217 gold holdout episodes** (591,740 input tokens; 75,408 supervised tokens), with zero exclusions. Its inventory also records the 306 reserve episodes without scoring their uncertain answers. Training episodes peak at 11,317 tokens; gold holdout at 24,319. All 21 former oversized parents remain represented by their 28 evidence-preserving derivatives in the retained corpus. See [DATA_AUDIT_REPORT.md](DATA_AUDIT_REPORT.md) for the 191 answer repairs (122 in the main audit, 69 in the 2026-10-14 reserve pass) and balance decisions, and [CONTEXT_PREPARATION_REPORT.md](CONTEXT_PREPARATION_REPORT.md) for the earlier context pass.

Rebuild in this order: `scripts/build_context_reductions.py` if its source selections changed, `scripts/plan_audited_mix.py`, `scripts/build_audited_mix.py`, then `train_lora.py --prepare` and `--check`. Reviews and source hashes must be updated deliberately when new exports arrive. If audit decisions exist without balanced files, the trainer refuses to silently fall back to the old broad approvals. Synthetic source files stay separate and unchanged; only selected tokenized positives are combined for training.

Preparation refuses duplicate IDs/content, cross-split conversation groups, mismatched tool-result IDs, unsupported multimodal content, empty targets and uncertain template prefix boundaries. The manifest hashes source data, prepared data and every tokenizer file. Token offsets are measured on each complete rendered episode, so BPE token boundaries are not guessed by separately tokenizing a prompt and answer.

## Remote setup on one B200

Choose a persistent directory with sufficient storage (500GB recommended). Transfer `train_lora.py`, `setup_remote.sh` and the entire private `seed_chats/training_ready/` bundle. Example remote layout:

```text
/persist/odysseus/train_lora.py
/persist/odysseus/setup_remote.sh
/persist/odysseus/prepared/{train.jsonl,holdout.jsonl,manifest.json,episode_inventory.jsonl,tokenizer/}
```

Then run:

```sh
env ODYSSEUS_PERSIST_DIR=/persist/odysseus bash /persist/odysseus/setup_remote.sh
```

Setup creates an isolated training environment (retaining preset/system packages when available), installs current Unsloth/Unsloth Zoo with Transformers 5, validates dependencies and bundle hashes, records `training-environment.txt`, and downloads only the pinned distilled checkpoint. It does not train. GPU driver/CUDA compatibility must be confirmed on the actual instance; select a GPU-ready Ubuntu/Unsloth preset. Package versions are frozen after successful setup for reproducing that run; an untested package lock is not supplied.

## GPU smoke test, long-episode probe, then full run

The current bundle has no unresolved overlength entries. Run in this order, each into a new output directory:

```sh
env HF_HOME=/persist/odysseus/hf /persist/odysseus/training-venv/bin/python /persist/odysseus/train_lora.py --prepared /persist/odysseus/prepared --output /persist/odysseus/out/smoke --smoke-test
env HF_HOME=/persist/odysseus/hf /persist/odysseus/training-venv/bin/python /persist/odysseus/train_lora.py --prepared /persist/odysseus/prepared --output /persist/odysseus/out/probe --probe-long
cat /persist/odysseus/out/probe/gpu_memory.json
env HF_HOME=/persist/odysseus/hf /persist/odysseus/training-venv/bin/python /persist/odysseus/train_lora.py --prepared /persist/odysseus/prepared --output /persist/odysseus/out/qwen38_3ep --epochs 3 --export-gguf
/persist/odysseus/training-venv/bin/python compare_gguf.py --check /persist/odysseus/out/qwen38_3ep/gguf/<file>.gguf gguf_reference_q4_k_m.json
```

If a future bundle has overlength episodes, prepare their context first; `--allow-overlength-exclusions` is only an explicit alternative that excludes them. Smoke mode uses eight short training episodes, four short holdout episodes, and two optimizer steps. It saves a clearly labeled disposable adapter and refuses GGUF export. Inspect finite loss and recorded trainable parameter names.

The smoke test cannot reveal peak memory because it picks the shortest episodes. `--probe-long` takes one optimizer step on the four longest training episodes (one full accumulation group) and evaluates the two longest holdout episodes; it also refuses GGUF export. Holdout evaluation is the expected peak: gold holdout episodes reach about 24K tokens while training episodes stay near 11K, and evaluation computes full-vocabulary logits. Every run writes `gpu_memory.json` with peak allocated/reserved GiB and headroom for model load, baseline evaluation, training and final evaluation, plus the longest sequences exercised versus the bundle's longest. Start the full run only if the probe finished with finite loss and comfortable headroom (for example 15 GiB or more) in every phase. The full run saves the adapter before final evaluation, so a late evaluation failure cannot lose the trained adapter. Full-run held-out loss is measured before and after training; the smoke-test subset is not a quality benchmark.

Training saves a run manifest, epoch checkpoints, baseline/final held-out loss, adapter and tokenizer. `--resume /path/to/checkpoint` resumes an interrupted run into its existing output directory; otherwise a nonempty output directory is refused. `--max-steps` is an optional override; the normal run uses complete epochs. `--export-gguf` requests Q4_K_M export after saving the adapter, so an export failure does not lose the adapter. GGUF conversion remains to be validated on the remote machine with its actual llama.cpp tooling.

### Epochs, best-epoch selection and export check

Every epoch is followed by a gold-holdout evaluation and a kept checkpoint (`save_total_limit=None`). At the end the Trainer reloads the epoch with the lowest gold eval loss; `epoch_selection.json` lists each epoch's loss and the chosen checkpoint, and the saved adapter and GGUF come from that epoch. Each checkpoint is about 11 GB (3.6 GB adapter plus optimizer state). `scripts/compare_gguf.py` compares an export against `seed_chats/gguf_reference_q4_k_m.json`, recorded from the original `Qwen3.8-35B-A3B-Q4_K_M.gguf` (21.7 GB, `qwen35moe`, 41 blocks including one MTP `nextn` block, 256 experts / 8 active, 753 tensors, file type 15, 379 Q4_K + 64 Q6_K + 310 F32). It fails on any missing or reshaped tensor, quantization change, missing MTP layer, or growth beyond 1%.

### Measured on the B200 (2026-10-14)

Hostinger B200 (178 GiB usable, driver 595.91), Unsloth preset with Python 3.12 (needed `apt install python3.12-venv`), torch 2.14.1, Transformers 5.17.0, Unsloth 2026.10.5, PEFT 0.21.2. Transformers 5 removed `warmup_ratio`; the trainer uses `warmup_steps=0.05`. Unsloth attached LoRA to all 40 layers' attention (full and linear) and MLP projections and to the routed experts (`mlp.experts.gate_up_proj`, `down_proj`): 944M trainable parameters (2.62%), 780 LoRA tensors, none in vision; the adapter is 3.6 GB. The model loaded within 64 GB host RAM. Peak reserved GPU memory: 69.7 GiB after load, 77.1 GiB evaluating the 24K-token holdout episodes, 89.3 GiB training the four ~11K-token episodes (89 GiB headroom). Smoke and probe losses were finite. The instance has no persistent storage: download outputs before destroying it.

## Before replacing the local model

Copy all outputs and the environment record home. Compare the original and trained GGUF on unseen Odysseus tool workflows, Lithuanian tutoring, source fidelity, general reasoning and long-context tasks. Held-out loss alone does not prove improved answers. Keep the original model until the trained model passes this comparison. MTP acceptance, speed and vision behavior need separate verification; text-only training does not certify them. No upload or Hub publication is performed by these scripts.

The full target screen and conservative first-run balancing are complete. The 306 reserve targets still require specific repairs or further evidence before becoming positives or gold. The new150-case mocked evaluation suite is separate; run baseline/trained comparisons and manually grade semantic correctness before claiming improvement. See [EVALUATION_RUNBOOK.md](EVALUATION_RUNBOOK.md) and [FRESH_AGENT_HANDOFF.md](FRESH_AGENT_HANDOFF.md).

## Local verification completed

- Thirty-nine trainer/context/audit/evaluation tests passed (including the long-probe row selection, unsafe flag combinations and GPU-memory recorder) with Transformers 5.19.0 and the actual pinned tokenizer, including tool-call masks, masked history/tool results, next-call-only targets, padding/end markers, tampering rejection and a tiny randomly initialized CPU model taking one optimizer step through the same Trainer/collator path.
- Fifty-three export/review/repair/native/synthetic/pilot regression tests passed.
- Curated-corpus tokenizer preparation and bundle verification passed; all 659 retained IDs remain inventoried and original source hashes still match. Shell syntax, Python compilation and diff whitespace checks passed.
- No 35B weights were loaded locally. B200 execution, Unsloth's actual MoE adapter coverage, peak VRAM and GGUF conversion remain unverified until the remote smoke/full run.

## First fine-tune result (2026-10-14)

Run `out/qwen38_3ep` on the B200: 4× mix, 3 epochs (102 optimizer steps, ~4 min training), LoRA r16 on attention, MLP and routed experts. Gold holdout loss (217 episodes): baseline 0.9947, epoch 1 0.9353, epoch 2 0.9208, **epoch 3 0.9188 (selected)**. Q4_K_M export: 21,713,462,688 bytes (original 21,713,462,944), identical 753-tensor layout, quant mix and MTP layer per `compare_gguf.py`; vision projector not converted (none is used locally). Downloaded to `seed_chats/training_runs/qwen38_3ep/` (adapter SHA256 8a3698e1…, GGUF SHA256 29a58d69…, see `gguf/SHA256SUMS`).

Unseen suite (150 cases, temperature 0, same llama.cpp KV settings as local: q4_0, flash-attn, 40K context, served on the B200): **both models 150/150 mechanical passes**, identical tool-call counts, no reasoning leakage. The suite is at ceiling mechanically. Blinded pairwise review (A/B randomised, key in `evaluation_unseen/blinded_review_ab_key.json`, grades in `blinded_review_qwen38_3ep.jsonl`): Lithuanian tutoring trained 9 wins (2 clear) vs baseline 6 (slight), 15 ties, criteria met 30/30 vs 28/30 (baseline errors: wrong median position, unsupported reinforcement content and wrong word); failed-tool recovery baseline 3 slight vs trained 1 slight, 26 ties (both sometimes omit that the requested file was missing at long context); discovery, follow-through and evidence correction 90 ties. Trained answers are shorter (median chars: discovery 90→39, tutoring 298→244, follow-through 202→177). Generation speed on B200 identical (~228 tok/s). Interpretation: no regressions found; a small, not statistically established improvement in Lithuanian tutoring. Live Odysseus use, local speed with `--n-cpu-moe`, and broader general-knowledge quality are still unverified.

### Holdout answer comparison and imatrix quantization (2026-10-14)

**Real held-out tasks.** Both Q4_K_M models answered all 217 gold holdout prompts (never trained on) at the local sampling settings (temp 0.6, top-p 0.95, top-k 20, seed 3407, max 3,072 tokens, thinking on), via `scripts/generate_holdout_answers.py`, served on the B200 through an SSH tunnel. Four blinded reviewers compared each pair with the reviewed gold answer as an anchor (`seed_chats/evaluation_holdout/blinded_review_qwen38_3ep.jsonl`, key alongside). Result: trained 85 wins (29 clear), baseline 88 (33 clear), 44 ties; acceptable 160 vs 164; sign test p = 0.88, **no detectable difference**. Splits (within noise): study 37–30 and coding 22–18 favour trained; writing 6–13, practical 5–8, technical 11–13 favour baseline. Trained answers are ~17% shorter (median 1,028 vs 1,242 chars). 8 answers per model hit the token cap (some empty because thinking used the budget). Conclusion: this small first run (~17K supervised tokens, 102 steps) is roughly neutral on general quality: no regression found, no clear gain. Larger effects need more (repaired) data or a different mix, evaluated the same way.

**imatrix Q4_K_M.** The trained merge was converted to BF16 GGUF, an importance matrix computed on the training text only (291 × 512-token chunks; a few experts 99.2–99.6% covered), and re-quantized to Q4_K_M with it (same 753-tensor layout, mix and MTP; `compare_gguf.py` passes; 21,713,462,912 bytes). KL divergence versus the BF16 fine-tuned model on 12 × 2,048-token holdout chunks: plain Q4_K_M mean KLD 0.0776, median 0.00386, 99% 1.68, RMS Δp 8.2%, same top token 95.1%; **imatrix Q4_K_M mean 0.0624, median 0.00248, 99% 1.22, RMS Δp 7.2%, same top 96.0%**. Prefer the imatrix file (`training_runs/qwen38_3ep/gguf_imatrix/`); the imatrix itself and the pipeline scripts/log are in `gguf_imatrix/aux/`. Tools were built on the B200 from Unsloth's llama.cpp checkout with CUDA 13.0 (`sm_100`); the prebuilt Unsloth binaries need `LD_LIBRARY_PATH` pointing at the CUDA 13 runtime from the training venv.

### Local test on the RTX 3060 Ti (2026-10-14)

Production settings (`--n-cpu-moe 32`, q4_0 KV, flash-attn, 8 threads, 50K context; scripts and logs in `training_runs/qwen38_3ep/local_tests/`). `llama-bench` at 8K depth: original 437 tok/s prompt / 44.7 tok/s generation, plain trained 434 / 43.8, imatrix trained 456 / 44.1: identical within noise. The imatrix model loads in 7.8 of 8 GB VRAM, like the original. On the 50 short mocked-tool cases (temperature 0, port 8010 so Odysseus on 8000 is unaffected) both the original and the imatrix fine-tune pass 50/50; the fine-tune finishes the set slightly faster (337 s vs 353 s total; median answer 161 vs 207 chars), mainly on Lithuanian tutoring and evidence answers. Odysseus itself was not switched to the new model.
