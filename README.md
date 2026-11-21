# PRISM — Predictive Risk Intelligence for Secure Migration

PRISM is a read-only AI decision-support layer for IBM ERP → SAP S/4HANA migrations alongside Qlik Talend Cloud.

## Deployment
Upload the extracted contents of `PRISM_Render_Ready_v0.3.zip` to this repository root (not a parent folder). The package contains `Dockerfile`, `render.yaml`, `requirements.txt`, `app/server.py`, `app/index.html`, `app/connected.js`, and tests.

Render: New > Web Service, connect this repository, runtime **Docker**, branch `main`, region **Singapore**. Configure a secret `PRISM_DEMO_PASSWORD`. Demo username: `prism`.

**Security:** Synthetic data only. SQLite is on Render's ephemeral filesystem and can be reset on restarts. This is not a production-ready authenticated enterprise application. Use PostgreSQL+pgvector and RBAC/SSO before real data.

The standalone v0.3 source package was generated in ChatGPT, and is not yet committed here.
