# Changelog

## 0.2.0 — 2026-11-07 (merge into development)

**Re-index required.** fastembed 0.9 raises the SPLADE max token length 128 -> 512, and the fastembed cache moved into the Hugging Face hub cache (`HF_HUB_CACHE`). Existing Qdrant collections hold stale sparse vectors: rebuild them with `rag-p05`.

### Added
- Dense, sparse and rerank backends are named plugins (`hybrid_engine.py` name -> loader dicts). P05: `-b/--dense-backend` (`sentence_transformers` default | `fastembed`), `-m/--dense-model`, `-s/--sparse-model`; P08: `-b/--backend` (`fastembed` default | `sentence_transformers`). Defaults come from `.env.example` (`RAG_DENSE_BACKEND`, `RAG_DENSE_MODEL`, `RAG_SPARSE_MODEL`, `RAG_CRAG_THRESHOLD`, `QDRANT_PATH`).
- P05 output and P06 plan carry `dense_backend`, `dense_model`, `sparse_model`; P07 retrieves with exactly the models P05 indexed with (no override).
- P04 chunker registry: `--strategy sliding_window|recursive` (`chunkers.py`); `Phase04ChunkedOutput.chunk_strategy`.
- `model_fetch.ensure_model`: every model is fetched with aria2c (resumable, 8 connections, retries) into the HF cache layout, announced and with live progress on stderr; `.complete` marker; `refs/main` written only after a verified fetch. aria2c is required (fail-fast with a per-OS install hint); Linux resolves CPU torch.
- Battery consolidation: one `verify_pipeline.py` core plus thin `verify_pipeline.ps1` / `verify_pipeline.sh` wrappers with identical flags; every phase exit is checked, CRAG convergence is asserted, transcripts go to `verify_logs/`. Live tests carry the `live` pytest marker and are excluded by default.
- CI: `.github/workflows/ci.yml` runs `ruff check` and non-live `pytest` on pull requests and pushes.

### Changed
- `Phase06QueryPlanOutput.qdrant_collection` replaces the embedded `index_snapshot`.
- CRAG threshold has a single source (`RAG_CRAG_THRESHOLD`, 0.65); p00 forwards only explicitly set options.
- p00 `--max-retries N` means N retries after the first attempt (default 2); child stderr is inherited; rewrites use anchors actually present in the corpus and stop when anchors are exhausted; the demo-corpus rewrite fallbacks are gone.
- P08 emits `rank="N"` on each context; P10 computes nDCG in rank order.
- Every CLI shows `Usage()` as its `--help` epilog; a missing `--in-file` is a usage error and stdin is read once.
- `.gitignore` covers `verify_logs/`.

### Fixed
- D10: `rag-p04 --overlap` must be `>= 0` and `< --max-words` (exit 2, empty stdout otherwise); the final window no longer duplicates its predecessor.
- P08 indents every line of each XML context body.

### Removed
- `rag-p04b` GraphRAG side stage (no consumer, not in the spec).
- `RAG_FASTEMBED_CACHE_DIR` and the p00 `--max-retries` workaround text.
- Non-product docs evicted to the kb: Gemini export, rejected plugin proposal, pipeline map, continuity set, plans. The repo keeps README, AGENTS.md, CHANGELOG, `docs/MASTER_MANUAL.md` and the `docs/architecture/` UML mirror. `changeset.md` is replaced by this file.

Verification: <filled after Task 7>
