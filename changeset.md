# Changeset

## 0.2.0 — 2026-11-02 (merge into development)

- feat(p04): chunker registry with `--strategy sliding_window|recursive` (`chunkers.py`); `Phase04ChunkedOutput.chunk_strategy` (defaulted).
- refactor(contracts): `Phase06QueryPlanOutput.qdrant_collection` replaces the embedded `index_snapshot` (P05 payload no longer travels past P05).
- test(verify): batteries exercise `rag-p04 -s recursive` and the negative unknown-strategy case; Stage 0 audits the new modules and the chunker registry.
- docs: README "Pluggability" section; `docs/MASTER_MANUAL.md`.
- feat(engine): `model_fetch.ensure_model` downloads every model with aria2c (resumable, 8 connections, retries) into the HF cache layout and reports each file and live progress on stderr; libraries no longer download silently. Requires `aria2c` on PATH.
- fix(verify): both batteries check every phase exit, `.sh` gains `Usage()`/`-s`/`-q`/`-h`, Stage 3 asserts CRAG convergence, transcripts persist to `artifacts/verify_<ps1|sh>_<ts>.log`.
- Tests 17 → 30; `verify_pipeline.ps1` Stages 0-3 PASS; live-QA ALL PASS (see kb run-ledger).

