"""Prepare masked Odysseus episodes locally; train the pinned Qwen on a GPU."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = "empero-ai/Qwen3.8-35B-A3B-Distill"
REVISION = "bcc2dbe2f21b213625df2dc1a5a690212373af07"
DEFAULT_PREPARED = ROOT / "seed_chats/training_ready"
TRAIN_SOURCES = [
    "approved/sft_train.jsonl",
    "odysseus/batches/native_2026_10_11/training_v1/sft_train.jsonl",
    "synthetic/batches/pilot_2026_10_11/reviewed/sft_candidates.jsonl",
    "synthetic/batches/expansion_2026_10_12/reviewed/sft_train.jsonl",
]
HOLDOUT_SOURCES = [
    "approved/sft_holdout.jsonl",
    "odysseus/batches/native_2026_10_11/training_v1/sft_holdout.jsonl",
]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_rows(path):
    rows = []
    with Path(path).open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        raise ValueError(f"Empty dataset: {path}")
    return rows


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    with Path(path).open("w", encoding="utf-8") as destination:
        for row in rows:
            destination.write(json.dumps(row, ensure_ascii=False) + "\n")


def episode_messages(row):
    prompt = copy.deepcopy(row["prompt"])
    completion = copy.deepcopy(row["completion"])
    if isinstance(completion, str):
        completion = [{"role": "assistant", "content": completion}]
    if not prompt or not completion or not any(m["role"] == "user" for m in prompt):
        raise ValueError("Episode needs a user prompt and a completion")
    if completion[-1]["role"] != "assistant":
        raise ValueError("Completion must end with an assistant")
    if any(m["role"] not in {"assistant", "tool"} for m in completion):
        raise ValueError("Completion may only contain assistant and tool messages")
    pending = set()
    messages = prompt + completion
    for message in messages:
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("This trainer supports text-only episodes")
        if message["role"] == "tool":
            call_id = message.get("tool_call_id")
            if call_id not in pending:
                raise ValueError("Tool result has no matching outstanding call")
            pending.remove(call_id)
        calls = message.get("tool_calls", [])
        if calls and message["role"] != "assistant":
            raise ValueError("Only assistant messages can call tools")
        for call in calls:
            if call["id"] in pending:
                raise ValueError("Duplicate outstanding tool call ID")
            pending.add(call["id"])
            function = call["function"]
            if isinstance(function["arguments"], str):
                function["arguments"] = json.loads(function["arguments"])
            if not isinstance(function["arguments"], dict):
                raise ValueError("Tool arguments must be an object")
    if pending and not completion[-1].get("tool_calls"):
        raise ValueError("Unresolved tool calls in a complete episode")
    return prompt, messages


def render(tokenizer, messages, tools):
    return tokenizer.apply_chat_template(
        messages, tools=tools or None, tokenize=False, add_generation_prompt=False,
    )


def encode_episode(tokenizer, row):
    prompt, messages = episode_messages(row)
    tools = row.get("tools", [])
    text = render(tokenizer, messages, tools)
    spans = []
    for index in range(len(prompt), len(messages)):
        if messages[index]["role"] != "assistant":
            continue
        before = render(tokenizer, messages[:index], tools)
        through = render(tokenizer, messages[:index + 1], tools)
        if not text.startswith(through) or not through.startswith(before):
            raise ValueError("Chat template changed an earlier prefix; refusing an uncertain mask")
        header = "<|im_start|>assistant\n"
        if not through[len(before):].startswith(header):
            raise ValueError("Unexpected assistant header in pinned Qwen template")
        spans.append((len(before) + len(header), len(through)))
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    labels = []
    for token_id, (start, end) in zip(encoded["input_ids"], encoded["offset_mapping"]):
        supervised = end > start and any(start >= left and end <= right for left, right in spans)
        labels.append(token_id if supervised else -100)
    if not any(value != -100 for value in labels):
        raise ValueError("Episode has no supervised assistant tokens")
    return {"input_ids": encoded["input_ids"], "attention_mask": encoded["attention_mask"], "labels": labels}



def apply_context_reductions(original, replacements):
    replacement = replacements.get(original["id"])
    if replacement is None:
        return [original]
    fingerprint = hashlib.sha256(json.dumps(original, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if fingerprint != replacement["original_row_sha256"]:
        raise ValueError(f"Original context-reduction source changed: {original['id']}")
    episodes = replacement["episodes"]
    if not episodes:
        raise ValueError("Context reduction cannot discard its parent episode")
    for row in episodes:
        review = row["context_reduction"]
        if review["parent_id"] != original["id"] or review["review_status"] not in {"accepted_reduced", "accepted_repaired"}:
            raise ValueError("Context reduction is unreviewed or belongs to another parent")
        if (row.get("group"), row.get("split_group")) != (original.get("group"), original.get("split_group")):
            raise ValueError("Context reduction changed the conversation group")
        if row.get("split") != original.get("split"):
            raise ValueError("Context reduction changed the split")
    return episodes


def prepare(args):
    from transformers import AutoTokenizer

    destination = args.prepared
    destination.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, trust_remote_code=False)
    if not tokenizer.is_fast:
        raise ValueError("A fast tokenizer with offsets is required for verified masking")
    tokenizer.save_pretrained(destination / "tokenizer")
    report = {
        "model": MODEL, "revision": REVISION, "max_seq_length": args.max_seq_length,
        "template_sha256": hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
        "tokenizer_files": {p.name: sha256(p) for p in (destination / "tokenizer").iterdir() if p.is_file()},
        "sources": [], "splits": {}, "excluded": [],
        "masking": "Only assistant completion bodies and end markers; no prompt/tool/padding loss",
    }
    balanced_manifest = args.seed_root / "balanced/manifest.json"
    if (args.seed_root / "audit_2026_10_13/review_plan.json").exists() and not balanced_manifest.exists():
        raise ValueError("Audit decisions exist; build the balanced corpus before tokenizer preparation")
    train_sources, holdout_sources = TRAIN_SOURCES, HOLDOUT_SOURCES
    if balanced_manifest.exists():
        balance = json.loads(balanced_manifest.read_text())
        for name, expected_hash in balance["files"].items():
            if sha256(balanced_manifest.parent / name) != expected_hash:
                raise ValueError(f"Balanced source changed: {name}")
        train_sources = ["balanced/sft_train.jsonl"]
        holdout_sources = ["balanced/sft_holdout.jsonl"]
        report["balanced_corpus"] = {"sha256": sha256(balanced_manifest), **balance}
    report["reserved_holdout"] = []
    reduction_path = args.seed_root / "context_reduction/overrides.json"
    replacements = {}
    if reduction_path.exists() and not balanced_manifest.exists():
        reduction_bundle = json.loads(reduction_path.read_text())
        if reduction_bundle["version"] != 1:
            raise ValueError("Unsupported context-reduction version")
        replacements = reduction_bundle["replacements"]
        report["context_reductions"] = {"path": "context_reduction/overrides.json", "sha256": sha256(reduction_path),
                                         "parents": len(replacements), "episodes": sum(len(r["episodes"]) for r in replacements.values())}
    applied_reductions = set()
    episode_inventory = []
    seen_ids = set()
    split_groups = {}
    split_signatures = {}
    for split, sources in [("train", train_sources), ("holdout", holdout_sources)]:
        output = []
        token_count = supervised_count = 0
        for relative in sources:
            path = args.seed_root / relative
            report["sources"].append({"path": relative, "sha256": sha256(path), "split": split})
            source_rows = []
            for original in load_rows(path):
                source_rows.extend(apply_context_reductions(original, replacements))
                if original["id"] in replacements:
                    applied_reductions.add(original["id"])
            for row in source_rows:
                identifier = row["id"]
                if identifier in seen_ids:
                    raise ValueError(f"Duplicate episode ID: {identifier}")
                seen_ids.add(identifier)
                if row.get("split", split) != split:
                    raise ValueError(f"Wrong split in {identifier}")
                group = row.get("split_group") or row.get("group")
                if not group:
                    raise ValueError(f"Missing conversation group: {identifier}")
                if group in split_groups and split_groups[group] != split:
                    raise ValueError(f"Conversation group crosses splits: {group}")
                split_groups[group] = split
                signature = hashlib.sha256(json.dumps(
                    [row["prompt"], row["completion"]], sort_keys=True, ensure_ascii=False,
                ).encode()).hexdigest()
                if signature in split_signatures:
                    raise ValueError(f"Duplicate episode content: {identifier}")
                split_signatures[signature] = split
                encoded = encode_episode(tokenizer, row)
                length = len(encoded["input_ids"])
                if length > args.max_seq_length:
                    report["excluded"].append({"id": identifier, "split": split, "tokens": length, "reason": "overlength; no truncation performed"})
                    continue
                if split == "holdout" and row.get("evaluation_eligible") is False:
                    report["reserved_holdout"].append(identifier)
                    episode_inventory.append({"id": identifier, "split": split, "source": relative,
                                              "parent_id": row.get("context_reduction", {}).get("parent_id"),
                                              "tokens": length, "supervised_tokens": 0,
                                              "evaluation_eligible": False})
                    continue
                output.append(encoded)
                episode_inventory.append({"id": identifier, "split": split, "source": relative,
                                          "parent_id": row.get("context_reduction", {}).get("parent_id"), "tokens": length,
                                          "supervised_tokens": sum(value != -100 for value in encoded["labels"])})
                token_count += length
                supervised_count += sum(value != -100 for value in encoded["labels"])
        if not output:
            raise ValueError(f"No usable {split} episodes")
        output_path = destination / f"{split}.jsonl"
        write_jsonl(output_path, output)
        report["splits"][split] = {"episodes": len(output), "tokens": token_count, "supervised_tokens": supervised_count, "sha256": sha256(output_path)}
    if applied_reductions != set(replacements):
        raise ValueError("Context reductions reference parents outside the explicit dataset sources")
    write_jsonl(destination / "episode_inventory.jsonl", episode_inventory)
    report["episode_inventory_sha256"] = sha256(destination / "episode_inventory.jsonl")
    write_json(destination / "manifest.json", report)
    print(json.dumps({"splits": report["splits"], "overlength_excluded": len(report["excluded"]), "manifest": str(destination / "manifest.json")}, indent=2))


class MaskedCollator:
    def __init__(self, pad_token_id):
        self.pad_token_id = pad_token_id

    def __call__(self, features):
        import torch

        length = max(len(row["input_ids"]) for row in features)
        batch = {"input_ids": [], "attention_mask": [], "labels": []}
        for row in features:
            padding = length - len(row["input_ids"])
            batch["input_ids"].append(row["input_ids"] + [self.pad_token_id] * padding)
            batch["attention_mask"].append(row["attention_mask"] + [0] * padding)
            batch["labels"].append(row["labels"] + [-100] * padding)
        return {key: torch.tensor(value, dtype=torch.long) for key, value in batch.items()}


def verify_prepared(directory, allow_exclusions):
    report = json.loads((directory / "manifest.json").read_text())
    if (report["model"], report["revision"]) != (MODEL, REVISION):
        raise ValueError("Prepared data belongs to a different checkpoint")
    if report["excluded"] and not allow_exclusions:
        raise ValueError("Overlength episodes need context preparation or explicit --allow-overlength-exclusions")
    if "episode_inventory_sha256" in report:
        if sha256(directory / "episode_inventory.jsonl") != report["episode_inventory_sha256"]:
            raise ValueError("Prepared episode inventory changed")
    for name, expected_hash in report["tokenizer_files"].items():
        if sha256(directory / "tokenizer" / name) != expected_hash:
            raise ValueError(f"Prepared tokenizer file changed: {name}")
    for split in ("train", "holdout"):
        if sha256(directory / f"{split}.jsonl") != report["splits"][split]["sha256"]:
            raise ValueError(f"Prepared {split} data changed since verification")
        for row in load_rows(directory / f"{split}.jsonl"):
            if not len(row["input_ids"]) == len(row["attention_mask"]) == len(row["labels"]):
                raise ValueError("Token/mask length mismatch")
            if len(row["input_ids"]) > report["max_seq_length"]:
                raise ValueError("Prepared episode exceeds context length")
            if not any(label != -100 for label in row["labels"]):
                raise ValueError("All tokens are masked")
            if any(label not in (-100, token) for label, token in zip(row["labels"], row["input_ids"])):
                raise ValueError("Label differs from its input token")
    return report


def select_rows(train_rows, holdout_rows, mode):
    """Smoke uses the shortest episodes; the probe uses the longest, which set peak training and evaluation memory."""
    if mode is None:
        return train_rows, holdout_rows
    longest_first = mode == "probe_long"
    by_length = lambda row: len(row["input_ids"])
    train_count, holdout_count = (4, 2) if longest_first else (8, 4)
    return (sorted(train_rows, key=by_length, reverse=longest_first)[:train_count],
            sorted(holdout_rows, key=by_length, reverse=longest_first)[:holdout_count])


def gpu_memory(torch, phase):
    """Peak memory since the previous reset, then reset for the next phase."""
    total = torch.cuda.get_device_properties(0).total_memory
    peak = {"phase": phase, "peak_allocated_gib": torch.cuda.max_memory_allocated() / 2**30,
            "peak_reserved_gib": torch.cuda.max_memory_reserved() / 2**30, "total_gib": total / 2**30}
    peak["headroom_gib"] = peak["total_gib"] - peak["peak_reserved_gib"]
    torch.cuda.reset_peak_memory_stats()
    return peak


def training_arguments(TrainingArguments, args, **overrides):
    """Transformers 5 removed warmup_ratio; a float warmup_steps below 1 is the ratio of total steps.
    Every epoch checkpoint is kept, and the epoch with the lowest gold holdout loss is reloaded at the end."""
    settings = dict(
        output_dir=str(args.output / "checkpoints"),
        num_train_epochs=args.epochs, max_steps=args.max_steps,
        per_device_train_batch_size=1, per_device_eval_batch_size=1,
        gradient_accumulation_steps=4, learning_rate=args.learning_rate,
        warmup_steps=0.05, optim="adamw_torch", weight_decay=0.01,
        lr_scheduler_type="linear", bf16=True, seed=3407,
        logging_steps=1, eval_strategy="epoch", save_strategy="epoch",
        save_total_limit=None, load_best_model_at_end=True,
        metric_for_best_model="eval_loss", greater_is_better=False,
        prediction_loss_only=True, report_to="none",
        remove_unused_columns=False, dataloader_num_workers=0,
    )
    settings.update(overrides)
    return TrainingArguments(**settings)


def epoch_selection(state):
    """Gold holdout loss per epoch and the checkpoint reloaded as the final adapter."""
    evaluations = [{"epoch": entry["epoch"], "step": entry["step"], "eval_loss": entry["eval_loss"]}
                   for entry in state.log_history if "eval_loss" in entry]
    return {"evaluations": evaluations, "best_eval_loss": state.best_metric,
            "best_checkpoint": state.best_model_checkpoint,
            "note": "The saved adapter and any GGUF export come from best_checkpoint."}


def train(args):
    report = verify_prepared(args.prepared, args.allow_overlength_exclusions)
    if args.output.exists() and any(args.output.iterdir()) and not args.resume:
        raise ValueError("Output is not empty; use a new directory or --resume CHECKPOINT")
    from unsloth import FastLanguageModel
    import torch
    from datasets import Dataset
    from transformers import AutoTokenizer, Trainer, TrainingArguments

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise ValueError("Training requires a BF16-capable CUDA GPU; use --prepare locally")
    tokenizer = AutoTokenizer.from_pretrained(args.prepared / "tokenizer")
    template_hash = hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()
    if template_hash != report["template_sha256"]:
        raise ValueError("Prepared tokenizer template changed")
    model, loaded_tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL, revision=REVISION, max_seq_length=report["max_seq_length"],
        dtype=torch.bfloat16, load_in_4bit=False, load_in_16bit=True,
        full_finetuning=False, trust_remote_code=False,
    )
    loaded_tokenizer = getattr(loaded_tokenizer, "tokenizer", loaded_tokenizer)
    if loaded_tokenizer.get_vocab() != tokenizer.get_vocab():
        raise ValueError("Model loader substituted a different tokenizer")
    if model.config.model_type not in {"qwen3_5_moe", "qwen3_5_moe_text"}:
        raise ValueError("Unexpected model architecture from loader")
    model = FastLanguageModel.get_peft_model(
        model, r=16, lora_alpha=16, lora_dropout=0, bias="none",
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "in_proj_qkv", "in_proj_z", "in_proj_b", "in_proj_a", "out_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        use_gradient_checkpointing="unsloth", random_state=3407,
    )
    trainable = [name for name, parameter in model.named_parameters() if parameter.requires_grad]
    if not trainable or any("lora_" not in name or "visual" in name or "vision" in name for name in trainable):
        raise ValueError("Unexpected trainable parameters; expected language LoRA only")
    args.output.mkdir(parents=True, exist_ok=True)
    # A resumed run keeps the original run's config and baseline records.
    suffix = "_resume" if args.resume else ""
    write_json(args.output / f"run_config{suffix}.json", {
        "model": MODEL, "revision": REVISION, "epochs": args.epochs,
        "max_steps": args.max_steps, "learning_rate": args.learning_rate,
        "prepared_manifest": report, "trainable_parameters": trainable,
        "smoke_test": args.smoke_test, "probe_long": args.probe_long, "resume": args.resume,
    })
    model.config.use_cache = False
    pad_token_id = tokenizer.pad_token_id
    if pad_token_id is None:
        pad_token_id = tokenizer.eos_token_id
    all_train_rows = load_rows(args.prepared / "train.jsonl")
    all_holdout_rows = load_rows(args.prepared / "holdout.jsonl")
    mode = "smoke" if args.smoke_test else "probe_long" if args.probe_long else None
    train_rows, holdout_rows = select_rows(all_train_rows, all_holdout_rows, mode)
    longest = lambda rows: max(len(row["input_ids"]) for row in rows)
    memory = {"mode": mode or "full", "longest_train_tokens": longest(train_rows),
              "longest_holdout_tokens": longest(holdout_rows),
              "bundle_longest_train_tokens": longest(all_train_rows),
              "bundle_longest_holdout_tokens": longest(all_holdout_rows),
              "phases": [gpu_memory(torch, "model_loaded")]}
    trainer = Trainer(
        model=model, processing_class=tokenizer,
        train_dataset=Dataset.from_list(train_rows),
        eval_dataset=Dataset.from_list(holdout_rows),
        data_collator=MaskedCollator(pad_token_id),
        args=training_arguments(TrainingArguments, args),
    )
    memory_file = args.output / f"gpu_memory{suffix}.json"
    if not args.resume:
        # The baseline is the untrained model; on resume it already exists and
        # rerunning the long-holdout eval only costs GPU time.
        write_json(args.output / "baseline_eval.json", trainer.evaluate())
        memory["phases"].append(gpu_memory(torch, "baseline_eval"))
        write_json(memory_file, memory)
    result = trainer.train(resume_from_checkpoint=args.resume)
    memory["phases"].append(gpu_memory(torch, "train"))
    write_json(memory_file, memory)
    write_json(args.output / "train_metrics.json", result.metrics)
    write_json(args.output / "epoch_selection.json", epoch_selection(trainer.state))
    model.save_pretrained(str(args.output / "adapter"))
    tokenizer.save_pretrained(args.output / "adapter")
    write_json(args.output / "final_eval.json", trainer.evaluate())
    memory["phases"].append(gpu_memory(torch, "final_eval"))
    write_json(memory_file, memory)
    if args.export_gguf:
        model.save_pretrained_gguf(str(args.output / "gguf"), tokenizer, quantization_method="q4_k_m")
    print(f"Saved adapter under {args.output / 'adapter'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true", help="Tokenizer-only preparation; no model weights")
    mode.add_argument("--check", action="store_true", help="Verify the prepared bundle without loading weights")
    parser.add_argument("--family", choices=["qwen"], default="qwen")
    parser.add_argument("--seed-root", type=Path, default=ROOT / "seed_chats")
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--output", type=Path, default=ROOT / "seed_chats/training_runs/qwen38")
    parser.add_argument("--max-seq-length", type=int, default=32768)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--max-steps", type=int, default=-1, help="Use 2 for the GPU smoke test")
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--smoke-test", action="store_true", help="Two optimizer steps on eight short episodes, four holdout episodes")
    parser.add_argument("--probe-long", action="store_true", help="One optimizer step on the four longest training episodes; evaluate the two longest holdout episodes")
    parser.add_argument("--resume", help="Trainer checkpoint directory")
    parser.add_argument("--allow-overlength-exclusions", action="store_true")
    parser.add_argument("--export-gguf", action="store_true")
    args = parser.parse_args()
    if args.smoke_test and args.probe_long:
        parser.error("Choose either --smoke-test or --probe-long")
    if args.smoke_test or args.probe_long:
        args.max_steps = 2 if args.smoke_test else 1
        if args.export_gguf:
            parser.error("Do not export a smoke-test or probe adapter")
    if args.max_seq_length < 128 or args.epochs <= 0 or args.learning_rate <= 0:
        parser.error("Context length, epochs and learning rate must be positive")
    if args.prepare:
        prepare(args)
    elif args.check:
        report = verify_prepared(args.prepared, args.allow_overlength_exclusions)
        print(json.dumps(report["splits"], indent=2))
    else:
        train(args)


if __name__ == "__main__":
    main()
