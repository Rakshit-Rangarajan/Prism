# PRISM — Universal Migration Studio and Company AI Architecture

## Product objective
Source-agnostic data conversion, cleaning, organization, risk identification, profiling, validation and explainable migration planning. A source platform, source *data model*, target platform and target *data model* are independently selected. This is an extensible capability model, **not** a claim that every possible pair already has an executable connector.

## Migration pipeline
1. Identify tenancy, authorization, retention, data region and approved connectors.
2. Discover source schemas, encodings, sizes, relationships, quality statistics and governance policies.
3. Profile and classify structured, semi-structured, unstructured, binary and streaming data.
4. Define canonical intermediate representation where appropriate, preserving raw source provenance.
5. Generate candidate field, object and relationship mappings and mark uncertain mappings.
6. Validate transformation rules, data types, nullability, referential integrity, duplicates, time zones, units, formats, PII and information loss.
7. Execute a *non-destructive* staging rehearsal using deterministic transforms in a constrained worker.
8. Compare source/target counts, hashes, distributions, orphan counts, schema compatibility, business rules and acceptance criteria.
9. Analyze failure clusters, downstream dependencies and milestone risks.
10. Require authorized sign-off for deployment, actual cutover and rollback.

## Capabilities model
Each adapter must describe: supported direction (read/write), type family, schema discovery, snapshot vs CDC, change ordering, replay, authentication, transaction semantics, binary limits, fidelity, business constraints, governance restrictions and test coverage.

The initial Migration Studio taxonomy offers 45 illustrative format/model categories in six families. Format parsing and migration adapters are **not yet implemented** universally. 'Native' in catalogue denotes initial suitability for generic schema profiling, not proven source/target connectivity.

## Local company-specific intelligence
- Keep one logical company namespace and authorization boundary for every approved source, document, vector and decision.
- Start with **RAG** over tenant-approved mappings, catalogues, target contracts, run books and resolved cases.
- Local embeddings are stored within the same protected tenant boundary. For initial development, PostgreSQL + pgvector is preferred, optionally keeping SQLite for offline mode.
- A locally deployed Ollama/llama.cpp/vLLM runtime may provide explanations, semantic matching and mapping suggestions, never irreversible migrations or autonomous approvals.
- Use a company-specific evaluation set (mapping precision/recall, exception triage, unsupported citations, privacy tests, drift monitoring) before use.
- Fine-tuning a separate small model or adapter per company is optional, subject to sufficient approved training examples, hardware, privacy and evaluations. Neither training nor inference is deployed by this UI-only increment.
- Company-specific source documents and data must never enter a shared external inference endpoint without explicit approval.

## Risks and guardrails
No universal lossless conversion exists. Converting between a video stream and a relational table, or an ERP business object and a PDF, requires specifying which information is extracted or rendered. Never silently coerce formats, drop columns, assume target ERP semantics, or mark an unsupported pair as compatible. Require explicit human-approved transformation contracts.

## Release stages
1. Interactive source/target/type selection, risk notes, JSON blueprint export (**this PR**).
2. Persist validated blueprints and approved connection profiles in the API.
3. Connector capability registry and conversion feasibility matrix.
4. Non-destructive ingestion, profiling, mapping and cleaning engine.
5. Tenant-scoped PostgreSQL + pgvector + local embeddings.
6. Enterprise isolated local LLM, RAG evaluation and monitoring.
7. Adapter workers, dry-run execution and reproducible evidence packs.
8. Controlled cutover orchestration only for validated connector pairs.
