# Changeset

## 0.2.0 — 2026-11-02 (merge into development)

- feat(p04): chunker registry with `--strategy sliding_window|recursive` (`chunkers.py`); `Phase04ChunkedOutput.chunk_strategy` (defaulted).
- refactor(contracts): `Phase06QueryPlanOutput.qdrant_collection` replaces the embedded `index_snapshot` (P05 payload no longer travels past P05).
- feat(p04b): `rag-p04b` GraphRAG entity co-occurrence side-artifact pass-through stage (`GraphArtifact`, `GraphNode`, `GraphEdge`).
- test(verify): batteries exercise `rag-p04 -s recursive`, `rag-p04b`, and the negative unknown-strategy case; Stage 0 audits the new modules and the extended chain.
- docs: README "Pluggability" section; `docs/MASTER_MANUAL.md`.
- Tests 17 → 30; `verify_pipeline.ps1` Stages 0-3 PASS; live-QA ALL PASS (see kb run-ledger).

