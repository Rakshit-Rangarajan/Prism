"""Regression tests for strict demo-run input validation and JSON safety."""
import os
import tempfile
import unittest

_TEMP = tempfile.TemporaryDirectory()
os.environ.setdefault("PRISM_DB", os.path.join(_TEMP.name, "prism.sqlite3"))
os.environ.setdefault("PRISM_ERP_DEMO_DB", os.path.join(_TEMP.name, "erp.sqlite3"))
os.environ.setdefault("PRISM_DEMO_PASSWORD", "synthetic-test-password")

from fastapi.testclient import TestClient  # noqa: E402
from app.server import app  # noqa: E402

AUTH = ("prism", "synthetic-test-password")


class ApiHardeningTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.post("/api/demo/erp/reset", json={"confirmation": "RESET SYNTHETIC DEMO"}, auth=AUTH)

    def tearDown(self):
        self.client.close()

    def post_raw(self, body, path="/api/demo/erp/run"):
        return self.client.post(path, content=body, headers={"Content-Type": "application/json"}, auth=AUTH)

    def test_string_apply_is_rejected_before_any_target_write(self):
        response = self.post_raw('{"apply":"yes"}')
        self.assertEqual(response.status_code, 422)
        run = self.client.post("/api/demo/erp/run", json={"apply": False}, auth=AUTH).json()
        self.assertEqual(run["reconciliation"]["target_total_records"], 0)

    def test_numeric_apply_is_rejected(self):
        self.assertEqual(self.post_raw('{"apply":1}').status_code, 422)

    def test_boolean_apply_still_works(self):
        response = self.client.post("/api/demo/erp/run", json={"apply": False}, auth=AUTH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "preview")

    def test_non_finite_json_constants_return_422(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                response = self.post_raw('{"apply":' + token + '}')
                self.assertEqual(response.status_code, 422)
                self.assertIn("Invalid JSON numeric literal", response.json()["detail"])

    def test_valid_json_without_apply_defaults_to_preview(self):
        response = self.post_raw("{}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "preview")


if __name__ == "__main__":
    unittest.main()
