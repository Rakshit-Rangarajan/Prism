"""Bounded synthetic/demo SQLite ingestion; never modifies uploaded source."""
import sqlite3
import tempfile
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response

router = APIRouter(prefix="/api/demo/database")
LIMIT = 10 * 1024 * 1024

def ident(name):
    return '"' + name.replace('"', '""') + '"'

async def upload(request):
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > LIMIT:
            raise HTTPException(413, "Database exceeds 10 MB demo limit")
        data.extend(chunk)
    if not data.startswith(b"SQLite format 3\x00"):
        raise HTTPException(422, "Upload a SQLite database file")
    return data

def inspect_db(db, clean=False):
    db.execute("PRAGMA trusted_schema=OFF")
    db.execute("PRAGMA foreign_keys=ON")
    tables = db.execute("SELECT name,sql FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    if len(tables) > 100:
        raise HTTPException(422, "Maximum 100 tables")
    report = []
    for name, sql in tables:
        if not sql or sql.upper().startswith("CREATE VIRTUAL"):
            raise HTTPException(422, "Virtual tables are unsupported")
        q = ident(name)
        cols = db.execute(f"PRAGMA table_xinfo({q})").fetchall()
        count = db.execute(f"SELECT count(*) FROM {q}").fetchone()[0]
        if count > 100000 or len(cols) > 100:
            raise HTTPException(422, "Demo limit: 100,000 rows and 100 columns per table")
        issues = []
        for cid, col, typ, required, default, pk, hidden in cols:
            if hidden:
                continue
            k = ident(col)
            blanks, whitespace, nulls = db.execute(f"""SELECT coalesce(sum(typeof({k})='text' AND trim({k})=''),0), coalesce(sum(typeof({k})='text' AND {k} COLLATE BINARY != trim({k}) COLLATE BINARY),0), coalesce(sum({k} IS NULL),0) FROM {q}""").fetchone()
            # Never edit keys, constrained/indexed columns or tables with triggers.
            indexed = any(col in [r[2] for r in db.execute(f"PRAGMA index_info({ident(ix[1])})")] or ix[4] for ix in db.execute(f"PRAGMA index_list({q})"))
            fk = db.execute(f"PRAGMA foreign_key_list({q})").fetchall()
            referenced = any(any(r[2].casefold()==name.casefold() for r in db.execute(f"PRAGMA foreign_key_list({ident(other)})")) for other,_ in tables)
            triggers = db.execute("SELECT 1 FROM sqlite_schema WHERE type='trigger' AND tbl_name=?", (name,)).fetchone()
            eligible = not (pk or indexed or fk or referenced or triggers or 'CHECK' in sql.upper() or any(x[6] for x in cols))
            issues.append({"column":col,"type":typ,"nulls":nulls,"blank_text":blanks,"whitespace":whitespace,"trim_eligible":bool(eligible)})
            if clean and eligible and whitespace:
                db.execute(f"UPDATE {q} SET {k}=trim({k}) WHERE typeof({k})='text' AND {k} COLLATE BINARY != trim({k}) COLLATE BINARY AND trim({k})!=''")
        report.append({"table":name,"rows":count,"columns":issues})
    return report

@router.get("/sample")
def sample():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"sample.sqlite"
        with sqlite3.connect(path) as db:
            db.executescript("""
            CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, email TEXT, country TEXT);
            INSERT INTO customers VALUES(1,' Alice ',' alice@example.test ',' UK '),(2,'Bob',NULL,'India'),(3,'Bob','bob@example.test','');
            CREATE TABLE materials(id INTEGER PRIMARY KEY, description TEXT, unit TEXT);
            INSERT INTO materials VALUES(1,' Steel bolt ',' EA '),(2,'Copper wire','M'),(3,'  ','KG');
            """)
        return Response(path.read_bytes(),media_type="application/octet-stream",headers={"Content-Disposition":"attachment; filename=prism-sample.sqlite"})

@router.post("/profile")
async def profile(request: Request):
    data=await upload(request)
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"source.sqlite"
        path.write_bytes(data)
        try:
            with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as db:
                return {"tables":inspect_db(db),"rule":"Trim surrounding spaces in eligible non-key text columns; retain missing/blank values for review."}
        except sqlite3.Error:
            raise HTTPException(422,"Invalid or unsupported SQLite database")

@router.post("/clean")
async def clean(request: Request):
    if request.headers.get("x-prism-approval")!="TRIM APPROVED":
        raise HTTPException(422,"Explicit approval required")
    data=await upload(request)
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"processed.sqlite"
        path.write_bytes(data)
        try:
            with sqlite3.connect(path) as db:
                inspect_db(db,clean=True)
                if db.execute("PRAGMA foreign_key_check").fetchone():
                    raise HTTPException(422,"Foreign key violations require review")
            return Response(path.read_bytes(),media_type="application/octet-stream",headers={"Content-Disposition":"attachment; filename=prism-processed.sqlite"})
        except sqlite3.Error:
            raise HTTPException(422,"Cleaning failed; original source remains unchanged")
