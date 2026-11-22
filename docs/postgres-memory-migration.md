# PostgreSQL Migration Memory preparation

This feature branch provides an **offline, opt-in, all-or-nothing** migration of the synthetic, versioned Migration Memory catalog from SQLite into PostgreSQL. It does **not** change the live FastAPI storage backend, provision a database, or enable pgvector. The existing Render demo remains on SQLite.

## Safe dry run

```bash
python -m scripts.migrate_memory_postgres --sqlite /path/to/prism.sqlite3
python -m unittest discover -s tests -p 'test_postgres_migration.py' -v
```

The source must already contain `memory_entries` and `memory_events`. The dry run opens SQLite read-only, verifies revision/audit references, and prints counts. It never creates a missing source database.

## Apply to an empty PostgreSQL database

```bash
python -m pip install 'psycopg[binary]>=3,<4'
export PRISM_POSTGRES_DSN='postgresql://USER:PASSWORD@HOST:5432/DBNAME'
python -m scripts.migrate_memory_postgres --sqlite /path/to/prism.sqlite3 --apply
unset PRISM_POSTGRES_DSN
```

The target **must be empty** for both Migration Memory tables. A transaction creates the schema, copies entries and audit events with stable identifiers, restores supersession links, synchronizes identity sequences, and checks row counts. Any error rolls back the transaction; existing destination records are never overwritten. Protect the DSN and database snapshot as secrets. Do not use actual customer or enterprise records.

## Not yet implemented

- FastAPI PostgreSQL connection adapter and live cutover
- PostgreSQL provisioned with persistent storage
- pgvector extension and local neural embeddings
- live PostgreSQL integration tests

Do not point the live Render app at PostgreSQL until the adapter and rollback path are tested.
