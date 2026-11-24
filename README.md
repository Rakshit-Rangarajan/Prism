# PRISM — Predictive Risk Intelligence for Secure Migration

PRISM is a read-only AI decision-support layer for IBM ERP → SAP S/4HANA migrations alongside Qlik Talend Cloud.

## Deployment
Upload the extracted contents of `PRISM_Render_Ready_v0.3.zip` to this repository root (not a parent folder). The current source layout contains `Dockerfile`, `render.yaml`, `requirements.txt`, `app/server.py`, the React source under `frontend/src/`, and tests. There is no `app/connected.js` in this branch.

Render: New > Web Service, connect this repository, runtime **Docker**, branch `main`, region **Singapore**. Configure a secret `PRISM_DEMO_PASSWORD`. Demo username: `prism`.

**Security:** Synthetic data only. SQLite is on Render's ephemeral filesystem and can be reset on restarts. This is not a production-ready authenticated enterprise application. Use PostgreSQL+pgvector and RBAC/SSO before real data.

The standalone v0.3 source package was generated in ChatGPT, and is not yet committed here.

## Company AI Training (synthetic demo)

The `Company AI Training` screen provides an isolated learning workspace per company: synthetic or redacted examples, approval-gated retrieval, a locally trained deterministic model with hold-out evaluation, and a versioned model registry. True LoRA fine-tuning is an opt-in offline script with local/cached weights; see `docs/COMPANY_LLM_TRAINING.md`.

