"""Migration Memory approval and relevance regression tests (synthetic data)."""
import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from fastapi import HTTPException
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
        self.assertEqual(memory.search_memory(q="supplier",domain="Vendor",target_object="SUPPLIER")["results"],[])
        memory.review_entry(a,memory.Review(action="approved",reviewer="Steward",note="Validated synthetic source"))
        memory.review_entry(b,memory.Review(action="rejected",reviewer="Steward",note="Insufficient evidence"))
        result=memory.search_memory(q="tax code",domain="Vendor",target_object="SUPPLIER")
        self.assertEqual([x["id"] for x in result["results"]],[a])
        self.assertEqual(result["retrieval"],"bm25-lexical")
        self.assertEqual(memory.search_memory(q="tax",domain="Finance")["results"],[])
        self.assertEqual(memory.search_memory(q="tax",target_object="PRODUCT")["results"],[])
    def test_review_is_immutable(self):
        identifier=self.create("Supplier account validation")
        memory.review_entry(identifier,memory.Review(action="approved",reviewer="Steward",note="Reviewed with evidence"))
        with self.assertRaises(HTTPException) as ctx:
            memory.review_entry(identifier,memory.Review(action="rejected",reviewer="Steward",note="Attempted re-review"))
        self.assertEqual(ctx.exception.status_code,409)
        self.assertEqual([x["action"] for x in memory.entry_events(identifier)],["created","approved"])
    def test_no_match_and_limit(self):
        ids=[self.create("Supplier mapping "+str(i)) for i in range(4)]
        for i in ids:
            memory.review_entry(i,memory.Review(action="approved",reviewer="Steward",note="Approved synthetic"))
        self.assertEqual(memory.search_memory(q="unmatchedword",domain="Vendor")["results"],[])
        self.assertEqual(len(memory.search_memory(q="",domain="Vendor",limit=2)["results"]),2)

if __name__=="__main__":
    unittest.main()
