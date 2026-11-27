"""Offline, company-isolated QLoRA with held-out loss evaluation.

Only approved plans become labels. An adapter is a candidate until separately
evaluated/promoted; training never changes deployed inference configuration.
"""
import argparse
import hashlib
import json
import os
import random
import time
from pathlib import Path


def export_examples(root):
    from app.company_learning import memory, SYSTEM
    from app.database_demo import sqlite_connection
    from app.erp_rules import quality, candidate_rules
    import tempfile
    examples = {}
    with memory() as db:
        plans = list(db.execute('SELECT digest,source,approved FROM plans WHERE approved IS NOT NULL ORDER BY created'))
    for plan in plans:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.sqlite'
            path.write_bytes(plan['source'])
            with sqlite_connection(path) as db:
                report = quality(db)
                candidates = {f'rule_{i:02d}': r.model_dump() for i, r in enumerate(candidate_rules(db, report), 1)}
        # Keep complete approved output; shortened metadata bounds training memory.
        issues = [{k: x[k] for k in ('table', 'column', 'counts', 'examples')} for x in report['issues']]
        approved = json.loads(plan['approved'])
        def identity(rule):
            return {k: v for k, v in rule.items() if k != 'reason'}
        selected = []
        for rule in approved:
            match = next((k for k, r in candidates.items() if identity(r) == identity(rule)), None)
            if match is None:
                # Steward corrections become explicit finite candidate rules as well.
                match = f'rule_{len(candidates)+1:02d}'
                candidates[match] = rule
            selected.append(match)
        user = json.dumps({'issues': issues, 'duplicate_candidates': report['duplicate_candidates'], 'orphan_invoices': report['orphan_invoices'],
                           'allowed_rules': candidates, 'approved_memory': [], 'company_context': {'business_rules': [], 'knowledge': []}})
        answer = json.dumps({'summary': 'Approved company transformations', 'selected_rule_ids': selected,
                             'risks': ['Retain unresolved findings for steward review.']})
        examples[plan['digest']] = {'source_sha256': plan['digest'], 'messages': [
            {'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}, {'role': 'assistant', 'content': answer}]}
    data = sorted(examples.values(), key=lambda x: x['source_sha256'])
    if len(data) < 5:
        raise ValueError('Need at least five distinct approved source databases for a held-out split')
    rng = random.Random(73)
    rng.shuffle(data)
    held_out = max(1, len(data) // 5)
    train, evaluation = data[held_out:], data[:held_out]
    root.mkdir(parents=True, exist_ok=True)
    for name, rows in [('train', train), ('evaluation', evaluation)]:
        (root / (name + '.jsonl')).write_text('\n'.join(json.dumps(x) for x in rows), encoding='utf-8')
    return train, evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-model', type=Path, required=True, help='Downloaded local HF directory; network disabled')
    parser.add_argument('--company-root', type=Path, required=True)
    parser.add_argument('--company', required=True)
    parser.add_argument('--steps', type=int, default=20)
    parser.add_argument('--max-length', type=int, default=2048)
    parser.add_argument('--export-only', action='store_true')
    args = parser.parse_args()
    os.environ['PRISM_COMPANY_ID'] = args.company
    os.environ['PRISM_COMPANY_ROOT'] = str(args.company_root.resolve())
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from app.company_learning import company_root
    company, root = company_root()
    stamp = time.strftime('%Y%m%d-%H%M%S')
    run = root / 'training' / stamp
    train, evaluation = export_examples(run)
    if args.export_only:
        print(json.dumps({'train': len(train), 'held_out': len(evaluation), 'directory': str(run)}))
        return
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, Trainer, TrainingArguments
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required for this QLoRA recipe')
    base = args.base_model.resolve()
    tokenizer = AutoTokenizer.from_pretrained(base, local_files_only=True)
    tokenizer.pad_token = tokenizer.eos_token
    torch.manual_seed(73)
    model = AutoModelForCausalLM.from_pretrained(base, local_files_only=True, device_map={'': 0},
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                                             bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16),
        torch_dtype=torch.float16, attn_implementation='sdpa')
    model.config.use_cache = False

    def encode(rows):
        result = []
        for row in rows:
            prompt = tokenizer.apply_chat_template(row['messages'][:-1], tokenize=False, add_generation_prompt=True)
            full = tokenizer.apply_chat_template(row['messages'], tokenize=False)
            prompt_ids = tokenizer(prompt, add_special_tokens=False)['input_ids']
            ids = tokenizer(full, add_special_tokens=False)['input_ids']
            if len(ids) > args.max_length:
                raise ValueError(f'Example has {len(ids)} tokens; increase --max-length rather than truncate labels')
            labels = [-100] * len(prompt_ids) + ids[len(prompt_ids):]
            result.append({'input_ids': ids, 'labels': labels, 'attention_mask': [1]*len(ids)})
        return result
    train_tokens, eval_tokens = encode(train), encode(evaluation)

    def collate(batch):
        width = max(len(x['input_ids']) for x in batch)
        return {key: torch.tensor([x[key] + [pad] * (width-len(x[key])) for x in batch])
                for key, pad in [('input_ids', tokenizer.pad_token_id), ('labels', -100), ('attention_mask', 0)]}

    def evaluate_loss():
        model.eval()
        losses = []
        with torch.no_grad():
            for item in eval_tokens:
                batch = {key: value.to(model.device) for key, value in collate([item]).items()}
                losses.append(float(model(**batch).loss))
        return sum(losses) / len(losses)

    base_loss = evaluate_loss()
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                          gradient_checkpointing_kwargs={'use_reentrant': False})
    model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05,
                                           target_modules=['q_proj', 'v_proj'], task_type='CAUSAL_LM'))
    model.print_trainable_parameters()
    trainer = Trainer(model=model, args=TrainingArguments(output_dir=str(run / 'checkpoints'), max_steps=args.steps,
        per_device_train_batch_size=1, gradient_accumulation_steps=1, learning_rate=1e-4,
        fp16=True, gradient_checkpointing=True, gradient_checkpointing_kwargs={'use_reentrant': False}, optim='adamw_torch', save_strategy='no',
        logging_steps=1, report_to=[], seed=73), train_dataset=train_tokens, data_collator=collate)
    started = time.perf_counter()
    trainer.train()
    adapted_loss = evaluate_loss()
    adapter = root / 'adapters' / stamp
    adapter.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(adapter)
    tokenizer.save_pretrained(adapter)
    report = {'company': company, 'base_model': str(base), 'base_config_sha256': hashlib.sha256((base/'config.json').read_bytes()).hexdigest(),
              'adapter': str(adapter), 'steps': args.steps, 'seconds': time.perf_counter()-started,
              'train_sources': len(train), 'held_out_sources': len(evaluation),
              'base_eval_loss': base_loss, 'adapter_eval_loss': adapted_loss,
              'peak_cuda_allocated_mb': torch.cuda.max_memory_allocated()/1024**2,
              'promoted': False, 'evaluation_limit': 'Held-out token loss on synthetic data; requires structured-output and semantic regression evaluation before promotion.'}
    (run/'evaluation.json').write_text(json.dumps(report, indent=2))
    (adapter/'prism-evaluation.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
