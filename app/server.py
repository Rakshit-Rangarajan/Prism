import os, sqlite3, secrets
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

app=FastAPI(title="PRISM",version="0.3-demo")
auth=HTTPBasic(auto_error=False)
DB=os.getenv("PRISM_DB","/tmp/prism.sqlite3")
@contextmanager
def connection():
    Path(DB).parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
    try:
        yield c
        c.commit()
    finally:c.close()
def require_user(creds:HTTPBasicCredentials|None=Depends(auth)):
    pw=os.getenv("PRISM_DEMO_PASSWORD")
    if not pw:raise HTTPException(503,"Set PRISM_DEMO_PASSWORD to enable demo")
    if not creds or not (secrets.compare_digest(creds.username,"prism") and secrets.compare_digest(creds.password,pw)):
        raise HTTPException(401,"Login required",headers={"WWW-Authenticate":"Basic realm=PRISM"})
def seed():
    with connection() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS exceptions(id INTEGER PRIMARY KEY,wave TEXT,domain TEXT,object TEXT,error TEXT,severity TEXT,state TEXT DEFAULT 'open',owner TEXT,note TEXT);
        CREATE TABLE IF NOT EXISTS knowledge(id INTEGER PRIMARY KEY,domain TEXT,title TEXT,resolution TEXT,evidence TEXT,approved INTEGER,version INTEGER);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,exception_id INTEGER,action TEXT,note TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);""")
        if not c.execute("SELECT 1 FROM exceptions").fetchone():
            c.executemany("INSERT INTO exceptions(id,wave,domain,object,error,severity,owner) VALUES(?,?,?,?,?,?,?)",[
            (1001,"Wave 0","Vendor","SUPPLIER","Missing reconciliation account","critical","Finance"),
            (1002,"Wave 1","Vendor","SUPPLIER","Unknown tax classification","high","Procurement"),
            (1003,"Wave 1","Material","PRODUCT","Invalid base unit","high","Master Data"),
            (1004,"Wave 2","Customer","BUSINESS_PARTNER","Potential duplicate candidate","medium","Steward"),
            (1005,"Wave 2","Finance","GL_ACCOUNT","Cost centre not found","critical","Finance"),
            (1006,"Wave 0","Material","PRODUCT","Description exceeds field length","low","Master Data")])
        if not c.execute("SELECT 1 FROM knowledge").fetchone():
            c.executemany("INSERT INTO knowledge(domain,title,resolution,evidence,approved,version) VALUES(?,?,?,?,1,1)",[
            ("Vendor","Tax mapping","Validate classifications against the approved target SAP lookup.","SYNTH-001"),
            ("Finance","Account mapping","Compare cost centre and reconciliation fields with the target chart of accounts.","SYNTH-002"),
            ("Material","UOM mapping","Use an approved UOM crosswalk and validate in staging.","SYNTH-003"),
            ("Customer","Duplicate checks","Escalate potential duplicates for steward review; do not auto-merge.","SYNTH-004")])
seed()
@app.get("/api/health")
def health():return {"status":"ok","mode":"synthetic"}
@app.get("/",dependencies=[Depends(require_user)])
def index():return FileResponse(Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html")
@app.get("/api/exceptions",dependencies=[Depends(require_user)])
def exceptions():
    with connection() as c:return [dict(r) for r in c.execute("SELECT * FROM exceptions ORDER BY id")]
@app.get("/api/knowledge",dependencies=[Depends(require_user)])
def knowledge():
    with connection() as c:return [dict(r) for r in c.execute("SELECT * FROM knowledge ORDER BY id")]
@app.get("/api/recommendations/{identifier}",dependencies=[Depends(require_user)])
def recommendations(identifier:int):
    with connection() as c:
        r=c.execute("SELECT * FROM exceptions WHERE id=?",(identifier,)).fetchone()
        if not r:raise HTTPException(404,"Not found")
        return {"exception":dict(r),"references":[dict(x) for x in c.execute("SELECT * FROM knowledge WHERE domain=? AND approved=1",(r["domain"],))]}
@app.get("/api/readiness",dependencies=[Depends(require_user)])
def readiness():
    with connection() as c:
        return [dict(r) for r in c.execute("SELECT domain,COUNT(*) total,SUM(state='open') open,SUM(state='open' AND severity='critical') blockers FROM exceptions GROUP BY domain")]
class Decision(BaseModel):
    action:str
    note:str
@app.post("/api/exceptions/{identifier}/decision",dependencies=[Depends(require_user)])
def decide(identifier:int,req:Decision):
    if req.action not in ("approved","rejected","reopened") or len(req.note.strip())<5:raise HTTPException(400,"Invalid action or note (minimum five characters)")
    with connection() as c:
        if not c.execute("SELECT 1 FROM exceptions WHERE id=?",(identifier,)).fetchone():raise HTTPException(404,"Not found")
        c.execute("UPDATE exceptions SET state=?,note=? WHERE id=?",(req.action,req.note,identifier))
        c.execute("INSERT INTO audit(exception_id,action,note) VALUES(?,?,?)",(identifier,req.action,req.note))
    return {"id":identifier,"state":req.action}
@app.get("/api/evidence",dependencies=[Depends(require_user)])
def evidence():
    with connection() as c:return {"synthetic":True,"exceptions":[dict(r) for r in c.execute("SELECT * FROM exceptions")],"audit":[dict(r) for r in c.execute("SELECT * FROM audit")]}

# React/Vite compiled assets; API endpoints retain their existing auth dependencies.
app.mount('/assets',StaticFiles(directory=str(Path(__file__).resolve().parent.parent / 'frontend' / 'dist' / 'assets')),name='assets')

# Register isolated, approval-gated Migration Memory catalog.
from .memory import router as memory_router
app.include_router(memory_router)
