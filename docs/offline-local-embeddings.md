# Offline local embeddings (synthetic-only)

This module is an opt-in building block, **not** a live semantic-search endpoint.
It does not modify the existing SQLite catalog, React UI, or deployed API.

## Prerequisites
Install `sentence-transformers` separately in a local development environment
and provision a compatible model directory ahead of time (under a license you have reviewed).
Set `PRISM_LOCAL_EMBEDDING_MODEL=/absolute/path/to/model`.
The adapter uses `local_files_only=True` and `trust_remote_code=False`;
it never downloads a model at runtime.

Use `from app.local_embeddings import embed_local` to embed a synthetic
query or approved synthetic record. Supply `expected_dimensions` when
writing into a fixed-dimension pgvector column. Invalid vectors, zero vectors,
missing models and mismatched dimensions fail closed. No fallback to a paid API.

## Validation
`python -m unittest discover -s tests -p 'test_local_embeddings.py' -v`

## Remaining integration
Implement a tenant-scoped PostgreSQL persistence pipeline and embed **only
approved/current** memory versions, with version retirement, provenance and
tenant isolation. Confirm live pgvector behavior against a disposable local
PostgreSQL instance before connecting to the API. This module by itself
does not prove semantic search or tenant isolation.
