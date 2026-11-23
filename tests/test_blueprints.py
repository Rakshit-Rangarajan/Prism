"""Synthetic-only blueprint persistence and validation regression tests."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import ValidationError
from app import server
from app import blueprints

SAMPLE = dict(company="Example Company", source="IBM Db2",
              destination="SAP S/4HANA", sourceType="sql", targetType="erp",
              volume=1000, priority="quality", model="ollama", isolation=True)

class BlueprintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "blueprints.sqlite")
        @contextmanager
        def db():
            c = sqlite3.connect(self.path)
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            finally:
                c.close()
        self.patch = patch.object(blueprints, "connection", db)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_create_and_retrieve(self):
        result = blueprints.create_blueprint(blueprints.Blueprint(**SAMPLE))
        self.assertEqual(result["status"], "draft")
        self.assertFalse(result["execution_enabled"])
        self.assertEqual(result["blueprint"]["sourceType"], "sql")
        self.assertEqual(blueprints.get_blueprint(result["id"], "Example Company"), result)

    def test_company_scope(self):
        first = blueprints.create_blueprint(blueprints.Blueprint(**SAMPLE))
        second = blueprints.create_blueprint(blueprints.Blueprint(**{**SAMPLE,"company":"Other Company"}))
        self.assertEqual([r["id"] for r in blueprints.list_blueprints("Example Company")["results"]], [first["id"]])
        self.assertEqual([r["id"] for r in blueprints.list_blueprints("Other Company")["results"]], [second["id"]])
        with self.assertRaises(HTTPException) as error:
            blueprints.get_blueprint(first["id"], "Other Company")
        self.assertEqual(error.exception.status_code, 404)

    def test_rejects_unapproved_format_and_model(self):
        for key, value in [("sourceType","malicious"), ("targetType","unknown"),
                           ("model","cloud-external"), ("priority","unsafe"),
                           ("isolation",False), ("volume",0)]:
            with self.subTest(key=key), self.assertRaises(ValidationError):
                blueprints.Blueprint(**{**SAMPLE,key:value})

    def test_no_execution_and_deterministic_order(self):
        ids = [blueprints.create_blueprint(blueprints.Blueprint(**SAMPLE))["id"] for _ in range(3)]
        result = blueprints.list_blueprints("Example Company",limit=2)
        self.assertEqual([r["id"] for r in result["results"]], ids[-1:-3:-1])
        self.assertEqual(result["mode"], "design-only")
        self.assertEqual(result["durability"], "ephemeral-sqlite")

if __name__ == "__main__":
    unittest.main()
