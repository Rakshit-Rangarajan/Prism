# Company AI Training Pipeline

**Status:** implemented in `feature/company-llm-training`; synthetic-first, opt-in for everything external.

## What this actually is

PRISM now supports a **per-company learning workspace** covering four migration tasks:

| Task | Learns to predict |
|---|---|
| `schema_mapping` | source table/column → SAP target object, field mappings, transforms |
| `exception_classification` | error description → category, severity, remediation, evidence |
| `sap_object_mapping` | legacy entity → S/4 object, loading strategy, prerequisites |
| `sql_conversion` | legacy SQL dialect → target dialect, converted SQL, notes |

There are two training methods:

1. **`deterministic` (default).** A small feature-hashing centroid classifier trained locally on approved examples. It has learned parameters, a hold-out evaluation and a versioned artifact. **It is not an LLM and must not be described as one.**
2. **`lora` (opt-in).** A prepared dataset manifest plus an offline LoRA/QLoRA script (`scripts/train_company_lora.py`) that fine-tunes a *local/cached* causal LM into a PEFT adapter. The web API never downloads weights and never launches a GPU job.

Both methods are gated by approval: examples become retrievable/trainable only after `APPROVE TRAINING EXAMPLE`, and a candidate model becomes usable only after `APPROVE COMPANY MODEL`.

## Company isolation

- `companies` owns every artifact via `company_id`.
- All list/query/train/predict/artifact endpoints include `company_id` in their SQL predicate. There is no endpoint that accepts a caller-supplied owner for another company's data.
- A unique constraint prevents duplicate `(company_id, task, input_json)` examples.
- Only one active model exists per `(company_id, task)`; activating a new candidate retires the previous one.

The current shared Basic auth is still a demo credential. Company scoping is structural, but it is **not** a substitute for per-user identity and RBAC in a production deployment.

## Data sources

### Synthetic (default)

`POST /api/company-learning/{id}/bootstrap` generates 12 deterministic examples per task, seeded from the company slug. `POST /{id}/sources/synthetic` generates a bounded count for one task.

### Anonymized exports

`POST /{id}/sources/anonymized` accepts up to 200 records with `{task, input, output}`. Emails, phone numbers, IPv4 addresses and patterned identifiers are replaced with markers before storage, and the count of replacements is reported. Records remain drafts.

### Live database connections

`POST /{id}/sources/live` is disabled unless `PRISM_ENABLE_LIVE_DB_SOURCES=true`.

- The DSN is read from a **server environment variable** named in the request; it is never accepted in the request body or echoed back.
- Only `sqlite:///` paths beneath `PRISM_LIVE_DB_ROOT` are allowed.
- The connection uses SQLite `mode=ro` and reads **schema metadata only** (table names and column names). No row values are read.
- Generated examples carry `require_human_mapping_review` and remain drafts.

Other dialects are reported as unsupported rather than silently emulated.

## API quick reference

```text
GET    /api/company-learning/capabilities
GET    /api/company-learning/companies
POST   /api/company-learning/companies
POST   /api/company-learning/{id}/bootstrap
GET    /api/company-learning/{id}/overview
GET    /api/company-learning/{id}/sources
POST   /api/company-learning/{id}/sources/synthetic       {"task","count"}
POST   /api/company-learning/{id}/sources/anonymized     {"name","records":[...]}
POST   /api/company-learning/{id}/sources/live           {"name","dsn_env_var"}
GET    /api/company-learning/{id}/examples?task=&state=
POST   /api/company-learning/{id}/examples/{eid}/approve {"confirmation":"APPROVE TRAINING EXAMPLE"}
POST   /api/company-learning/{id}/rag/query              {"task","query","limit"}
GET    /api/company-learning/{id}/dataset?task=
POST   /api/company-learning/{id}/train                  {"task","method","epochs"}
GET    /api/company-learning/{id}/runs
GET    /api/company-learning/{id}/models
POST   /api/company-learning/{id}/models/{mid}/approve   {"confirmation":"APPROVE COMPANY MODEL"}
GET    /api/company-learning/{id}/models/{mid}/artifact
POST   /api/company-learning/{id}/predict                {"task","input":{...}}
```

All routes require the same Basic auth as the rest of the demo API.

## Retrieval

Approved examples are indexed with a 512-bucket signed feature hash. `rag/query` returns cosine-ranked approved examples with a `deterministic-hash-embedding` label. This is lexical/feature-hash retrieval, **not** neural semantic search and not a vector database.

## Training and evaluation

- Deterministic split: 1 in 5 approved examples is a hold-out (fallback to training set if none), so results are reproducible.
- Artifacts are written atomically to `PRISM_MODEL_ARTIFACT_ROOT` (default `runtime/company-models`), under `company-slug/task/`.
- Metrics include hold-out accuracy, train/hold-out counts, label count, epochs and `is_llm: false` for the default method.
- `predict` uses the active model plus up to two supporting approved examples. With no active model it returns `mode: "rag-only"` and an explicit warning.

## True LoRA fine-tuning (offline)

1. Export approved records: `GET /api/company-learning/{id}/dataset?task=schema_mapping` → save as JSON.
2. Install `requirements-lora.txt` in an approved offline environment with a local/cached base model.
3. Run:

```bash
python scripts/train_company_lora.py \
  --dataset alpha-schema_mapping.json --company alpha --task schema_mapping \
  --base-model C:/models/local-base \
  --output-dir runtime/company-models/alpha/schema_mapping/lora-v1 \
  --epochs 2 --4bit
```

4. The script writes a PEFT adapter and `training_summary.json`. It exits with code 2 and a clear message if any optional package is missing. It calls `from_pretrained(..., local_files_only=True)` and makes no download attempt.
5. A human must review the adapter before it is deployed. The API's `method=lora` train call only creates a **manifest** (`status: prepared`) or a `blocked` run when packages are absent; it does not claim an LLM was trained.

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `PRISM_LEARNING_DB` | isolated SQLite for learning artifacts | server `PRISM_DB` |
| `PRISM_MODEL_ARTIFACT_ROOT` | model artifact directory | `runtime/company-models` |
| `PRISM_ENABLE_LIVE_DB_SOURCES` | enables read-only live schema sources | `false` |
| `PRISM_LIVE_DB_ROOT` | allow-listed root for live SQLite paths | `runtime/live-db` |

## Known limitations

- Shared Basic credential; no per-user approver identity or RBAC.
- Company isolation is by explicit ID, not authenticated tenant principal.
- No vector database, embedding model download, or semantic similarity.
- Small hold-out sets; accuracy is a demo signal, not a production quality gate.
- LoRA script trains on full instruction text (no completion-only masking) and uses fixed target modules by default; adapt `--target-modules` for other architectures.
- No external database write-back, SAP connection, or production data path.

## Tests

`tests/test_company_learning.py` covers capabilities, auth, company CRUD, synthetic bootstrap, approval gating, cross-company isolation, training/evaluation/activation, prediction provenance, PII scrubbing, read-only live schema introspection, path containment, LoRA preflight and dataset export. `frontend/tests/learning-engine.test.mjs` covers the UI helpers.
