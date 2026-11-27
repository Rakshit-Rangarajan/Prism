# PRISM — Predictive Risk Intelligence for Secure Migration

PRISM profiles source databases, recommends approval-gated ERP transformations, learns through company-specific approved migration memory, and generates a separate processed database with Qlik-compatible exports. The local small language model recommends finite rules; Python validates and executes them. Source databases remain unchanged.

## Deployment
The existing Render Docker service automatically deploys `main`. `Dockerfile` builds the React/TypeScript/Vite frontend and runs the backend/demo test suites. `render.yaml` retains the service configuration. No GPU model or training dependencies are included in the hosted image.

Render: New > Web Service, connect this repository, runtime **Docker**, branch `main`, region **Singapore**. Configure a secret `PRISM_DEMO_PASSWORD`. Demo username: `prism`.

**Security:** Synthetic data only. SQLite is on Render's ephemeral filesystem and can be reset on restarts. This is not a production-ready authenticated enterprise application. Use PostgreSQL+pgvector and RBAC/SSO before real data.

## Local GPU demo

See [local setup and presentation guide](docs/local-demo.md) and [model comparison and measured results](docs/model-selection.md). On the prepared Windows machine, run `scripts/start-local.ps1`; PRISM opens at `http://127.0.0.1:8091`. Use **Local AI & Learning** for the complete MySQL/SQLite → structured recommendation → human correction/approval → company memory → processed database workflow.

Twenty deliberately messy ERP datasets cover vendors, materials and invoices. The verified replay preserves row counts and source hashes while improving quality metrics. Duplicate candidates, invalid dates, orphan references and unknown financial mappings remain for steward review. Immediate learning uses approved retrieval. Offline QLoRA is a separate command that produces per-company adapter candidates and held-out evaluation reports.

Qlik-compatible CSV/SQLite exports are retained. Live Qlik and SAP integrations remain deferred pending credentials. Basic Auth, synthetic ERP vocabularies and single-company-per-server isolation support demonstrations; they do not constitute enterprise SSO or SAP acceptance.
