"""Offline migration contract tests; no PostgreSQL service or paid resources required."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from scripts.migrate_memory_postgres import read_snapshot, migration_plan, migrate, SCHEMA

class PostgresMigrationTests(unittest.TestCase):
    @contextmanager
    def source_db(self):
        # Explicit close is required on Windows for TemporaryDirectory cleanup.
        db=sqlite3.connect(self.path)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"source.sqlite"
        with self.source_db() as db:
            db.executescript("""
            CREATE TABLE memory_entries (
              id INTEGER PRIMARY KEY, domain TEXT,target_object TEXT,title TEXT,
              resolution TEXT,evidence TEXT,version INTEGER,state TEXT,reviewer TEXT,
              review_note TEXT,created_at TEXT,reviewed_at TEXT,supersedes_id INTEGER
            );
            CREATE TABLE memory_events (
              id INTEGER PRIMARY KEY,entry_id INTEGER,action TEXT,note TEXT,
              actor TEXT,created_at TEXT
            );
            INSERT INTO memory_entries VALUES
             (1,'Vendor','SUPPLIER','Old mapping','Old mapping evidence','SYNTH-1',1,
              'superseded','Steward','Reviewed','2026-01-01','2026-01-02',NULL),
             (2,'Vendor','SUPPLIER','New mapping','New mapping evidence','SYNTH-2',2,
              'approved','Steward','Reviewed','2026-01-03','2026-01-04',1);
            INSERT INTO memory_events VALUES
             (1,1,'approved','Approved','Steward','2026-01-02'),
             (2,1,'superseded','Replaced','Steward','2026-01-04'),
             (3,2,'approved','Approved','Steward','2026-01-04');
            """)
    def tearDown(self):
        self.temp.cleanup()
    def test_dry_run_is_read_only_and_counts_audit(self):
        before=self.path.read_bytes()
        plan=migration_plan(self.path)
        self.assertEqual(plan["memory_entries"],2)
        self.assertEqual(plan["memory_events"],3)
        self.assertEqual(plan["requires_empty_destination"],True)
        self.assertEqual(self.path.read_bytes(),before)
        entries,events=read_snapshot(self.path)
        self.assertEqual(entries[1][-1],1)
        self.assertEqual(events[-1][1],2)
    def test_missing_source_does_not_create_database(self):
        missing=Path(self.temp.name)/"absent.sqlite"
        with self.assertRaises(FileNotFoundError):
            migration_plan(missing)
        self.assertFalse(missing.exists())
    def test_orphan_audit_rejected(self):
        with self.source_db() as db:
            db.execute("INSERT INTO memory_events VALUES(4,999,'approved','bad','Steward','2026-01-05')")
        with self.assertRaisesRegex(ValueError,"orphaned audit"):
            read_snapshot(self.path)
    def test_orphan_supersession_rejected(self):
        with self.source_db() as db:
            db.execute("UPDATE memory_entries SET supersedes_id=999 WHERE id=2")
        with self.assertRaisesRegex(ValueError,"orphaned supersession"):
            read_snapshot(self.path)
    def test_invalid_governance_state_rejected(self):
        with self.source_db() as db:
            db.execute("UPDATE memory_entries SET state='unreviewed' WHERE id=2")
        with self.assertRaisesRegex(ValueError,"Invalid memory state"):
            read_snapshot(self.path)
    def test_supersession_scope_mismatch_rejected(self):
        with self.source_db() as db:
            db.execute("UPDATE memory_entries SET domain='Finance' WHERE id=2")
        with self.assertRaisesRegex(ValueError,"Invalid supersession scope"):
            read_snapshot(self.path)
    def test_supersession_cycle_rejected(self):
        with self.source_db() as db:
            db.execute("UPDATE memory_entries SET supersedes_id=2 WHERE id=1")
        with self.assertRaisesRegex(ValueError,"supersession cycle"):
            read_snapshot(self.path)
    def test_competing_draft_successors_rejected(self):
        with self.source_db() as db:
            db.execute("UPDATE memory_entries SET state='draft' WHERE id=2")
            db.execute("""INSERT INTO memory_entries VALUES
              (3,'Vendor','SUPPLIER','Competing','Conflict','SYNTH-3',2,'draft',
               NULL,NULL,'2026-01-05',NULL,1)""")
        with self.assertRaisesRegex(ValueError,"competing draft"):
            read_snapshot(self.path)
    def test_duplicate_audit_ids_rejected(self):
        # A duplicate is impossible under the canonical PK, so simulate an
        # exported SQLite table without the constraint.
        with self.source_db() as db:
            db.executescript("""ALTER TABLE memory_events RENAME TO old_events;
                CREATE TABLE memory_events(id INTEGER,entry_id INTEGER,action TEXT,
                    note TEXT,actor TEXT,created_at TEXT);
                INSERT INTO memory_events SELECT * FROM old_events;
                DROP TABLE old_events;""")
            db.execute("INSERT INTO memory_events SELECT * FROM memory_events WHERE id=1")
        with self.assertRaisesRegex(ValueError,"Duplicate source audit"):
            read_snapshot(self.path)

    def test_reviewed_successor_requires_retired_parent(self):
        with self.source_db() as db:
            db.execute("UPDATE memory_entries SET state='approved' WHERE id=1")
        with self.assertRaisesRegex(ValueError,"non-superseded predecessor"):
            read_snapshot(self.path)

    def test_superseded_entry_requires_reviewed_successor(self):
        with self.source_db() as db:
            db.execute("UPDATE memory_entries SET state='rejected' WHERE id=2")
        with self.assertRaisesRegex(ValueError,"lacks a reviewed successor"):
            read_snapshot(self.path)

    def test_competing_approved_successors_rejected(self):
        with self.source_db() as db:
            db.execute("""INSERT INTO memory_entries VALUES
                (3,'Vendor','SUPPLIER','Competing','Conflict','SYNTH-3',2,'approved',
                 'Steward','Approved','2026-01-05','2026-01-06',1)""")
        with self.assertRaisesRegex(ValueError,"competing reviewed successors"):
            read_snapshot(self.path)

    def test_no_dsn_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"PRISM_POSTGRES_DSN"):
            migrate(self.path,"")
    def test_schema_has_approval_and_unique_draft_guards(self):
        self.assertIn("memory_one_draft_per_parent",SCHEMA)
        self.assertIn("state='draft' AND supersedes_id IS NOT NULL",SCHEMA)
        self.assertIn("REFERENCES memory_entries(id)",SCHEMA)
if __name__=="__main__":
    unittest.main()
