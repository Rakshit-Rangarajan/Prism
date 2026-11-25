# Migration Memory retrieval governance guard

`app/memory_retrieval_policy.py` implements a pure, fail-closed policy for selecting **current approved** Migration Memory revisions. It checks exact tenant/domain/target-object scope, missing predecessors, version continuity, conflicting approved successors and approval supersession. It does not modify records.

**Important:** The live SQLite demo has no real tenant identity. This guard is deliberately **not wired** into existing endpoints. Before using it, the PostgreSQL retrieval adapter must (1) resolve tenant identity from verified authentication, never request parameters; (2) query **all revisions** in the exact tenant/domain/object scope using parameterized SQL and enforce row-level security; (3) apply this policy to that full set before ranking vectors; (4) revalidate returned IDs and approval states against the source of truth in the same consistent snapshot; and (5) fail closed if any check fails.

A Python policy check is defense in depth, **not** a substitute for database tenant authorization or row-level security. The guard cannot detect revisions omitted by a compromised or incorrectly scoped SQL query. No real PostgreSQL or embedding model has been validated.

Validation: `python -m unittest discover -s tests -p 'test_memory_retrieval_policy.py' -v` (12 synthetic unit tests). The existing Dockerfile executes `test_*.py` during builds.

No paid services, production migrations, company records, or Qlik/SAP credentials are used.
