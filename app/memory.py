"""Versioned, approval-gated Migration Memory catalog for the PRISM demo.

Uses the existing SQLite connection and enforces domain scoping. This is
deterministic retrieval, not a trained AI model or production governance.
"""
import re
import math
from collections import Counter
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
    columns={row["name"] for row in c.execute("PRAGMA table_info(memory_entries)")}
    if "supersedes_id" not in columns:
        c.execute("ALTER TABLE memory_entries ADD COLUMN supersedes_id INTEGER REFERENCES memory_entries(id)")
    c.execute("CREATE INDEX IF NOT EXISTS memory_scope_idx ON memory_entries(domain,target_object,state)")
    c.execute("CREATE INDEX IF NOT EXISTS memory_supersedes_idx ON memory_entries(supersedes_id)")
    # Enforce one draft per predecessor even under concurrent requests.
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS memory_one_draft_per_parent ON memory_entries(supersedes_id) WHERE state='draft' AND supersedes_id IS NOT NULL")

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
        rows=[dict(r) for r in c.execute(sql+" ORDER BY reviewed_at DESC,id DESC",params)]
        tokens=[t for t in re.findall(r"[a-zA-Z0-9_]+",q.casefold()) if len(t)>1][:24]
        if tokens:
            # BM25-inspired lexical ranking with document-length normalization.
            # This is explicitly NOT neural semantic search.
            documents=[re.findall(r"[a-zA-Z0-9_]+",(r["title"]+" "+r["resolution"]+" "+r["evidence"]).casefold()) for r in rows]
            counts=[Counter(doc) for doc in documents]
            n=len(rows)
            avg_length=sum(map(len,documents))/n if n else 1
            df=Counter(token for doc in counts for token in doc)
            ranked=[]
            for row,doc,frequency in zip(rows,documents,counts):
                score=0.0
                for token in set(tokens):
                    occurrences=frequency[token]
                    if occurrences:
                        idf=math.log(1+(n-df[token]+0.5)/(df[token]+0.5))
                        score+=idf*occurrences*2.2/(occurrences+1.2*(0.25+0.75*len(doc)/avg_length))
                if score:
                    row["retrieval_score"]=round(score,5)
                    ranked.append(row)
            rows=sorted(ranked,key=lambda row:(-row["retrieval_score"],-row["id"]))
        return {"query":q,"domain":domain,"target_object":target_object,"results":rows[:limit],"retrieval":"bm25-lexical","approved_only":True}

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
        c.execute("BEGIN IMMEDIATE")
        entry=c.execute("SELECT * FROM memory_entries WHERE id=?",(entry_id,)).fetchone()
        if not entry: raise HTTPException(404,"Memory entry not found")
        if entry["state"] != "draft": raise HTTPException(409,"Only drafts can be reviewed")
        if review.action=="approved" and entry["supersedes_id"] is not None:
            prior=c.execute("SELECT * FROM memory_entries WHERE id=?",(entry["supersedes_id"],)).fetchone()
            if not prior or prior["state"]!="approved":
                raise HTTPException(409,"Predecessor is no longer approved")
            # Reject competing approved successors: only one current approved version.
            c.execute("UPDATE memory_entries SET state='superseded' WHERE id=? AND state='approved'",(prior["id"],))
            c.execute("INSERT INTO memory_events(entry_id,action,note,actor) VALUES(?,?,?,?)",(prior["id"],"superseded",f"Replaced by version {entry['version']} (entry {entry_id})",review.reviewer))
        c.execute("""UPDATE memory_entries SET state=?,reviewer=?,review_note=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?""",(review.action,review.reviewer,review.note,entry_id))
        c.execute("INSERT INTO memory_events(entry_id,action,note,actor) VALUES(?,?,?,?)",(entry_id,review.action,review.note,review.reviewer))
        return {"id":entry_id,"state":review.action}

@router.get("/entries/{entry_id}/events")
def entry_events(entry_id:int):
    with connection() as c:
        ensure_schema(c)
        if not c.execute("SELECT 1 FROM memory_entries WHERE id=?",(entry_id,)).fetchone(): raise HTTPException(404,"Memory entry not found")
        return [dict(r) for r in c.execute("SELECT * FROM memory_events WHERE entry_id=? ORDER BY id",(entry_id,))]

class Revision(BaseModel):
    title: str = Field(min_length=5,max_length=200)
    resolution: str = Field(min_length=10,max_length=4000)
    evidence: str = Field(min_length=3,max_length=500)

@router.post("/entries/{entry_id}/revisions",status_code=201)
def revise_entry(entry_id:int,revision:Revision):
    """Create a draft successor. Approval atomically retires its predecessor."""
    with connection() as c:
        ensure_schema(c)
        c.execute("BEGIN IMMEDIATE")
        prior=c.execute("SELECT * FROM memory_entries WHERE id=?",(entry_id,)).fetchone()
        if not prior: raise HTTPException(404,"Memory entry not found")
        if prior["state"]!="approved": raise HTTPException(409,"Only approved entries may be revised")
        if prior["version"]>=9999: raise HTTPException(409,"Maximum version reached")
        # Do not allow parallel drafts for the same predecessor.
        if c.execute("SELECT 1 FROM memory_entries WHERE supersedes_id=? AND state='draft'",(entry_id,)).fetchone():
            raise HTTPException(409,"A draft revision already exists")
        cur=c.execute("""INSERT INTO memory_entries
            (domain,target_object,title,resolution,evidence,version,supersedes_id)
            VALUES(?,?,?,?,?,?,?)""",(prior["domain"],prior["target_object"],revision.title,
                revision.resolution,revision.evidence,prior["version"]+1,entry_id))
        c.execute("INSERT INTO memory_events(entry_id,action,note,actor) VALUES(?,?,?,?)",
                  (cur.lastrowid,"created",f"Revision of entry {entry_id}","demo"))
        return {"id":cur.lastrowid,"version":prior["version"]+1,"state":"draft","supersedes_id":entry_id}
