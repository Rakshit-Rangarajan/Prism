"""Company-scoped learning pipeline tests.

Synthetic data only, isolated SQLite, no network and no production credentials.
"""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.server import app

AUTH = ("prism", "synthetic-test-password")


class CompanyLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "PRISM_LEARNING_DB": os.path.join(self.tmp.name, "learning.sqlite3"),
            "PRISM_MODEL_ARTIFACT_ROOT": os.path.join(self.tmp.name, "models"),
            "PRISM_DEMO_PASSWORD": "synthetic-test-password",
            "PRISM_ENABLE_LIVE_DB_SOURCES": "false",
        })
        self.env.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.tmp.cleanup()

    def create_company(self, name="Alpha", slug="alpha"):
        response = self.client.post("/api/company-learning/companies", json={
            "name": name, "slug": slug, "description": "Synthetic QA company"
        }, auth=AUTH)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def approve_first(self, company_id, task, count):
        examples = self.client.get(
            f"/api/company-learning/{company_id}/examples?task={task}&state=draft", auth=AUTH
        ).json()
        approved = []
        for example in examples[:count]:
            response = self.client.post(
                f"/api/company-learning/{company_id}/examples/{example['id']}/approve",
                json={"confirmation": "APPROVE TRAINING EXAMPLE"}, auth=AUTH,
            )
            self.assertEqual(response.status_code, 200, response.text)
            approved.append(example["id"])
        return approved

    def test_capabilities_declare_honest_defaults(self):
        response = self.client.get("/api/company-learning/capabilities", auth=AUTH)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["tasks"]), 4)
        self.assertEqual(data["default_method"], "deterministic")
        self.assertFalse(data["default_method_is_llm"])
        self.assertFalse(data["live_db_sources_enabled"])

    def test_auth_is_required(self):
        self.assertEqual(self.client.get("/api/company-learning/companies").status_code, 401)

    def test_company_creation_rejects_duplicate_slug(self):
        self.create_company()
        duplicate = self.client.post("/api/company-learning/companies", json={
            "name": "Alpha Two", "slug": "alpha"
        }, auth=AUTH)
        self.assertEqual(duplicate.status_code, 409)

    def test_bootstrap_creates_four_task_datasets_and_approval_gates_retrieval(self):
        company_id = self.create_company()
        response = self.client.post(f"/api/company-learning/{company_id}/bootstrap", auth=AUTH)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["examples_created"], {task: 12 for task in data["examples_created"]})
        self.assertTrue(data["synthetic"])

        drafts = self.client.get(
            f"/api/company-learning/{company_id}/examples?task=schema_mapping&state=draft", auth=AUTH
        ).json()
        query = {"task": "schema_mapping", "query": json.dumps(drafts[0]["input"])[:900], "limit": 5}
        before = self.client.post(
            f"/api/company-learning/{company_id}/rag/query", json=query, auth=AUTH
        ).json()
        self.assertEqual(before["results"], [])

        weak = self.client.post(
            f"/api/company-learning/{company_id}/examples/{drafts[0]['id']}/approve",
            json={"confirmation": "yes"}, auth=AUTH,
        )
        self.assertEqual(weak.status_code, 422)
        self.approve_first(company_id, "schema_mapping", 1)
        after = self.client.post(
            f"/api/company-learning/{company_id}/rag/query", json=query, auth=AUTH
        ).json()
        self.assertTrue(after["results"])
        self.assertEqual(after["approved_only"], True)
        self.assertEqual(after["retrieval"], "deterministic-hash-embedding")

    def test_company_isolation_blocks_cross_company_access(self):
        first = self.create_company("Alpha", "alpha")
        second = self.create_company("Beta", "beta")
        self.client.post(f"/api/company-learning/{first}/bootstrap", auth=AUTH)
        examples = self.client.get(
            f"/api/company-learning/{first}/examples?state=draft", auth=AUTH).json()
        foreign_id = examples[0]["id"]

        denied = self.client.post(
            f"/api/company-learning/{second}/examples/{foreign_id}/approve",
            json={"confirmation": "APPROVE TRAINING EXAMPLE"}, auth=AUTH,
        )
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(self.client.get(
            f"/api/company-learning/{second}/examples", auth=AUTH).json(), [])
        blocked = self.client.post(f"/api/company-learning/{second}/train", json={
            "task": "schema_mapping", "method": "deterministic", "epochs": 1
        }, auth=AUTH)
        self.assertEqual(blocked.status_code, 422)

        self.approve_first(first, "schema_mapping", 8)
        trained = self.client.post(f"/api/company-learning/{first}/train", json={
            "task": "schema_mapping", "method": "deterministic", "epochs": 2
        }, auth=AUTH).json()
        model_id = max(
            model["id"] for model in self.client.get(
                f"/api/company-learning/{first}/models", auth=AUTH).json())
        self.assertEqual(self.client.get(
            f"/api/company-learning/{second}/models/{model_id}/artifact", auth=AUTH).status_code, 404)
        self.assertGreater(trained["metrics"]["accuracy"], 0.0)

    def test_training_evaluation_model_approval_and_prediction(self):
        company_id = self.create_company()
        self.client.post(f"/api/company-learning/{company_id}/bootstrap", auth=AUTH)
        self.approve_first(company_id, "schema_mapping", 10)

        before = self.client.post(f"/api/company-learning/{company_id}/predict", json={
            "task": "schema_mapping",
            "input": {"source_system": "LEGACY_ERP", "source_table": "VEND_MAST",
                      "columns": ["VEND_ID", "VEND_NM", "VEND_AMT"]},
        }, auth=AUTH).json()
        self.assertEqual(before["mode"], "rag-only")

        trained = self.client.post(f"/api/company-learning/{company_id}/train", json={
            "task": "schema_mapping", "method": "deterministic", "epochs": 3
        }, auth=AUTH)
        self.assertEqual(trained.status_code, 200, trained.text)
        result = trained.json()
        self.assertEqual(result["status"], "evaluated")
        self.assertFalse(result["metrics"]["is_llm"])
        self.assertGreaterEqual(result["metrics"]["accuracy"], 0.0)
        self.assertEqual(result["metrics"]["train_examples"] + result["metrics"]["holdout_examples"], 10)

        models = self.client.get(f"/api/company-learning/{company_id}/models", auth=AUTH).json()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["state"], "candidate")
        weak = self.client.post(
            f"/api/company-learning/{company_id}/models/{models[0]['id']}/approve",
            json={"confirmation": "approve"}, auth=AUTH)
        self.assertEqual(weak.status_code, 422)

        approved = self.client.post(
            f"/api/company-learning/{company_id}/models/{models[0]['id']}/approve",
            json={"confirmation": "APPROVE COMPANY MODEL"}, auth=AUTH)
        self.assertEqual(approved.status_code, 200)
        prediction = self.client.post(f"/api/company-learning/{company_id}/predict", json={
            "task": "schema_mapping",
            "input": {"source_system": "LEGACY_ERP", "source_table": "VEND_MAST",
                      "columns": ["VEND_ID", "VEND_NM", "VEND_AMT"]},
        }, auth=AUTH).json()
        self.assertEqual(prediction["mode"], "model+rag")
        self.assertEqual(prediction["provenance"]["method"], "deterministic")
        self.assertEqual(prediction["provenance"]["model_id"], models[0]["id"])
        self.assertTrue(prediction["supporting_examples"])

        artifact = self.client.get(
            f"/api/company-learning/{company_id}/models/{models[0]['id']}/artifact", auth=AUTH)
        self.assertEqual(artifact.status_code, 200)
        self.assertEqual(artifact.json()["format"], "prism-deterministic-v1")

    def test_anonymized_ingest_scrubs_pii_before_storage(self):
        company_id = self.create_company()
        ingest = self.client.post(f"/api/company-learning/{company_id}/sources/anonymized", json={
            "name": "Redacted export",
            "records": [{
                "task": "exception_classification",
                "input": {"error_message": "owner jane.doe@example.com at 10.20.30.40 phone +1 555 123 4567"},
                "output": {"category": "contact_data", "severity": "low",
                           "recommended_action": "use the redacted contact record", "evidence": "SYN-001"},
            }],
        }, auth=AUTH)
        self.assertEqual(ingest.status_code, 201, ingest.text)
        self.assertGreater(ingest.json()["scrubbed_values"], 0)
        raw = self.client.get(
            f"/api/company-learning/{company_id}/examples?task=exception_classification", auth=AUTH).json()
        self.assertTrue(raw)
        serialized = json.dumps(raw)
        self.assertNotIn("jane.doe@example.com", serialized)
        self.assertNotIn("10.20.30.40", serialized)
        self.assertIn("<EMAIL>", serialized)
        self.assertEqual(raw[0]["state"], "draft")

    def test_live_source_is_opt_in_read_only_and_schema_only(self):
        company_id = self.create_company()
        disabled = self.client.post(f"/api/company-learning/{company_id}/sources/live", json={
            "name": "Local read-only", "dsn_env_var": "PRISM_QA_LIVE_DSN"
        }, auth=AUTH)
        self.assertEqual(disabled.status_code, 503)

        root = os.path.join(self.tmp.name, "live-db")
        os.makedirs(root, exist_ok=True)
        db_path = os.path.join(root, "legacy.sqlite3")
        db = sqlite3.connect(db_path)
        db.execute("CREATE TABLE VEND_MAST (VEND_ID TEXT, VEND_NM TEXT, SECRET_NOTE TEXT)")
        db.execute("INSERT INTO VEND_MAST VALUES(?,?,?)", ("C001", "acme", "jane.doe@example.com"))
        db.commit()
        db.close()

        with patch.dict(os.environ, {
            "PRISM_ENABLE_LIVE_DB_SOURCES": "true",
            "PRISM_LIVE_DB_ROOT": root,
            "PRISM_QA_LIVE_DSN": "sqlite:///" + db_path,
        }):
            response = self.client.post(f"/api/company-learning/{company_id}/sources/live", json={
                "name": "Local read-only", "dsn_env_var": "PRISM_QA_LIVE_DSN"
            }, auth=AUTH)
            self.assertEqual(response.status_code, 201, response.text)
            data = response.json()
            self.assertTrue(data["read_only"])
            self.assertIn("VEND_MAST", data["tables"])
            self.assertEqual(data["examples_created"], 1)
            examples = self.client.get(
                f"/api/company-learning/{company_id}/examples?task=schema_mapping", auth=AUTH).json()
            self.assertEqual(examples[0]["input"]["samples"], {})
            self.assertNotIn("jane.doe@example.com", json.dumps(examples))

        outside = os.path.join(self.tmp.name, "outside.sqlite3")
        with patch.dict(os.environ, {
            "PRISM_ENABLE_LIVE_DB_SOURCES": "true",
            "PRISM_LIVE_DB_ROOT": root,
            "PRISM_QA_LIVE_DSN": "sqlite:///" + outside,
        }):
            blocked = self.client.post(f"/api/company-learning/{company_id}/sources/live", json={
                "name": "Outside root", "dsn_env_var": "PRISM_QA_LIVE_DSN"
            }, auth=AUTH)
            self.assertEqual(blocked.status_code, 422)

    def test_lora_preflight_is_blocked_without_optional_dependencies(self):
        company_id = self.create_company()
        self.client.post(f"/api/company-learning/{company_id}/bootstrap", auth=AUTH)
        self.approve_first(company_id, "sql_conversion", 6)
        with patch("app.company_learning.importlib.util.find_spec", return_value=None):
            response = self.client.post(f"/api/company-learning/{company_id}/train", json={
                "task": "sql_conversion", "method": "lora", "epochs": 1
            }, auth=AUTH)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "blocked")
        self.assertIn("torch", response.json()["error"])
        runs = self.client.get(f"/api/company-learning/{company_id}/runs", auth=AUTH).json()
        self.assertEqual(runs[0]["status"], "blocked")
        self.assertEqual(self.client.get(
            f"/api/company-learning/{company_id}/models", auth=AUTH).json(), [])

    def test_dataset_export_contains_only_approved_records(self):
        company_id = self.create_company()
        self.client.post(f"/api/company-learning/{company_id}/bootstrap", auth=AUTH)
        approved = self.approve_first(company_id, "sap_object_mapping", 5)
        dataset = self.client.get(
            f"/api/company-learning/{company_id}/dataset?task=sap_object_mapping", auth=AUTH).json()
        self.assertEqual(dataset["count"], len(approved))
        self.assertEqual(dataset["format"], "instruction-input-output")
        self.assertTrue(all(record["instruction"] for record in dataset["records"]))


if __name__ == "__main__":
    unittest.main()
