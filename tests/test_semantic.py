"""No database or model downloads: isolated pgvector adapter tests."""
import unittest
from unittest.mock import MagicMock
from app.semantic import (VECTOR_DIMENSION, SEARCH_SQL, SCHEMA_SQL, UPSERT_SQL,
                          vector_literal, search_approved, upsert_approved,
                          retire_entry, local_encoder, SemanticUnavailable)

def sample_vector():
    return [1.0] + [0.0] * (VECTOR_DIMENSION - 1)

class PgvectorSemanticTests(unittest.TestCase):
    def test_vector_rejects_invalid_shape_and_nonfinite(self):
        for bad in ([1.0], [0.0] * VECTOR_DIMENSION,
                    [float("nan")] + [1.0] * (VECTOR_DIMENSION - 1),
                    [float("inf")] + [1.0] * (VECTOR_DIMENSION - 1)):
            with self.assertRaises(ValueError):
                vector_literal(bad)
        self.assertTrue(vector_literal(sample_vector()).startswith("[1,"))

    def test_search_is_approval_gated_and_scoped_in_sql(self):
        db=MagicMock()
        cursor=db.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value=[(12, 3, 0.21)]
        result=search_approved(db,tenant_id="company-A",domain="Vendor",
                               target_object="SUPPLIER",embedding=sample_vector(),limit=3)
        self.assertEqual(result,[{"entry_id":12,"version":3,"distance":0.21}])
        sql,args=cursor.execute.call_args.args
        self.assertEqual(sql,SEARCH_SQL)
        self.assertIn("state = 'approved'",sql)
        self.assertIn("tenant_id = %s",sql)
        self.assertEqual(args[1:4],("company-A","Vendor","SUPPLIER"))
        self.assertEqual(args[-1],3)

    def test_scope_is_mandatory(self):
        db=MagicMock()
        for params in ({"tenant_id":""},{"domain":""},{"target_object":""},
                       {"limit":0},{"limit":101},{"limit":True}):
            args=dict(tenant_id="company-A",domain="Vendor",
                      target_object="SUPPLIER",embedding=sample_vector())
            args.update(params)
            with self.assertRaises(ValueError):
                search_approved(db,**args)
        db.cursor.assert_not_called()

    def test_approved_index_and_retirement_are_tenant_scoped(self):
        db=MagicMock()
        cursor=db.cursor.return_value.__enter__.return_value
        upsert_approved(db,tenant_id="company-A",entry_id=7,domain="Vendor",
                        target_object="SUPPLIER",version=2,embedding=sample_vector())
        sql,args=cursor.execute.call_args.args
        self.assertEqual(sql,UPSERT_SQL)
        self.assertEqual(args[:6],("company-A",7,"Vendor","SUPPLIER","approved",2))
        retire_entry(db,tenant_id="company-A",entry_id=7)
        sql,args=cursor.execute.call_args.args
        self.assertIn("tenant_id=%s AND entry_id=%s",sql)
        self.assertEqual(args,("company-A",7))

    def test_local_model_missing_fails_closed(self):
        with self.assertRaises(SemanticUnavailable):
            local_encoder("/definitely/missing/local/model")

    def test_schema_has_tenant_key_and_vector_dimension(self):
        self.assertIn("PRIMARY KEY (tenant_id, entry_id)",SCHEMA_SQL)
        self.assertIn("embedding vector(384)",SCHEMA_SQL)
        self.assertNotIn("DROP TABLE",SCHEMA_SQL)

if __name__=="__main__":
    unittest.main()
