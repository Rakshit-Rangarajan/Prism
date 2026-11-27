"""Operator-configured MySQL source; no arbitrary network targets from browser."""
import os
import sqlite3
import tempfile
from pathlib import Path
from contextlib import closing
from decimal import Decimal
from datetime import date, datetime, time, timedelta
import pymysql
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from .database_demo import LIMIT, ident

router = APIRouter(prefix="/api/demo/database/mysql")

def configured():
    return all(os.getenv("PRISM_MYSQL_"+k) for k in ("HOST","DATABASE","USER","PASSWORD"))

def mysql_ident(name):
    return "`" + name.replace("`","``") + "`"

def adapt(value):
    if isinstance(value, (Decimal, date, datetime, time, timedelta)):
        return str(value)
    return value

@router.get("/status")
def status():
    return {"configured": configured(), "mode": "read-only snapshot"}

@router.post("/snapshot")
def snapshot():
    if not configured():
        raise HTTPException(503, "Configure PRISM_MYSQL_HOST, DATABASE, USER and PASSWORD on the PRISM server.")
    schema = os.environ["PRISM_MYSQL_DATABASE"]
    try:
        local = os.getenv("PRISM_MYSQL_HOST") in ("localhost","127.0.0.1","::1")
        ca = os.getenv("PRISM_MYSQL_SSL_CA")
        if not local and not ca:
            raise HTTPException(503, "Remote MySQL requires PRISM_MYSQL_SSL_CA for verified TLS.")
        with closing(pymysql.connect(host=os.environ["PRISM_MYSQL_HOST"], port=int(os.getenv("PRISM_MYSQL_PORT","3306")), user=os.environ["PRISM_MYSQL_USER"], password=os.environ["PRISM_MYSQL_PASSWORD"], database=schema, connect_timeout=5, read_timeout=15, write_timeout=10, charset="utf8mb4", ssl_ca=ca, ssl_verify_cert=bool(ca), ssl_verify_identity=bool(ca))) as source:
            with source.cursor() as cur, tempfile.TemporaryDirectory() as folder:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
                cur.execute("SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME LIMIT 101",(schema,))
                tables=cur.fetchall()
                if len(tables)>100 or any(engine!="InnoDB" for _,engine in tables):
                    raise HTTPException(422,"Demo requires at most 100 InnoDB tables.")
                path=Path(folder)/"mysql-snapshot.sqlite"
                with closing(sqlite3.connect(path)) as target:
                    target.execute(f"PRAGMA max_page_count={LIMIT//4096}")
                    target.execute("PRAGMA page_size=4096")
                    for table,_ in tables:
                        cur.execute("SELECT COLUMN_NAME, DATA_TYPE, COLUMN_KEY FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",(schema,table))
                        columns=cur.fetchall()
                        if not columns or len(columns)>100:
                            raise HTTPException(422,"Unsupported table width.")
                        # Snapshot is a staging representation, not a faithful SQL DDL clone.
                        defs=[]
                        for name,typ,key in columns:
                            kind = "INTEGER" if typ in ("tinyint","smallint","mediumint","int") else "REAL" if typ in ("float","double") else "BLOB" if typ in ("binary","varbinary","blob","tinyblob","mediumblob","longblob","bit") else "TEXT"
                            defs.append(ident(name)+" "+kind)
                        cur.execute("SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION",(schema,table))
                        primary=[ident(r[0]) for r in cur.fetchall()]
                        if primary:
                            defs.append("PRIMARY KEY ("+",".join(primary)+")")
                        target.execute("CREATE TABLE "+ident(table)+" ("+",".join(defs)+")")
                        # Protect indexed source columns against automatic normalization.
                        cur.execute("SELECT DISTINCT COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME IS NOT NULL",(schema,table))
                        for idx,(keycol,) in enumerate(cur.fetchall()):
                            import hashlib
                            index_name="prism_key_"+hashlib.sha256((table+"\u0000"+str(idx)).encode()).hexdigest()
                            target.execute("CREATE INDEX "+ident(index_name)+" ON "+ident(table)+" ("+ident(keycol)+")")
                        names=",".join(mysql_ident(x[0]) for x in columns)
                        cur.execute("SELECT "+names+" FROM "+mysql_ident(table)+" LIMIT 10001")
                        rows=cur.fetchall()
                        if len(rows)>10000:
                            raise HTTPException(422,"Demo limit: 10,000 rows per MySQL table; no silent truncation.")
                        target.executemany("INSERT INTO "+ident(table)+" VALUES ("+",".join("?" for _ in columns)+")", [tuple(adapt(v) for v in row) for row in rows])
                    target.commit()
                data=path.read_bytes()
                if len(data)>LIMIT:
                    raise HTTPException(422,"Snapshot exceeds 10 MB demo limit.")
                return Response(data,media_type="application/octet-stream",headers={"Content-Disposition":"attachment; filename=mysql-snapshot.sqlite"})
    except HTTPException:
        raise
    except (pymysql.MySQLError, sqlite3.Error, ValueError, OverflowError):
        raise HTTPException(422,"MySQL snapshot failed. Check read-only grants, network, TLS, supported data types and size limits.")
