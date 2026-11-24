"""Offline, opt-in LoRA/QLoRA fine-tuning for one company and one task.

This script deliberately does NOT run from the web process and does NOT
download model weights. Supply a local/cached base model path and a dataset
exported from ``GET /api/company-learning/{company_id}/dataset?task=...``.

Example:
    python scripts/train_company_lora.py \
      --dataset runtime/datasets/alpha-schema_mapping.json \
      --company alpha --task schema_mapping \
      --base-model C:/models/local-base \
      --output-dir runtime/company-models/alpha/schema_mapping/lora-v1 \
      --epochs 2 --4bit

The resulting artifact is a PEFT adapter, not a full model. PRISM's API
registers only a manifest for it; a human must review and approve before any
adapter is treated as an active company model.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

OPTIONAL_DEPS = ("torch", "transformers", "peft", "datasets")


def check_dependencies():
    missing = [name for name in OPTIONAL_DEPS if importlib.util.find_spec(name) is None]
    if missing:
        print("LoRA training is unavailable. Missing optional packages: " + ", ".join(missing))
        print("Install them explicitly from requirements-lora.txt in an offline-approved environment.")
        return False
    return True


def load_records(path: Path):
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
        records = payload["records"] if isinstance(payload, dict) else payload
    except json.JSONDecodeError:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    cleaned = []
    for record in records:
        if not all(key in record for key in ("instruction", "input", "output")):
            raise ValueError("Every dataset record needs instruction, input and output")
        cleaned.append({
            "instruction": str(record["instruction"])[:1000],
            "input": record["input"],
            "output": json.dumps(record["output"], sort_keys=True, separators=(",", ":")),
        })
    if not cleaned:
        raise ValueError("Dataset is empty")
    return cleaned


def render(record: dict) -> str:
    return (f"### Instruction:\n{record['instruction']}\n\n"
            f"### Input:\n{json.dumps(record['input'], sort_keys=True, ensure_ascii=False)}\n\n"
            f"### Response:\n{record['output']}\n")


def split_records(records, validation_fraction):
    """Deterministic split so the same dataset always yields the same holdout."""
    train, validation = [], []
    for record in records:
        digest = hashlib.sha256(json.dumps(record["input"], sort_keys=True).encode("utf-8")).digest()
        (validation if digest[0] / 255 < validation_fraction else train).append(record)
    if not validation:
        validation = train[-1:]
    if not train:
        train = validation[:]
    return train, validation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="JSON or JSONL dataset exported by PRISM")
    parser.add_argument("--company", required=True, help="Company slug; must match the dataset owner")
    parser.add_argument("--task", required=True, help="One PRISM learning task")
    parser.add_argument("--base-model", required=True, help="Local path or cached model id; no downloads")
    parser.add_argument("--output-dir", required=True, help="Directory for the PEFT adapter")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--target-modules", default="q_proj,v_proj")
    parser.add_argument("--4bit", action="store_true", dest="four_bit")
    args = parser.parse_args(argv)

    if not check_dependencies():
        return 2

    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              BitsAndBytesConfig, DataCollatorForLanguageModeling,
                              Trainer, TrainingArguments)

    tasks = ("schema_mapping", "exception_classification", "sap_object_mapping", "sql_conversion")
    if args.task not in tasks:
        parser.error("Unsupported task: " + args.task)
    if not 0.0 <= args.validation_fraction < 0.5:
        parser.error("--validation-fraction must be between 0 and 0.5")

    records = load_records(Path(args.dataset))
    train_records, validation_records = split_records(records, args.validation_fraction)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def encode(batch):
        return tokenizer([render(record) for record in batch], truncation=True,
                         max_length=args.max_length, padding="max_length")

    train_dataset = Dataset.from_list(train_records).map(
        encode, batched=True, remove_columns=["instruction", "input", "output"])
    validation_dataset = Dataset.from_list(validation_records).map(
        encode, batched=True, remove_columns=["instruction", "input", "output"])

    quantization = None
    if args.four_bit:
        quantization = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model, local_files_only=True, quantization_config=quantization,
        device_map="auto" if args.four_bit else None)
    if args.four_bit:
        model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        target_modules=[item.strip() for item in args.target_modules.split(",") if item.strip()],
        task_type="CAUSAL_LM",
    ))

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        logging_steps=10,
        save_strategy="epoch",
        report_to=[],
        seed=17,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )
    result = trainer.train()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    summary = {
        "format": "prism-company-lora-v1",
        "company": args.company,
        "task": args.task,
        "base_model": args.base_model,
        "local_files_only": True,
        "four_bit": bool(args.four_bit),
        "records": len(records),
        "train_records": len(train_records),
        "validation_records": len(validation_records),
        "train_loss": getattr(result, "training_loss", None),
        "dependencies": {name: getattr(sys.modules.get(name), "__version__", "unknown")
                         for name in OPTIONAL_DEPS},
        "status": "adapter-created-requires-human-review",
    }
    (output / "training_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
