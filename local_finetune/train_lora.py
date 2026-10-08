"""LoRA fine-tune for Gemma 4 26B A4B or Qwen3.6 35B A3B.

Run this on the rented GPU after setup_remote.sh. On the desktop it only
checks that Unsloth imports, then exits. A 26B MoE LoRA does not fit in 8GB.
"""

import argparse
import json
import sys
from pathlib import Path

FAMILIES = {
    "gemma": {
        "model": "unsloth/gemma-4-26B-A4B-it",
        "template": "gemma-4-thinking",
        "instruction_part": "<|turn>user\n",
        "response_part": "<|turn>model\n",
        "quant": "q4_k_m",
        "load_in_16bit": True,
    },
    "qwen": {
        "model": "unsloth/Qwen3.6-35B-A3B",
        "template": "qwen-3",
        "instruction_part": "<|im_start|>user\n",
        "response_part": "<|im_start|>assistant\n",
        "quant": "q4_k_m",
        "load_in_16bit": True,
    },
}


def load_rows(path: Path) -> list:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if not rows:
        raise SystemExit(f"no rows in {path}")
    return rows


def conversations(rows: list) -> list:
    return [{"conversations": row["messages"]} for row in rows if row.get("messages")]


def train(family: str, dataset: Path, output: Path, max_steps: int, max_seq_length: int) -> None:
    spec = FAMILIES[family]
    try:
        from unsloth import FastModel
        from unsloth.chat_templates import get_chat_template, train_on_responses_only
        from trl import SFTConfig, SFTTrainer
    except Exception as exc:
        raise SystemExit(
            "Unsloth is not installed. This script is for the rented GPU. "
            f"Import error: {exc}"
        ) from exc

    rows = conversations(load_rows(dataset))
    model, tokenizer = FastModel.from_pretrained(
        model_name=spec["model"],
        max_seq_length=max_seq_length,
        load_in_4bit=False,
        load_in_16bit=spec["load_in_16bit"],
        full_finetuning=False,
    )
    model = FastModel.get_peft_model(
        model,
        r=16,
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        target_modules="all-linear",
        use_gradient_checkpointing="unsloth",
    )
    tokenizer = get_chat_template(tokenizer, chat_template=spec["template"])

    def formatting_prompts_func(examples):
        texts = []
        for convo in examples["conversations"]:
            rendered = tokenizer.apply_chat_template(
                convo,
                tokenize=False,
                add_generation_prompt=False,
            )
            texts.append(rendered.removeprefix("<bos>"))
        return {"text": texts}

    from datasets import Dataset

    dataset_obj = Dataset.from_list(rows)
    dataset_obj = dataset_obj.map(formatting_prompts_func, batched=True)
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset_obj,
        args=SFTConfig(
            dataset_text_field="text",
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            warmup_steps=5,
            max_steps=max_steps,
            learning_rate=2e-5,
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=3407,
            output_dir=str(output / "trainer"),
            report_to="none",
        ),
    )
    trainer = train_on_responses_only(
        trainer,
        instruction_part=spec["instruction_part"],
        response_part=spec["response_part"],
    )
    trainer.train()
    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output / "adapter"))
    tokenizer.save_pretrained(str(output / "adapter"))
    # Merged GGUF. This is Q4_K_M, not Gemma's original QAT UD-Q4_K_XL.
    model.save_pretrained_gguf(str(output / "gguf"), tokenizer, quantization_method=spec["quant"])
    print(f"wrote adapter and GGUF under {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=sorted(FAMILIES), required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--check", action="store_true", help="Validate the JSONL and exit.")
    args = parser.parse_args()
    load_rows(args.dataset)
    if args.check:
        print(f"ok: {args.family} dataset {args.dataset}")
        return
    train(args.family, args.dataset, args.output, args.max_steps, args.max_seq_length)


if __name__ == "__main__":
    main()
