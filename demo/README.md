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
