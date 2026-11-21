"""Versioned, approval-gated Migration Memory catalog for the PRISM demo.

Uses the existing SQLite connection and enforces domain scoping. This is
deterministic retrieval, not a trained AI model or production governance.
"""
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from .server import connection, require_user

router = APIRouter(prefix="/api/memory", tags=["Migration Memory"], dependencies=[Depends(require_user)])

def ensure_schema(c):
    c.execute("""CREATE TABLE IF NOT EXISTS memory_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        target_object TEXT NOT NULL,
        title TEXT NOT NULL,
        resolution TEXT NOT NULL,
        evidence TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','approved','rejected','superseded')),
        reviewer TEXT,
        review_note TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS memory_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        note TEXT,
        actor TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS memory_scope_idx ON memory_entries(domain,target_object,state)")

class MemoryEntry(BaseModel):
    domain: str = Field(min_length=2, max_length=80)
    target_object: str = Field(min_length=2, max_length=100)
    title: str = Field(min_length=5, max_length=200)
    resolution: str = Field(min_length=10, max_length=4000)
    evidence: str = Field(min_length=3, max_length=500)
    version: int = Field(default=1, ge=1, le=9999)

class Review(BaseModel):
    action: str
    reviewer: str = Field(min_length=2, max_length=100)
    note: str = Field(min_length=8, max_length=2000)

@router.get("/search")
def search_memory(q: str = Query(default="", max_length=250), domain: str = Query(default="", max_length=80), target_object: str = Query(default="", max_length=100), limit: int = Query(default=20, ge=1, le=100)):
    """Only approved entries are retrieved. Scope boundaries are exact matches."""
    with connection() as c:
        ensure_schema(c)
        sql="SELECT * FROM memory_entries WHERE state='approved'"
        params=[]
        if domain:
            sql+=" AND domain=?"; params.append(domain)
        if target_object:
            sql+=" AND target_object=?"; params.append(target_object)
        if q.strip():
            tokens=[t for t in re.findall(r"[a-zA-Z0-9_]+",q.lower()) if len(t)>1][:12]
            for token in tokens:
                sql+=" AND (LOWER(title) LIKE ? OR LOWER(resolution) LIKE ? OR LOWER(evidence) LIKE ?)"
                wildcard="%"+token+"%"
                params.extend([wildcard]*3)
        sql+=" ORDER BY reviewed_at DESC, id DESC LIMIT ?"
        params.append(limit)
        return {"query":q,"domain":domain,"target_object":target_object,"results":[dict(r) for r in c.execute(sql,params)],"retrieval":"deterministic-keywords","approved_only":True}

@router.get("/entries")
def list_entries():
    with connection() as c:
        ensure_schema(c)
        return [dict(r) for r in c.execute("SELECT * FROM memory_entries ORDER BY id DESC LIMIT 500")]

@router.post("/entries",status_code=201)
def create_entry(entry:MemoryEntry):
    with connection() as c:
        ensure_schema(c)
        cur=c.execute("""INSERT INTO memory_entries(domain,target_object,title,resolution,evidence,version)
          VALUES(?,?,?,?,?,?)""",(entry.domain,entry.target_object,entry.title,entry.resolution,entry.evidence,entry.version))
        c.execute("INSERT INTO memory_events(entry_id,action,note,actor) VALUES(?,?,?,?)",(cur.lastrowid,"created","Draft created","demo"))
        return {"id":cur.lastrowid,"state":"draft"}

@router.post("/entries/{entry_id}/review")
def review_entry(entry_id:int,review:Review):
    if review.action not in ("approved","rejected"): raise HTTPException(400,"Invalid review action")
    with connection() as c:
        ensure_schema(c)
        entry=c.execute("SELECT * FROM memory_entries WHERE id=?",(entry_id,)).fetchone()
        if not entry: raise HTTPException(404,"Memory entry not found")
        if entry["state"] != "draft": raise HTTPException(409,"Only drafts can be reviewed")
        c.execute("""UPDATE memory_entries SET state=?,reviewer=?,review_note=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?""",(review.action,review.reviewer,review.note,entry_id))
        c.execute("INSERT INTO memory_events(entry_id,action,note,actor) VALUES(?,?,?,?)",(entry_id,review.action,review.note,review.reviewer))
        return {"id":entry_id,"state":review.action}

@router.get("/entries/{entry_id}/events")
def entry_events(entry_id:int):
    with connection() as c:
        ensure_schema(c)
        if not c.execute("SELECT 1 FROM memory_entries WHERE id=?",(entry_id,)).fetchone(): raise HTTPException(404,"Memory entry not found")
        return [dict(r) for r in c.execute("SELECT * FROM memory_events WHERE entry_id=? ORDER BY id",(entry_id,))]
