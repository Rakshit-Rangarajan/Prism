"""Synthetic migration dry-run regression tests; no external services required."""
import unittest
from app.migration_preview import FieldMap, preview_migration

class MigrationPreviewTests(unittest.TestCase):
    def test_converts_and_preserves_source(self):
        rows = [{"id": "0042", "amount": "10.50", "active": "yes"}]
        before = [dict(row) for row in rows]
        result = preview_migration(rows, [
            FieldMap("id", "supplier_id", "integer"),
            FieldMap("amount", "balance", "decimal"),
            FieldMap("active", "enabled", "boolean")])
        self.assertEqual(result["records"], [{"supplier_id": 42, "balance": "10.50", "enabled": True}])
        self.assertEqual(rows, before)
        self.assertFalse(result["writes_performed"])

    def test_rejects_bad_rows_without_partial_row(self):
        result = preview_migration([{"id": "1", "amount": "bad"}, {"id": "2", "amount": "3.00"}],
            [FieldMap("id", "id", "integer"), FieldMap("amount", "amount", "decimal")])
        self.assertEqual(result["valid_count"], 1)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["records"], [{"id": 2, "amount": "3.00"}])
        self.assertEqual(result["errors"][0]["field"], "amount")

    def test_missing_required_and_invalid_types(self):
        result = preview_migration([{}, {"x": None}, {"x": "NaN"}, {"x": True}],
            [FieldMap("x", "number", "decimal")])
        self.assertEqual(result["valid_count"], 0)
        self.assertEqual(result["invalid_count"], 4)

    def test_fails_closed_for_invalid_mapping_and_size(self):
        with self.assertRaises(ValueError):
            preview_migration([{}], [FieldMap("a", "x", "text"), FieldMap("b", "x", "text")])
        with self.assertRaises(ValueError):
            preview_migration([{}] * 1001, [FieldMap("a", "a", "text")])
        with self.assertRaises(ValueError):
            preview_migration([], [FieldMap("a", "a", "binary")])
        with self.assertRaises(ValueError):
            preview_migration([], [])

class MigrationPreviewSafetyTests(unittest.TestCase):
    def test_oversized_text_fails_row_without_partial_output(self):
        result = preview_migration([{"id": "1", "name": "x" * 4097}],
            [FieldMap("id", "id", "integer"), FieldMap("name", "name", "text")])
        self.assertEqual(result["valid_count"], 0)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["records"], [])
        self.assertEqual(result["errors"][0]["field"], "name")
        self.assertFalse(result["writes_performed"])

    def test_mapping_validation_rejects_malformed_objects(self):
        for mappings in ([object()], [FieldMap([], "target", "text")],
                         [FieldMap("source", "target", "text", required="false")],
                         [FieldMap("source", "x" * 129, "text")]):
            with self.subTest(mappings=mappings):
                with self.assertRaises(ValueError):
                    preview_migration([], mappings)

    def test_text_boundary_accepted(self):
        result = preview_migration([{"name": "x" * 4096}], [FieldMap("name", "name", "text")])
        self.assertEqual(result["valid_count"], 1)


if __name__ == "__main__":
    unittest.main()
