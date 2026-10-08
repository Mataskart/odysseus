# Fine-tune runbook

Do this only after a week of flagged turns. Do not start a Hostinger instance until that data exists and you say to.

## What this changes, and what it costs

- Method is LoRA on the full-precision bases, then a merge back to Q4_K_M GGUF. Full fine-tuning is out of scope.
- Gemma's current file is a quantization-aware Q4. A LoRA merge does not keep that QAT advantage.
- Gemma's MTP drafter and Qwen's MTP heads were trained on the original weights. After this merge, fewer drafted tokens will be accepted until those heads are retrained. Leave that for a later RTX PRO 6000 session.
- Local launch flags stay as they are. Swap only the GGUF path after you have compared eval scores.

## Bases

- Gemma: `unsloth/gemma-4-26B-A4B-it`, 16-bit LoRA. Unsloth advises against 4-bit LoRA for this MoE. It needs more than 40GB, so use the B200 (192GB) or the RTX PRO 6000 (96GB).
- Qwen: `unsloth/Qwen3.6-35B-A3B`, 16-bit LoRA, on a recent Unsloth that includes the Qwen3.6 MoE LoRA fix.
- Accept any Hugging Face license gate on these repos before the session, from a machine that is not billing.

## Spend

5,000 credits is about 11 hours of B200 (450/hour) or about 77 hours of RTX PRO 6000 (65/hour). Skip the A100: it costs more than the PRO 6000 and has less VRAM.

One B200 session, about 6–8 hours:

1. `bash setup_remote.sh` with `ODYSSEUS_PERSIST_DIR` on the persistent disk.
2. Generate more rows with a large teacher model using `teacher_prompt.txt`. Append them to the dataset. Keep `eval_prompts.jsonl` out of training.
3. Train Gemma, then Qwen.
4. Copy `persist/out` to this machine.
5. Delete the instance. Billing continues until it is deleted, rounded up to the next hour.

Repeat runs, eval, and MTP retraining go on the RTX PRO 6000.

## Before paying

```bash
python3 local_finetune/validate_dataset.py
python3 local_finetune/check_template.py
python3 local_finetune/train_lora.py --check --family gemma --dataset local_finetune/seed_tasks.jsonl --output /tmp/unused
```

`check_template.py` talks to the llama-server already running on port 8000.

## After the GGUF is home

Score `eval_prompts.jsonl` against the old server and the new server. Keep the new file only if tool choice and refusal rate are better and tokens per second are still acceptable.
