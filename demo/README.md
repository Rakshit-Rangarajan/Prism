# PRISM ERP learning demo (experimental)

This is an **offline, synthetic demonstration**, not a production migration engine or SAP integration. No external data, credentials, model downloads, or live database writes.

## Run

From repository root:

```bash
python -m unittest discover -s demo -p 'test_*.py' -v
python demo/erp_learning_pipeline.py --db /tmp/prism-demo.sqlite
python demo/erp_learning_pipeline.py --db /tmp/prism-demo.sqlite --apply
python demo/erp_learning_pipeline.py --db /tmp/prism-demo.sqlite --approve-legacy-format --apply
```

The first run previews 20 synthetic scenarios. The second attempts a local SQLite target migration and records errors. The third explicitly approves a narrowly defined repair rule and replays the scenarios. Approved repairs persist across runs and are reused for both currency-symbol and thousands-separator errors. Other errors remain rejected and are recorded as observations; they are **not automatically repaired**. The demo prints JSON results including rejected records and reused lessons.

**Limitations:** This initial increment uses SQLite, not PostgreSQL; it has no UI or API integration, no ML training, no external ERP source adapter, and no real SAP target. Approval is a local command-line demonstration, not authenticated enterprise governance. No production deployment is implied. Do not merge until full repository tests and security review pass.

**Next increments:** integrate PostgreSQL and tenant-scoped governance, add API/UI stepper, export reconciliation report, add regression and Playwright tests, and deploy to staging before production.

## Integrated PRISM demo UI/API (feature branch only)

After installing the repository's backend and frontend dependencies, run the app normally.
In the sidebar open **ERP Learning Demo**.

1. **Preview 20 records**: generates synthetic source input and records issues in isolated local demo SQLite; target records remain unchanged.
2. **Approve learned rule**: after inspection, authorize only the demonstrated `amount:legacy_format` normalization. Approval requires exact confirmation and existing Basic Auth.
3. **Execute local migration**: validates each record and writes accepted records to the isolated synthetic SQLite target, preserving rejections for review.
4. **Export reconciliation JSON**: includes per-record results, rejected signatures, target counts and reused lesson evidence.

API routes (all protected by existing PRISM Basic Auth): `GET /api/demo/erp/scenarios`, `POST /api/demo/erp/run` with `{"apply":false|true}`, `GET /api/demo/erp/lessons`, and `POST /api/demo/erp/lessons/approve` with `{"signature":"amount:legacy_format","confirmation":"APPROVE SYNTHETIC RULE"}`.

The demo SQLite path is configured server-side with `PRISM_ERP_DEMO_DB` and defaults to `/tmp/prism_erp_learning.sqlite3`. Avoid placing it under a production DB path. On ephemeral hosts it will **not** survive instance replacement; use a disposable local test setup for the approval/replay demonstration. Repeated execution against an unchanged target correctly produces duplicate-ID rejections. For a clean replay, start with a *new isolated test database path*, not a production database. No web-accessible reset endpoint is provided.

### Release gates before merge

```bash
python -m unittest discover -s demo -p 'test_*.py' -v
python -m unittest discover -s tests -p 'test_*.py' -v
cd frontend && npm ci && npm run build
```

Then verify via browser with PRISM Basic Auth that the source is synthetic, preview has zero target writes, unauthenticated requests are rejected, approval is explicit, replay reuses only approved rules, and the downloaded report matches the displayed counts. No production deploy or PR merge until gates pass.

**Safety boundaries:** Not tenant-isolated PostgreSQL, not an ERP/SAP connector, and not trained machine learning. Current approved learning is a rule-memory demonstration. The full PRISM roadmap still requires PostgreSQL+pgvector, authenticated tenant isolation, durable evidence history, AI retrieval, and real staging E2E validation.

## Live presentation rehearsal (after build and staging verification)

1. Open **ERP Learning Demo**, then choose **Restart synthetic demo**. The confirmation resets only this demo's isolated local tables.
2. Choose **Preview 20 records**. Show rejected currency formats and the repeated customer ID. Target count remains zero.
3. Explain that the unapproved rule appears in **Remembered lessons** with observations but is blocked from use.
4. Choose **Approve learned rule**, confirm, then **Execute local migration**.
5. Point to the reductions in rejected records, the three uses of `amount:legacy_format`, the remaining errors requiring steward review, and **Export reconciliation JSON**.
6. To repeat, reset the synthetic demo again. The reset also clears approvals, intentionally returning to the initial state.

The reconciliation metric verifies *run-level counts and unique inserted identifiers*, not complete financial balancing or an enterprise migration guarantee. SQLite state on Render's free ephemeral filesystem can disappear after restart. The demonstration requires staging browser verification, full Docker build, authentication checks, and written release approval before merging to `main` or replacing the live deployment.
