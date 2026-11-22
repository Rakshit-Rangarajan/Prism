"""Migration Memory approval and relevance regression tests (synthetic data)."""
import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from fastapi import HTTPException
from app import server  # initialize FastAPI routes before memory's server dependencies
from app import memory
import sqlite3

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=os.path.join(self.temp.name,"memory.sqlite")
        @contextmanager
        def db():
            c=sqlite3.connect(self.path)
            c.row_factory=sqlite3.Row
            try:
                yield c
                c.commit()
            finally:
                c.close()
        self.patch=patch.object(memory,"connection",db)
        self.patch.start()
    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()
    def create(self,title,resolution="Use approved mapping crosswalk evidence."):
        return memory.create_entry(memory.MemoryEntry(domain="Vendor",target_object="SUPPLIER",title=title,resolution=resolution,evidence="SYNTH-001"))["id"]
    def test_approval_gate_and_ranking(self):
        a=self.create("Supplier tax code mapping", "Validate supplier tax code against approved lookup")
        b=self.create("Supplier account reconciliation", "Reconcile supplier account using signed chart")
        self.assertEqual(memory.search_memory(q="supplier",domain="Vendor",target_object="SUPPLIER",limit=20)["results"],[])
        memory.review_entry(a,memory.Review(action="approved",reviewer="Steward",note="Validated synthetic source"))
        memory.review_entry(b,memory.Review(action="rejected",reviewer="Steward",note="Insufficient evidence"))
        result=memory.search_memory(q="tax code",domain="Vendor",target_object="SUPPLIER",limit=20)
        self.assertEqual([x["id"] for x in result["results"]],[a])
        self.assertEqual(result["retrieval"],"bm25-lexical")
        self.assertEqual(memory.search_memory(q="tax",domain="Finance",target_object="",limit=20)["results"],[])
        self.assertEqual(memory.search_memory(q="tax",domain="",target_object="PRODUCT",limit=20)["results"],[])
    def test_review_is_immutable(self):
        identifier=self.create("Supplier account validation")
        memory.review_entry(identifier,memory.Review(action="approved",reviewer="Steward",note="Reviewed with evidence"))
        with self.assertRaises(HTTPException) as ctx:
            memory.review_entry(identifier,memory.Review(action="rejected",reviewer="Steward",note="Attempted re-review"))
        self.assertEqual(ctx.exception.status_code,409)
        self.assertEqual([x["action"] for x in memory.entry_events(identifier)],["created","approved"])
    def test_revision_approval_supersedes_predecessor(self):
        old=self.create("Supplier tax mapping version one")
        memory.review_entry(old,memory.Review(action="approved",reviewer="Steward",note="Validated old version"))
        new=memory.revise_entry(old,memory.Revision(title="Supplier tax mapping version two",resolution="Use corrected approved tax mapping reference.",evidence="SYNTH-REV-002"))["id"]
        self.assertEqual(memory.search_memory(q="",domain="Vendor",target_object="SUPPLIER",limit=20)["results"][0]["id"],old)
        with self.assertRaises(HTTPException) as ctx:
            memory.revise_entry(old,memory.Revision(title="Competing draft revision",resolution="Another proposed replacement rule.",evidence="SYNTH-REV-003"))
        self.assertEqual(ctx.exception.status_code,409)
        memory.review_entry(new,memory.Review(action="approved",reviewer="Steward",note="New mapping reviewed"))
        current=memory.search_memory(q="",domain="Vendor",target_object="SUPPLIER",limit=20)["results"]
        self.assertEqual([r["id"] for r in current],[new])
        self.assertEqual(current[0]["version"],2)
        self.assertEqual(current[0]["supersedes_id"],old)
        self.assertEqual([e["action"] for e in memory.entry_events(old)],["created","approved","superseded"])

    def test_rejected_revision_preserves_approved_version(self):
        old=self.create("Supplier account reference original")
        memory.review_entry(old,memory.Review(action="approved",reviewer="Steward",note="Original approved"))
        new=memory.revise_entry(old,memory.Revision(title="Supplier account alternative",resolution="Alternative proposed mapping approach.",evidence="SYNTH-REV-004"))["id"]
        memory.review_entry(new,memory.Review(action="rejected",reviewer="Steward",note="No adequate evidence"))
        result=memory.search_memory(q="",domain="Vendor",target_object="SUPPLIER",limit=20)
        self.assertEqual([r["id"] for r in result["results"]],[old])

    def test_database_rejects_competing_draft_successors(self):
        old=self.create("Supplier mapping approved parent")
        memory.review_entry(old,memory.Review(action="approved",reviewer="Steward",note="Approved synthetic mapping"))
        memory.revise_entry(old,memory.Revision(title="Supplier mapping next version",resolution="Use a reviewed successor mapping.",evidence="SYNTH-REV-101"))
        with sqlite3.connect(self.path) as c:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute("""INSERT INTO memory_entries(domain,target_object,title,resolution,evidence,version,state,supersedes_id)
                    VALUES(?,?,?,?,?,?,?,?)""",("Vendor","SUPPLIER","Competing successor","A conflicting draft mapping.","SYNTH-REV-102",2,"draft",old))

    def test_review_transaction_commits_audit_and_supersession(self):
        old=self.create("Supplier reviewed predecessor")
        memory.review_entry(old,memory.Review(action="approved",reviewer="Steward",note="Validated predecessor"))
        new=memory.revise_entry(old,memory.Revision(title="Supplier reviewed successor",resolution="Corrected reviewed mapping details.",evidence="SYNTH-REV-103"))["id"]
        memory.review_entry(new,memory.Review(action="approved",reviewer="Steward",note="Validated successor"))
        with sqlite3.connect(self.path) as c:
            self.assertEqual(c.execute("SELECT state FROM memory_entries WHERE id=?",(old,)).fetchone()[0],"superseded")
            self.assertEqual(c.execute("SELECT state FROM memory_entries WHERE id=?",(new,)).fetchone()[0],"approved")
            self.assertEqual(c.execute("SELECT COUNT(*) FROM memory_events WHERE action='superseded' AND entry_id=?",(old,)).fetchone()[0],1)

    def test_no_match_and_limit(self):
        ids=[self.create("Supplier mapping "+str(i)) for i in range(4)]
        for i in ids:
            memory.review_entry(i,memory.Review(action="approved",reviewer="Steward",note="Approved synthetic"))
        self.assertEqual(memory.search_memory(q="unmatchedword",domain="Vendor",target_object="",limit=20)["results"],[])
        self.assertEqual(len(memory.search_memory(q="",domain="Vendor",target_object="",limit=2)["results"]),2)

if __name__=="__main__":
    unittest.main()
