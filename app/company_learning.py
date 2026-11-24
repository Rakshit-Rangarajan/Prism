"""Company-scoped learning pipeline for database migration assistance.

Design boundaries (important):

* Every artifact is scoped by an explicit ``company_id``. No cross-company
  query path exists; scope is part of the SQL predicate, not a display filter.
* The default trainer is a small, deterministic feature-hashing classifier
  trained locally on approved examples. It is a genuine learned model, but it
  is NOT a Transformer/LLM. True LoRA fine-tuning is opt-in, runs offline via
  ``scripts/train_company_lora.py``, and never downloads weights implicitly.
* Live database access is read-only schema introspection, disabled unless
  ``PRISM_ENABLE_LIVE_DB_SOURCES=true``. Connection strings are read only from
  server environment variables, never from request bodies or logs.
* Synthetic data is the default. Any supplied records are PII-scrubbed before
  storage and remain drafts until explicitly approved.
"""
import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .server import DB, require_user

router = APIRouter(
    prefix="/api/company-learning",
    tags=["Company AI Training"],
    dependencies=[Depends(require_user)],
)

TASKS = (
    "schema_mapping",
    "exception_classification",
    "sap_object_mapping",
    "sql_conversion",
)
METHODS = ("deterministic", "lora")
BUCKETS = 512
APPROVE_EXAMPLE_CONFIRMATION = "APPROVE TRAINING EXAMPLE"
APPROVE_MODEL_CONFIRMATION = "APPROVE COMPANY MODEL"
MAX_CANONICAL_CHARS = 8000

TASK_INSTRUCTIONS = {
    "schema_mapping": "Map legacy database tables and columns to the target SAP object, field names and transforms.",
    "exception_classification": "Classify a migration error and recommend the approved remediation and evidence source.",
    "sap_object_mapping": "Recommend the SAP S/4HANA object, loading strategy and prerequisites for a legacy entity.",
    "sql_conversion": "Convert a legacy SQL dialect expression into the target database dialect, preserving semantics.",
}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _db_path() -> str:
    return os.getenv("PRISM_LEARNING_DB", DB)


@contextmanager
def connection():
    """Explicit open/commit/close; Windows cannot cleanly close GC'd SQLite handles."""
    path = Path(_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def ensure_schema(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS companies (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      slug TEXT NOT NULL UNIQUE,
      description TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS learning_sources (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      company_id INTEGER NOT NULL REFERENCES companies(id),
      kind TEXT NOT NULL CHECK(kind IN ('synthetic','anonymized_export','live_schema')),
      name TEXT NOT NULL,
      metadata_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS learning_examples (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      company_id INTEGER NOT NULL REFERENCES companies(id),
      source_id INTEGER REFERENCES learning_sources(id),
      task TEXT NOT NULL,
      input_json TEXT NOT NULL,
      output_json TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','approved','rejected')),
      scrubbed_count INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      reviewed_at TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS learning_example_unique
      ON learning_examples(company_id,task,input_json);
    CREATE INDEX IF NOT EXISTS learning_example_scope
      ON learning_examples(company_id,task,state);
    CREATE TABLE IF NOT EXISTS rag_index (
      example_id INTEGER PRIMARY KEY REFERENCES learning_examples(id),
      company_id INTEGER NOT NULL,
      task TEXT NOT NULL,
      embedding_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS rag_scope ON rag_index(company_id,task);
    CREATE TABLE IF NOT EXISTS training_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      company_id INTEGER NOT NULL,
      task TEXT NOT NULL,
      method TEXT NOT NULL,
      status TEXT NOT NULL,
      config_json TEXT NOT NULL,
      metrics_json TEXT NOT NULL DEFAULT '{}',
      artifact_path TEXT,
      error TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      finished_at TEXT
    );
    CREATE INDEX IF NOT EXISTS training_run_scope ON training_runs(company_id,task);
    CREATE TABLE IF NOT EXISTS company_models (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      company_id INTEGER NOT NULL,
      task TEXT NOT NULL,
      run_id INTEGER NOT NULL,
      version INTEGER NOT NULL,
      metrics_json TEXT NOT NULL,
      artifact_path TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'candidate' CHECK(state IN ('candidate','active','retired')),
      approved_at TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE UNIQUE INDEX IF NOT EXISTS one_active_model_per_scope
      ON company_models(company_id,task) WHERE state='active';
    CREATE INDEX IF NOT EXISTS model_scope ON company_models(company_id,task,state);
    """)


def _company(c, company_id: int) -> dict:
    row = c.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Company not found")
    return dict(row)


def _validate_task(task: str) -> str:
    if task not in TASKS:
        raise HTTPException(422, "Unsupported task: " + task[:60])
    return task


def _canonical(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(text) > MAX_CANONICAL_CHARS:
        raise HTTPException(422, "Example payload too large (8000 character limit per field)")
    return text


# ---------------------------------------------------------------------------
# Privacy and deterministic embeddings
# ---------------------------------------------------------------------------

_PII_PATTERNS = (
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "<EMAIL>"),
    (re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b"), "<PHONE>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<IP_ADDRESS>"),
    (re.compile(r"\b[A-Z]{2}\d{6,}\b"), "<IDENTIFIER>"),
)


def _scrub_text(text: str) -> tuple[str, int]:
    total = 0
    for pattern, replacement in _PII_PATTERNS:
        text, count = pattern.subn(replacement, text)
        total += count
    return text, total


def _scrub(value: Any, counter: list[int]) -> Any:
    if isinstance(value, str):
        cleaned, count = _scrub_text(value)
        counter[0] += count
        return cleaned
    if isinstance(value, list):
        return [_scrub(item, counter) for item in value[:100]]
    if isinstance(value, dict):
        return {str(key)[:80]: _scrub(item, counter)
                for key, item in list(value.items())[:80]}
    return value


def _scrub_example(value: dict) -> tuple[dict, int]:
    counter = [0]
    return _scrub(value, counter), counter[0]


def _tokens(text: Any) -> list[str]:
    if not isinstance(text, str):
        text = _canonical(text)
    return [token for token in re.findall(r"[a-z0-9_]+", text.casefold()) if len(token) > 1]


def _vector(text: str) -> dict[int, float]:
    """Signed feature hashing into a fixed-width sparse unit vector."""
    vector: dict[int, float] = defaultdict(float)
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        number = int.from_bytes(digest, "big")
        vector[number % BUCKETS] += 1.0 if number & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if not norm:
        return {}
    return {key: round(value / norm, 6) for key, value in vector.items() if value}


def _normalize(vector: dict[int, float]) -> dict[int, float]:
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if not norm:
        return {}
    return {k: round(v / norm, 6) for k, v in vector.items() if abs(v) >= 1e-4}


def _cosine(left: dict, right: dict) -> float:
    if not left or not right:
        return 0.0
    # JSON round-trips turn integer bucket keys into strings. Normalize both
    # sides so persisted artifacts and fresh vectors compare identically.
    small = {str(key): value for key, value in left.items()}
    large = {str(key): value for key, value in right.items()}
    if len(small) > len(large):
        small, large = large, small
    return round(sum(value * large.get(key, 0.0) for key, value in small.items()), 6)


def _scores(vector: dict[int, float], centroids: dict) -> dict[str, float]:
    return {label: _cosine(vector, data["vector"]) for label, data in centroids.items()}


def _argmax(scores: dict[str, float]) -> str:
    return max(sorted(scores), key=lambda label: scores[label]) if scores else ""


# ---------------------------------------------------------------------------
# Synthetic example generation (seeded per company, no network)
# ---------------------------------------------------------------------------

def _synthetic_pair(task: str, index: int, slug: str) -> tuple[dict, dict]:
    record_id = f"SYN-{slug[:8]}-{index:03d}"
    variants = index % 4
    if task == "schema_mapping":
        sources = [
            ({"source_system": "LEGACY_ERP", "source_table": "VEND_MAST",
              "columns": ["VEND_ID", "VEND_NM", "VEND_AMT"],
              "samples": {"VEND_NM": "acme industrial ltd", "VEND_AMT": "$1,234.56"}},
             {"target_object": "BUSINESS_PARTNER", "target_table": "BP_MASTER",
              "field_mappings": [{"source": "VEND_ID", "target": "BP_ID", "transform": "trim"},
                                 {"source": "VEND_NM", "target": "NAME1", "transform": "upper"},
                                 {"source": "VEND_AMT", "target": "OPEN_AMOUNT", "transform": "currency_normalize"}],
              "rules": ["validate_currency", "require_approved_crosswalk"]}),
            ({"source_system": "LEGACY_CRM", "source_table": "CUST_MAST",
              "columns": ["CUST_ID", "CUST_EMAIL", "CUST_STATUS"],
              "samples": {"CUST_EMAIL": "buyer@example.invalid", "CUST_STATUS": "A"}},
             {"target_object": "BUSINESS_PARTNER", "target_table": "BP_MASTER",
              "field_mappings": [{"source": "CUST_ID", "target": "BP_ID", "transform": "trim"},
                                 {"source": "CUST_EMAIL", "target": "SMTP_ADDR", "transform": "validate_email"},
                                 {"source": "CUST_STATUS", "target": "BP_STATUS", "transform": "status_crosswalk"}],
              "rules": ["duplicate_check", "require_steward_review"]}),
            ({"source_system": "PLANT_SYSTEM", "source_table": "MATL_T",
              "columns": ["MATL_NO", "MATL_DESC", "BASE_UOM"],
              "samples": {"MATL_DESC": "bearing 6204-2rs", "BASE_UOM": "EA"}},
             {"target_object": "PRODUCT", "target_table": "MATERIAL_MASTER",
              "field_mappings": [{"source": "MATL_NO", "target": "MATNR", "transform": "trim_pad"},
                                 {"source": "MATL_DESC", "target": "MTXZL", "transform": "upper_trim"},
                                 {"source": "BASE_UOM", "target": "MEINS", "transform": "uom_crosswalk"}],
              "rules": ["validate_uom", "check_description_length"]}),
            ({"source_system": "LEGACY_GL", "source_table": "GL_ACCT",
              "columns": ["ACCT_NO", "ACCT_DESC", "COST_CTR"],
              "samples": {"ACCT_DESC": "office supplies", "COST_CTR": "CC-1000"}},
             {"target_object": "GL_ACCOUNT", "target_table": "S4_GL_ACCOUNT",
              "field_mappings": [{"source": "ACCT_NO", "target": "SAKNR", "transform": "trim_pad"},
                                 {"source": "ACCT_DESC", "target": "TXT50", "transform": "title_case"},
                                 {"source": "COST_CTR", "target": "KOSTL", "transform": "cost_centre_crosswalk"}],
              "rules": ["chart_of_accounts_validation", "require_finance_approval"]}),
        ]
        source, output = sources[variants]
        source = dict(source)
        source["record_id"] = record_id
        return source, output
    if task == "exception_classification":
        cases = [
            ({"object": "SUPPLIER", "domain": "Vendor", "error_message": "Missing reconciliation account for vendor",
              "legacy_code": "DB-014"},
             {"category": "missing_configuration", "severity": "critical",
              "recommended_action": "Map reconciliation account using the approved chart of accounts and finance review.",
              "evidence": "SYN-REC-ACCOUNT"}),
            ({"object": "PRODUCT", "domain": "Material", "error_message": "Invalid base unit of measure",
              "legacy_code": "DB-021"},
             {"category": "invalid_reference_data", "severity": "high",
              "recommended_action": "Apply the approved UOM crosswalk and validate in staging.",
              "evidence": "SYN-UOM-CROSSWALK"}),
            ({"object": "BUSINESS_PARTNER", "domain": "Customer", "error_message": "Potential duplicate customer candidate",
              "legacy_code": "DB-037"},
             {"category": "duplicate_candidate", "severity": "medium",
              "recommended_action": "Escalate to a data steward; do not auto-merge.",
              "evidence": "SYN-DUP-POLICY"}),
            ({"object": "GL_ACCOUNT", "domain": "Finance", "error_message": "Cost centre not found in target",
              "legacy_code": "DB-052"},
             {"category": "missing_cross_reference", "severity": "critical",
              "recommended_action": "Load approved cost-centre mapping before retrying the GL batch.",
              "evidence": "SYN-COST-CENTRE"}),
        ]
        source, output = cases[variants]
        return dict(source, record_id=record_id), output
    if task == "sap_object_mapping":
        cases = [
            ({"legacy_entity": "VEND_MAST", "process": "procurement", "fields": ["VEND_ID", "VEND_NM"]},
             {"sap_object": "BUSINESS_PARTNER", "s4_transition_object": "SUPPLIER",
              "loading_strategy": "Migration Cockpit with staged BP templates",
              "prerequisites": ["BP number range", "reconciliation account", "tax crosswalk"]}),
            ({"legacy_entity": "CUST_MAST", "process": "order_to_cash", "fields": ["CUST_ID", "CUST_EMAIL"]},
             {"sap_object": "BUSINESS_PARTNER", "s4_transition_object": "CUSTOMER",
              "loading_strategy": "Migration Cockpit with BP + company-code extensions",
              "prerequisites": ["duplicate check", "company code assignment", "payment terms"]}),
            ({"legacy_entity": "MATL_T", "process": "inventory", "fields": ["MATL_NO", "BASE_UOM"]},
             {"sap_object": "PRODUCT", "s4_transition_object": "MATERIAL",
              "loading_strategy": "Migration Cockpit material template, staging first",
              "prerequisites": ["UOM crosswalk", "valuation area", "description length validation"]}),
            ({"legacy_entity": "GL_ACCT", "process": "record_to_report", "fields": ["ACCT_NO", "COST_CTR"]},
             {"sap_object": "GL_ACCOUNT", "s4_transition_object": "GL_ACCOUNT",
              "loading_strategy": "Migration Cockpit GL account template with finance approval",
              "prerequisites": ["chart of accounts", "cost centre mapping", "field status group"]}),
        ]
        source, output = cases[variants]
        return dict(source, record_id=record_id), output
    cases = [
        ({"dialect": "oracle", "sql": "SELECT NVL(discount,0) FROM orders"},
         {"target_dialect": "postgresql", "converted_sql": "SELECT COALESCE(discount,0) FROM orders",
          "notes": ["NVL maps to COALESCE"]}),
        ({"dialect": "mssql", "sql": "SELECT TOP 10 customer_id FROM orders"},
         {"target_dialect": "postgresql", "converted_sql": "SELECT customer_id FROM orders LIMIT 10",
          "notes": ["TOP maps to LIMIT", "preserve deterministic ORDER BY in production"]}),
        ({"dialect": "oracle", "sql": "SELECT SYSDATE FROM dual"},
         {"target_dialect": "postgresql", "converted_sql": "SELECT CURRENT_TIMESTAMP",
          "notes": ["SYSDATE maps to CURRENT_TIMESTAMP", "dual table removed"]}),
        ({"dialect": "oracle", "sql": "SELECT DECODE(status,'A',1,0) FROM orders"},
         {"target_dialect": "postgresql", "converted_sql": "SELECT CASE WHEN status='A' THEN 1 ELSE 0 END FROM orders",
          "notes": ["DECODE maps to CASE"]}),
    ]
    source, output = cases[variants]
    return dict(source, record_id=record_id), output


def _add_examples(c, company_id: int, source_id: int, task: str,
                  pairs: list[tuple[dict, dict]]) -> int:
    created = 0
    for source_value, output_value in pairs:
        clean_input, scrubbed = _scrub_example(source_value)
        clean_output, output_scrubbed = _scrub_example(output_value)
        cursor = c.execute(
            """INSERT OR IGNORE INTO learning_examples
               (company_id,source_id,task,input_json,output_json,scrubbed_count)
               VALUES(?,?,?,?,?,?)""",
            (company_id, source_id, task, _canonical(clean_input),
             _canonical(clean_output), scrubbed + output_scrubbed),
        )
        created += cursor.rowcount
    return created


# ---------------------------------------------------------------------------
# Training and evaluation
# ---------------------------------------------------------------------------

def _model_root() -> Path:
    return Path(os.getenv("PRISM_MODEL_ARTIFACT_ROOT", "runtime/company-models")).resolve()


def _write_artifact(company_id: int, slug: str, task: str, method: str,
                    run_id: int, payload: dict) -> str:
    directory = _model_root() / _safe_component(slug) / _safe_component(task)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{method}-{run_id}.json"
    temporary = directory / f"{method}-{run_id}.tmp"
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)
    return str(target)


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)[:60]


def train_deterministic(examples: list[dict], epochs: int) -> tuple[dict, dict]:
    """Train a sparse centroid classifier; return artifact and evaluation metrics."""
    groups: dict[str, list[dict[int, float]]] = defaultdict(list)
    for example in examples:
        groups[example["label"]].append(_vector(example["input"]))

    centroids: dict[str, dict] = {}
    for label, vectors in groups.items():
        accumulator: dict[int, float] = defaultdict(float)
        for vector in vectors:
            for key, value in vector.items():
                accumulator[key] += value
        count = len(vectors) or 1
        centroids[label] = {
            "vector": _normalize({key: value / count for key, value in accumulator.items()}),
            "count": count,
        }

    train, holdout = [], []
    for example in examples:
        digest = hashlib.sha256(
            (str(example["id"]) + "|" + example["label"]).encode("utf-8")
        ).digest()
        (holdout if digest[0] % 5 == 0 else train).append(example)
    holdout_fallback = not holdout
    if holdout_fallback:
        holdout = train[:]
    if not train:
        train = holdout[:]

    for _ in range(epochs):
        for example in train:
            vector = _vector(example["input"])
            predicted = _argmax(_scores(vector, centroids))
            if predicted == example["label"] and _cosine(vector, centroids[predicted]["vector"]) >= 0.30:
                continue
            target = centroids[example["label"]]["vector"]
            keys = set(target) | set(vector)
            updated = {key: target.get(key, 0.0) + 0.25 * (vector.get(key, 0.0) - target.get(key, 0.0))
                       for key in keys}
            centroids[example["label"]]["vector"] = _normalize(updated)

    correct = sum(
        1 for example in holdout
        if _argmax(_scores(_vector(example["input"]), centroids)) == example["label"]
    )
    metrics = {
        "method": "deterministic",
        "accuracy": round(correct / len(holdout), 4) if holdout else 0.0,
        "train_examples": len(train),
        "holdout_examples": len(holdout),
        "holdout_fallback": holdout_fallback,
        "labels": len(centroids),
        "epochs": epochs,
        "buckets": BUCKETS,
        "is_llm": False,
    }
    artifact = {"format": "prism-deterministic-v1", "buckets": BUCKETS, "centroids": centroids}
    return artifact, metrics


def predict_deterministic(artifact: dict, input_value: dict) -> dict:
    vector = _vector(_canonical(input_value))
    scores = _scores(vector, artifact["centroids"])
    ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    if not ranked:
        return {"prediction": {}, "confidence": 0.0, "alternatives": []}
    winner, confidence = ranked[0]
    return {
        "prediction": json.loads(winner),
        "confidence": confidence,
        "alternatives": [{"label": label, "score": score} for label, score in ranked[1:4]],
    }


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,48}$")
    description: str = Field(default="", max_length=300)


class SyntheticSourceIn(BaseModel):
    task: str
    count: int = Field(default=12, ge=4, le=60)


class RecordIn(BaseModel):
    task: str
    input: dict[str, Any]
    output: dict[str, Any]


class IngestIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    records: list[RecordIn] = Field(min_length=1, max_length=200)


class LiveSourceIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    dsn_env_var: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")


class ConfirmationIn(BaseModel):
    confirmation: str


class RagIn(BaseModel):
    task: str
    query: str = Field(min_length=2, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)


class TrainIn(BaseModel):
    task: str
    method: str = Field(default="deterministic")
    epochs: int = Field(default=3, ge=1, le=20)


class PredictIn(BaseModel):
    task: str
    input: dict[str, Any]


# ---------------------------------------------------------------------------
# Company and source endpoints
# ---------------------------------------------------------------------------

@router.get("/capabilities")
def capabilities():
    optional = {name: importlib.util.find_spec(name) is not None
                for name in ("torch", "transformers", "peft", "datasets")}
    return {
        "tasks": list(TASKS),
        "methods": list(METHODS),
        "default_method": "deterministic",
        "default_method_is_llm": False,
        "live_db_sources_enabled": os.getenv("PRISM_ENABLE_LIVE_DB_SOURCES", "false").lower() == "true",
        "live_db_scheme": "sqlite:/// (read-only schema introspection)",
        "optional_lora_dependencies": optional,
        "note": "LoRA fine-tuning is an offline opt-in script; no weights are downloaded by the API.",
    }


@router.get("/companies")
def list_companies():
    with connection() as c:
        ensure_schema(c)
        rows = [dict(row) for row in c.execute("SELECT * FROM companies ORDER BY id")]
        for row in rows:
            row["examples"] = c.execute(
                "SELECT COUNT(*) FROM learning_examples WHERE company_id=?", (row["id"],)
            ).fetchone()[0]
            row["approved_examples"] = c.execute(
                "SELECT COUNT(*) FROM learning_examples WHERE company_id=? AND state='approved'", (row["id"],)
            ).fetchone()[0]
            row["active_models"] = c.execute(
                "SELECT COUNT(*) FROM company_models WHERE company_id=? AND state='active'", (row["id"],)
            ).fetchone()[0]
        return rows


@router.post("/companies", status_code=201)
def create_company(payload: CompanyIn):
    with connection() as c:
        ensure_schema(c)
        try:
            cursor = c.execute(
                "INSERT INTO companies(name,slug,description) VALUES(?,?,?)",
                (payload.name, payload.slug, payload.description),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Company slug already exists")
        return {"id": cursor.lastrowid, "slug": payload.slug, "state": "created"}


@router.get("/{company_id}/overview")
def overview(company_id: int):
    with connection() as c:
        ensure_schema(c)
        company = _company(c, company_id)
        return {
            "company": company,
            "sources": c.execute(
                "SELECT COUNT(*) FROM learning_sources WHERE company_id=?", (company_id,)
            ).fetchone()[0],
            "examples_by_task": {
                task: {
                    "approved": c.execute(
                        "SELECT COUNT(*) FROM learning_examples WHERE company_id=? AND task=? AND state='approved'",
                        (company_id, task),
                    ).fetchone()[0],
                    "draft": c.execute(
                        "SELECT COUNT(*) FROM learning_examples WHERE company_id=? AND task=? AND state='draft'",
                        (company_id, task),
                    ).fetchone()[0],
                }
                for task in TASKS
            },
            "runs": c.execute(
                "SELECT COUNT(*) FROM training_runs WHERE company_id=?", (company_id,)
            ).fetchone()[0],
            "active_models": c.execute(
                "SELECT COUNT(*) FROM company_models WHERE company_id=? AND state='active'", (company_id,)
            ).fetchone()[0],
        }


@router.get("/{company_id}/sources")
def list_sources(company_id: int):
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        return [dict(row) for row in c.execute(
            "SELECT id,kind,name,metadata_json,created_at FROM learning_sources WHERE company_id=? ORDER BY id",
            (company_id,),
        )]


@router.post("/{company_id}/sources/synthetic", status_code=201)
def add_synthetic_source(company_id: int, payload: SyntheticSourceIn):
    task = _validate_task(payload.task)
    with connection() as c:
        ensure_schema(c)
        company = _company(c, company_id)
        slug = company["slug"]
        seed = int.from_bytes(hashlib.sha256(slug.encode("utf-8")).digest()[:4], "big")
        pairs = [_synthetic_pair(task, (seed + offset) % 240, slug) for offset in range(payload.count)]
        cursor = c.execute(
            """INSERT INTO learning_sources(company_id,kind,name,metadata_json)
               VALUES(?,?,?,?)""",
            (company_id, "synthetic", f"Synthetic {task} ({payload.count})",
             json.dumps({"synthetic": True, "seed": seed, "task": task})),
        )
        created = _add_examples(c, company_id, cursor.lastrowid, task, pairs)
        return {"source_id": cursor.lastrowid, "task": task, "examples_created": created,
                "drafts_require_approval": True, "synthetic": True}


@router.post("/{company_id}/sources/anonymized", status_code=201)
def add_anonymized_source(company_id: int, payload: IngestIn):
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        grouped: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
        scrubbed_total = 0
        for record in payload.records:
            task = _validate_task(record.task)
            clean_input, first = _scrub_example(record.input)
            clean_output, second = _scrub_example(record.output)
            scrubbed_total += first + second
            grouped[task].append((clean_input, clean_output))
        cursor = c.execute(
            """INSERT INTO learning_sources(company_id,kind,name,metadata_json)
               VALUES(?,?,?,?)""",
            (company_id, "anonymized_export", payload.name,
             json.dumps({"scrubbed_values": scrubbed_total, "records": len(payload.records)})),
        )
        created = sum(_add_examples(c, company_id, cursor.lastrowid, task, pairs)
                      for task, pairs in grouped.items())
        return {"source_id": cursor.lastrowid, "records_received": len(payload.records),
                "examples_created": created, "scrubbed_values": scrubbed_total,
                "drafts_require_approval": True}


@router.post("/{company_id}/sources/live", status_code=201)
def add_live_source(company_id: int, payload: LiveSourceIn):
    if os.getenv("PRISM_ENABLE_LIVE_DB_SOURCES", "false").lower() != "true":
        raise HTTPException(503, "Live database sources are disabled; set PRISM_ENABLE_LIVE_DB_SOURCES=true")
    dsn = os.getenv(payload.dsn_env_var)
    if not dsn:
        raise HTTPException(422, "Configured DSN environment variable is not set on the server")
    if not dsn.startswith("sqlite:///"):
        raise HTTPException(422, "This phase implements read-only sqlite:/// schema introspection only")
    root = Path(os.getenv("PRISM_LIVE_DB_ROOT", "runtime/live-db")).resolve()
    candidate = Path(dsn[len("sqlite:///"):]).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(422, "Database path is outside the permitted read-only root")
    if not candidate.is_file():
        raise HTTPException(404, "Database file not found")

    read_only = sqlite3.connect(f"file:{candidate.as_posix()}?mode=ro", uri=True)
    try:
        tables = [row[0] for row in read_only.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        pairs: list[tuple[dict, dict]] = []
        schema: dict[str, list[str]] = {}
        for table in tables[:50]:
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [row[1] for row in read_only.execute(f"PRAGMA table_info({quoted})")]
            schema[table] = columns[:60]
            target = "PRODUCT" if any("MAT" in col.upper() for col in columns) else "BUSINESS_PARTNER"
            pairs.append((
                {"source_system": "live_sqlite", "source_table": table,
                 "columns": columns[:60], "samples": {}, "record_id": f"LIVE-{table[:24]}"},
                {"target_object": target, "target_table": target + "_MASTER",
                 "field_mappings": [{"source": col, "target": col.upper(), "transform": "review_required"}
                                    for col in columns[:12]],
                 "rules": ["read_only_schema_introspection", "require_human_mapping_review"]},
            ))
    finally:
        read_only.close()

    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        cursor = c.execute(
            """INSERT INTO learning_sources(company_id,kind,name,metadata_json)
               VALUES(?,?,?,?)""",
            (company_id, "live_schema", payload.name,
             json.dumps({"read_only": True, "tables": list(schema), "dsn_disclosed": False})),
        )
        created = _add_examples(c, company_id, cursor.lastrowid, "schema_mapping", pairs)
        return {"source_id": cursor.lastrowid, "read_only": True, "tables": list(schema),
                "examples_created": created, "drafts_require_approval": True,
                "note": "Schema metadata only; no row values were read."}


# ---------------------------------------------------------------------------
# Examples, approval and retrieval
# ---------------------------------------------------------------------------

@router.get("/{company_id}/examples")
def list_examples(company_id: int, task: str = Query(default="", max_length=60),
                  state: str = Query(default="", max_length=20),
                  limit: int = Query(default=50, ge=1, le=200)):
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        sql = "SELECT * FROM learning_examples WHERE company_id=?"
        params: list[Any] = [company_id]
        if task:
            sql += " AND task=?"
            params.append(_validate_task(task))
        if state:
            if state not in ("draft", "approved", "rejected"):
                raise HTTPException(422, "Invalid state")
            sql += " AND state=?"
            params.append(state)
        rows = [dict(row) for row in c.execute(
            sql + " ORDER BY id DESC LIMIT ?", params + [limit])]
        for row in rows:
            row["input"] = json.loads(row.pop("input_json"))
            row["output"] = json.loads(row.pop("output_json"))
        return rows


@router.post("/{company_id}/examples/{example_id}/approve")
def approve_example(company_id: int, example_id: int, payload: ConfirmationIn):
    if payload.confirmation != APPROVE_EXAMPLE_CONFIRMATION:
        raise HTTPException(422, "Explicit training-example confirmation required")
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        row = c.execute(
            "SELECT * FROM learning_examples WHERE id=? AND company_id=?", (example_id, company_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Example not found for this company")
        if row["state"] == "approved":
            return {"id": example_id, "state": "approved", "already_approved": True}
        if row["state"] != "draft":
            raise HTTPException(409, "Only draft examples can be approved")
        c.execute(
            "UPDATE learning_examples SET state='approved',reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
            (example_id,),
        )
        text = row["input_json"] + " " + row["output_json"]
        c.execute(
            """INSERT OR REPLACE INTO rag_index(example_id,company_id,task,embedding_json)
               VALUES(?,?,?,?)""",
            (example_id, company_id, row["task"], json.dumps(_vector(text))),
        )
        return {"id": example_id, "state": "approved", "task": row["task"]}


@router.post("/{company_id}/rag/query")
def rag_query(company_id: int, payload: RagIn):
    task = _validate_task(payload.task)
    query_vector = _vector(payload.query)
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        rows = c.execute(
            """SELECT e.id,e.input_json,e.output_json,r.embedding_json
               FROM rag_index r JOIN learning_examples e ON e.id=r.example_id
               WHERE r.company_id=? AND r.task=? AND e.state='approved'""",
            (company_id, task),
        ).fetchall()
        scored = []
        for row in rows:
            score = _cosine(query_vector, json.loads(row["embedding_json"]))
            if score > 0:
                scored.append({
                    "id": row["id"],
                    "input": json.loads(row["input_json"]),
                    "output": json.loads(row["output_json"]),
                    "score": score,
                })
        scored.sort(key=lambda item: (-item["score"], item["id"]))
        return {
            "company_id": company_id,
            "task": task,
            "retrieval": "deterministic-hash-embedding",
            "approved_only": True,
            "results": scored[:payload.limit],
            "warning": "Lexical/hash retrieval over approved examples; not neural semantic search.",
        }


@router.get("/{company_id}/dataset")
def export_dataset(company_id: int, task: str = Query(default="", max_length=60)):
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        sql = "SELECT task,input_json,output_json FROM learning_examples WHERE company_id=? AND state='approved'"
        params: list[Any] = [company_id]
        if task:
            sql += " AND task=?"
            params.append(_validate_task(task))
        rows = [dict(row) for row in c.execute(sql + " ORDER BY id", params)]
        records = [{
            "instruction": TASK_INSTRUCTIONS[row["task"]],
            "input": json.loads(row["input_json"]),
            "output": json.loads(row["output_json"]),
        } for row in rows]
        return {"company_id": company_id, "task": task or "all", "count": len(records),
                "records": records, "format": "instruction-input-output"}


# ---------------------------------------------------------------------------
# Training, evaluation and model registry
# ---------------------------------------------------------------------------

def _run_payload(row) -> dict:
    result = dict(row)
    result["config"] = json.loads(result.pop("config_json"))
    result["metrics"] = json.loads(result.pop("metrics_json"))
    return result


@router.post("/{company_id}/train")
def train(company_id: int, payload: TrainIn):
    task = _validate_task(payload.task)
    if payload.method not in METHODS:
        raise HTTPException(422, "Unsupported training method")
    config = {"task": task, "method": payload.method, "epochs": payload.epochs}
    with connection() as c:
        ensure_schema(c)
        company = _company(c, company_id)
        rows = c.execute(
            """SELECT id,input_json,output_json FROM learning_examples
               WHERE company_id=? AND task=? AND state='approved' ORDER BY id""",
            (company_id, task),
        ).fetchall()
        if len(rows) < 4:
            raise HTTPException(422, "Approve at least four examples before training")
        examples = [{"id": row["id"], "input": json.loads(row["input_json"]),
                     "label": row["output_json"]} for row in rows]
        cursor = c.execute(
            """INSERT INTO training_runs(company_id,task,method,status,config_json)
               VALUES(?,?,?,?,?)""",
            (company_id, task, payload.method, "running", json.dumps(config)),
        )
        run_id = cursor.lastrowid

        if payload.method == "lora":
            missing = [name for name in ("torch", "transformers", "peft", "datasets")
                       if importlib.util.find_spec(name) is None]
            if missing:
                error = "LoRA dependencies missing: " + ", ".join(missing)
                c.execute(
                    "UPDATE training_runs SET status='blocked',error=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
                    (error, run_id),
                )
                return {"run_id": run_id, "status": "blocked", "error": error,
                        "next_step": "Install requirements-lora.txt and use scripts/train_company_lora.py offline."}
            manifest = _write_artifact(
                company_id, company["slug"], task, "lora-manifest", run_id,
                {"format": "prism-lora-manifest-v1", "company": company["slug"],
                 "task": task, "records": [{"instruction": TASK_INSTRUCTIONS[task],
                                            "input": ex["input"], "output": json.loads(ex["label"])}
                                           for ex in examples]},
            )
            c.execute(
                """UPDATE training_runs SET status='prepared',artifact_path=?,
                   metrics_json=?,finished_at=CURRENT_TIMESTAMP WHERE id=?""",
                (manifest, json.dumps({"method": "lora", "is_llm": True, "prepared_only": True}), run_id),
            )
            return {"run_id": run_id, "status": "prepared", "artifact_path": manifest,
                    "next_step": "Launch scripts/train_company_lora.py with a local base model."}

        artifact, metrics = train_deterministic(examples, payload.epochs)
        path = _write_artifact(company_id, company["slug"], task, "deterministic", run_id, artifact)
        c.execute(
            """UPDATE training_runs SET status='evaluated',metrics_json=?,artifact_path=?,
               finished_at=CURRENT_TIMESTAMP WHERE id=?""",
            (json.dumps(metrics), path, run_id),
        )
        version = c.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM company_models WHERE company_id=? AND task=?",
            (company_id, task),
        ).fetchone()[0]
        c.execute(
            """INSERT INTO company_models(company_id,task,run_id,version,metrics_json,artifact_path,state)
               VALUES(?,?,?,?,?,?,'candidate')""",
            (company_id, task, run_id, version, json.dumps(metrics), path),
        )
        return {"run_id": run_id, "status": "evaluated", "metrics": metrics,
                "artifact_path": path, "candidate_model_version": version}


@router.get("/{company_id}/runs")
def list_runs(company_id: int):
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        return [_run_payload(row) for row in c.execute(
            "SELECT * FROM training_runs WHERE company_id=? ORDER BY id DESC LIMIT 100", (company_id,))]


@router.get("/{company_id}/runs/{run_id}")
def get_run(company_id: int, run_id: int):
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        row = c.execute(
            "SELECT * FROM training_runs WHERE id=? AND company_id=?", (run_id, company_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Run not found for this company")
        return _run_payload(row)


@router.get("/{company_id}/models")
def list_models(company_id: int):
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        rows = [dict(row) for row in c.execute(
            "SELECT * FROM company_models WHERE company_id=? ORDER BY id DESC", (company_id,))]
        for row in rows:
            row["metrics"] = json.loads(row.pop("metrics_json"))
        return rows


@router.post("/{company_id}/models/{model_id}/approve")
def approve_model(company_id: int, model_id: int, payload: ConfirmationIn):
    if payload.confirmation != APPROVE_MODEL_CONFIRMATION:
        raise HTTPException(422, "Explicit model approval confirmation required")
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        row = c.execute(
            "SELECT * FROM company_models WHERE id=? AND company_id=?", (model_id, company_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Model not found for this company")
        if row["state"] == "active":
            return {"id": model_id, "state": "active", "already_active": True}
        if row["state"] != "candidate":
            raise HTTPException(409, "Only candidate models can be activated")
        c.execute(
            """UPDATE company_models SET state='retired' WHERE company_id=? AND task=? AND state='active'""",
            (company_id, row["task"]),
        )
        c.execute(
            """UPDATE company_models SET state='active',approved_at=CURRENT_TIMESTAMP WHERE id=?""",
            (model_id,),
        )
        return {"id": model_id, "task": row["task"], "state": "active"}


@router.get("/{company_id}/models/{model_id}/artifact")
def model_artifact(company_id: int, model_id: int):
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        row = c.execute(
            "SELECT artifact_path FROM company_models WHERE id=? AND company_id=?", (model_id, company_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Model not found for this company")
        path = Path(row["artifact_path"]).resolve()
        root = _model_root()
        try:
            path.relative_to(root)
        except ValueError:
            raise HTTPException(409, "Artifact path outside configured root")
        if not path.is_file():
            raise HTTPException(404, "Artifact file missing")
        return json.loads(path.read_text(encoding="utf-8"))


@router.post("/{company_id}/predict")
def predict(company_id: int, payload: PredictIn):
    task = _validate_task(payload.task)
    clean_input, _ = _scrub_example(payload.input)
    with connection() as c:
        ensure_schema(c)
        _company(c, company_id)
        active = c.execute(
            """SELECT m.id,m.task,m.run_id,m.version,m.artifact_path,m.state,
                      r.metrics_json AS run_metrics
               FROM company_models m JOIN training_runs r ON r.id=m.run_id
               WHERE m.company_id=? AND m.task=? AND m.state='active'""",
            (company_id, task),
        ).fetchone()
        rag = rag_query(company_id, RagIn(task=task, query=_canonical(clean_input), limit=2))
        if not active:
            top = rag["results"][0]["output"] if rag["results"] else {}
            return {
                "company_id": company_id, "task": task, "mode": "rag-only",
                "prediction": top, "confidence": rag["results"][0]["score"] if rag["results"] else 0.0,
                "provenance": {"model_id": None, "reason": "No approved active model for this company and task"},
                "supporting_examples": rag["results"],
                "warning": "Retrieval-only result. Train and approve a company model before model-based prediction.",
            }
        path = Path(active["artifact_path"]).resolve()
        if not path.is_file():
            raise HTTPException(409, "Approved model artifact is missing")
        artifact = json.loads(path.read_text(encoding="utf-8"))
        result = predict_deterministic(artifact, clean_input)
        method = json.loads(active["run_metrics"]).get("method", "deterministic")
        return {
            "company_id": company_id, "task": task, "mode": "model+rag",
            "prediction": result["prediction"], "confidence": result["confidence"],
            "alternatives": result["alternatives"],
            "provenance": {"model_id": active["id"], "run_id": active["run_id"],
                           "version": active["version"], "method": method,
                           "artifact": active["artifact_path"]},
            "supporting_examples": rag["results"],
            "warning": "Small locally trained model over approved examples; not an enterprise-grade LLM.",
        }


@router.post("/{company_id}/bootstrap")
def bootstrap(company_id: int):
    """Convenience path for a deterministic, synthetic-only end-to-end demo."""
    with connection() as c:
        ensure_schema(c)
        company = _company(c, company_id)
    created = {}
    for task in TASKS:
        response = add_synthetic_source(company_id, SyntheticSourceIn(task=task, count=12))
        created[task] = response["examples_created"]
    return {"company_id": company_id, "slug": company["slug"], "examples_created": created,
            "next_step": "Approve draft examples, then train a model per task.", "synthetic": True}
