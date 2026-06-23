# TASKS

## Completed Tasks

- [x] **Wave 1: Foundation & Strict Contracts**
  - [x] Implement `BasePhasePayload(strict=True, extra="forbid")` and all Pydantic output schemas in `rag_contracts.py`.
  - [x] Implement generic `PhaseCLI[T_In, T_Out]` enforcing Tri-Plex I/O.
  - [x] Configure `pyproject.toml` with console script entrypoints `rag-p00` through `rag-p10`.
- [x] **Wave 2: Core Ingestion (Phases 01–04)**
  - [x] Implement `p01_load.py` with multi-file directory and single-file loading, HTML MIME detection, and stem collision disambiguation.
  - [x] Implement `p02_markdown.py` with HTML-to-clean-Markdown normalization via BeautifulSoup.
  - [x] Implement `p03_parse.py` with hierarchical AST Markdown header-path extraction.
  - [x] Implement `p04_chunk.py` with sliding-window semantic chunking preserving `parent_markdown`.
- [x] **Wave 3: Hybrid Engine & Vector Indexing (Phases 05 & 07)**
  - [x] Implement `hybrid_engine.py` singleton embedder loaders for Jina-v3 dense (1024-d, INT8 quantization) and SPLADE sparse embeddings.
  - [x] Implement embedded local disk persistence fallback at `./qdrant_storage` with deterministic UUIDv5 point IDs.
  - [x] Implement `p05_index.py` contextual prefix injection and batch upsert.
  - [x] Implement `p07_retrieve.py` Prefetch + Reciprocal Rank Fusion (RRF) query points execution.
- [x] **Wave 4: Reranking, CRAG & Evaluation (Phases 06, 08–10, 00)**
  - [x] Implement `p06_query.py` query clause decomposition and HyDE passage expansion.
  - [x] Implement `p08_rerank.py` Cross-Encoder scoring, parent section deduplication, and Lost-in-the-Middle context assembly.
  - [x] Implement `p09_generate.py` CRAG decision gate, grounded synthesis, and citation anchoring.
  - [x] Implement `p10_evaluate.py` RAG Triad metrics (nDCG@k, context precision, faithfulness, answer relevance).
  - [x] Implement `p00_crag_orchestrator.py` autonomous retry loop controller with query rewriting.
- [x] **Wave 5: Quality Assurance & Demonstration**
  - [x] Develop and verify 17 integration and unit tests in `tests/test_p01_to_p04.py`, `tests/test_p05_and_p07.py`, and `tests/test_p06_p08_p09_p10_p00.py`.
  - [x] Build live terminal verification test batteries (`verify_pipeline.ps1` and `verify_pipeline.sh`).
  - [x] Add README demo pipeline runner (`run_readme_pipeline.ps1` / `run_readme_pipeline.py`) and Rich output visualizer (`display_readme_results.py`).
  - [x] Comprehensive documentation in `README.md` and SDD in `docs/plans/2026-10-31-hybrid-rag-cli-plan.md`.
- [x] **Wave 6: Git Operations, Code Reviews & Release Merge**
  - [x] Address automated Codex review feedback for PR #1 (HTML MIME detection and stem collision disambiguation).
  - [x] Add regression test `test_p01_html_mime_and_stem_collision_disambiguation`.
  - [x] Commit and push demo scripts (`14fbac8`).
  - [x] Merge PR #1 (`feat/hybrid-rag-cli` -> `development`).
  - [x] Create and publish branch `main` at root commit `bc1a027`.
  - [x] Open PR #2 (`development` -> `main`) and merge into `main` (`7437c3a`).
  - [x] Set `main` as the default branch on GitHub repository `zautke/phase-rag-cli`.
- [x] **Wave 7: Formal Architecture Mapping & Knowledge Base Synchronization**
  - [x] Author comprehensive 10-phase + P00 architectural and mathematical map (`docs/architecture/phase_rag_pipeline_map.md`).
  - [x] Dispatch 2 specialized review subagents (`Math & Algorithmic Auditor` and `Systems & Pipeline Auditor`) to audit formulas, schemas, and execution mechanics.
  - [x] Integrate closed-form LITM permutations, guarded nDCG@k, SPLADE++ formulations, chunk count formulas, and tri-query retrieval flows.
  - [x] Synchronize definitive map to `master-kb` (`projects/phase-rag-cli/Phase RAG Pipeline Complete Architectural and Mathematical Map.md`) adhering to the `master-kb` singularity invariant.
  - [x] Re-index repository symbols and AST graph using `jcodemunch`.
  - [x] Update canonical continuity document set in `docs/continuity/`.

## Follow-up & Backlog Tasks

- [ ] **Continuous Integration (CI):**
  - [ ] Add `.github/workflows/ci.yml` running `uv run pytest` and lint checks on PRs targeting `development` and `main`.
- [ ] **Deployment & Standalone Services:**
  - [ ] Add `docker-compose.yml` for optional standalone Qdrant server + Web UI dashboard on port 6333.
- [ ] **Package Distribution:**
  - [ ] Verify `uv build` wheel generation and local test installation via `uv tool install`.
