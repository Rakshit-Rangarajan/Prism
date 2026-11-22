"""Validated, non-executing migration blueprints (synthetic/demo workspace).

No connector credentials, data payloads, or LLM prompts are stored here.
SQLite remains ephemeral on the Render demo until durable storage is provisioned.
"""
import json
import sqlite3
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from .server import connection, require_user

router = APIRouter(prefix="/api/blueprints", tags=["Migration Blueprints"],
                   dependencies=[Depends(require_user)])

# The UI taxonomy is intentionally explicit; unknown types fail closed.
DATA_TYPES = frozenset("""
sql warehouse columnar csv spreadsheet fixed dbf lakehouse json xml yaml avro
document nosql wide graphql erp crm saas mainframe edi hl7 gis timeseries
graph vector search spatial scientific blockchain txt pdf office html email
archive logs image audio video cad blob events cdc iot
""".split())

class Blueprint(BaseModel):
    company: str = Field(min_length=2, max_length=90)
    source: str = Field(min_length=2, max_length=120)
    destination: str = Field(min_length=2, max_length=120)
    sourceType: str
    targetType: str
    volume: int = Field(ge=1, le=100_000_000_000)
    priority: str
    model: str
    isolation: bool = True

    @field_validator("company", "source", "destination")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2 or any(ord(char) < 32 for char in value):
            raise ValueError("Invalid name")
        return value

    @field_validator("sourceType", "targetType")
    @classmethod
    def known_type(cls, value: str) -> str:
        if value not in DATA_TYPES:
            raise ValueError("Unsupported data type")
        return value

    @field_validator("priority")
    @classmethod
    def known_priority(cls, value: str) -> str:
        if value not in {"quality", "risk", "speed", "cost"}:
            raise ValueError("Unsupported priority")
        return value

    @field_validator("model")
    @classmethod
    def known_runtime(cls, value: str) -> str:
        if value not in {"ollama", "llamacpp", "vllm", "disabled"}:
            raise ValueError("Unsupported local runtime")
        return value

    @model_validator(mode="after")
    def require_isolation(self):
        if not self.isolation:
            raise ValueError("Company isolation is mandatory")
        return self

def ensure_schema(c):
    c.execute("""CREATE TABLE IF NOT EXISTS migration_blueprints (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      company TEXT NOT NULL,
      payload TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','archived')),
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS blueprint_company_idx ON migration_blueprints(company,id)")

def row_payload(row):
    return {"id": row["id"], "company": row["company"],
            "status": row["status"], "created_at": row["created_at"],
            "updated_at": row["updated_at"], "blueprint": json.loads(row["payload"]),
            "execution_enabled": False}

@router.post("", status_code=201)
def create_blueprint(payload: Blueprint):
    now = datetime.now(timezone.utc).isoformat()
    with connection() as c:
        ensure_schema(c)
        try:
            cur = c.execute("""INSERT INTO migration_blueprints
              (company,payload,created_at,updated_at) VALUES(?,?,?,?)""",
              (payload.company, payload.model_dump_json(), now, now))
        except sqlite3.DatabaseError:
            raise HTTPException(500, "Unable to store migration blueprint")
        row = c.execute("SELECT * FROM migration_blueprints WHERE id=?", (cur.lastrowid,)).fetchone()
        return row_payload(row)

@router.get("")
def list_blueprints(company: str = Query(min_length=2, max_length=90),
                    limit: int = Query(default=30, ge=1, le=100)):
    company = company.strip()
    with connection() as c:
        ensure_schema(c)
        rows = c.execute("""SELECT * FROM migration_blueprints
          WHERE company=? ORDER BY id DESC LIMIT ?""", (company,limit)).fetchall()
        return {"company":company,"results":[row_payload(r) for r in rows],
                "mode":"design-only","durability":"ephemeral-sqlite"}

@router.get("/{blueprint_id}")
def get_blueprint(blueprint_id: int, company: str = Query(min_length=2, max_length=90)):
    with connection() as c:
        ensure_schema(c)
        row = c.execute("""SELECT * FROM migration_blueprints
          WHERE id=? AND company=?""", (blueprint_id,company.strip())).fetchone()
        if row is None:
            raise HTTPException(404, "Blueprint not found in company scope")
        return row_payload(row)
