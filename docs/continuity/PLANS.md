# PLANS

## Active — SOTA 10-Phase Hybrid RAG CLI Suite & CRAG Loop Controller

### Goals
Deliver a production-grade, 10-phase UNIX-piped Hybrid RAG CLI toolsuite with an autonomous Corrective RAG (CRAG) loop controller executed via `uv`. The architecture enforces a strict Tri-Plex I/O contract (`stdout` JSON payload, `stderr` Rich telemetry, `disk` atomic artifact), named dense/sparse vectors in Qdrant, and cross-encoder validation with RAG Triad evaluation.

### Current Facts & Milestones
- **Architecture Spec:** Defined in `AGENTS.md` and detailed SDD in `docs/plans/2026-10-31-hybrid-rag-cli-plan.md`.
- **Phase 01–04 (Core Ingestion):**
  - `p01_load.py`: Disambiguates document stems (`guide_md`, `guide_html`), assigns proper MIME types.
  - `p02_markdown.py`: Normalizes HTML markup to clean Markdown using BeautifulSoup.
  - `p03_parse.py`: Extracts Markdown AST header paths.
  - `p04_chunk.py`: Sliding-window semantic chunker preserving `parent_markdown`.
- **Phases 05 & 07 (Hybrid Engine & Vector DB):**
  - `hybrid_engine.py`: FastEmbed singleton loaders for Jina-v3 dense (1024-d, INT8 scalar quantization) and SPLADE sparse embeddings; dual cross-encoder rerankers; Qdrant embedded client fallback at `./qdrant_storage`.
  - `p05_index.py`: Live batch embedding upsert with deterministic UUIDv5 point IDs.
  - `p07_retrieve.py`: Prefetch + Reciprocal Rank Fusion (RRF) query points execution on Qdrant.
- **Phases 06, 08–10 (Rerank, CRAG & Evaluation):**
  - `p06_query.py`: Multi-clause query decomposition and HyDE passage expansion.
  - `p08_rerank.py`: Cross-Encoder reranking, section deduplication, Lost-in-the-Middle context assembly.
  - `p09_generate.py`: CRAG confidence decision gate, synthesized grounded answer with citations.
  - `p10_evaluate.py`: RAG Triad metrics (nDCG@k, context precision, faithfulness, answer relevance).
- **P00 CRAG Orchestrator:**
  - `p00_crag_orchestrator.py`: Multi-attempt query rewriting loop controller with disk checkpointing.
- **Verification & Releases:**
  - 17 unit and integration tests passing in `tests/`.
  - Automated smoke test suites in `verify_pipeline.ps1` and `verify_pipeline.sh`.
  - PR #1 (`feat/hybrid-rag-cli` -> `development`) merged.
  - PR #2 (`development` -> `main`) merged.
  - `main` branch initialized, merged, and configured as the default GitHub repository branch.

### Non-Goals
- External server daemon requirement for baseline CLI operations (embedded Qdrant engine operates out-of-the-box).
- Ad-hoc unstructured stdout logging (strictly forbidden; stdout is reserved for JSON output).
- Breaking Pydantic schema contracts (`extra="forbid"` enforced across all phases).

### Future Potential Initiatives
- **CI/CD Pipeline:** Add GitHub Actions workflow for multi-platform test batteries (Linux/Windows).
- **Packaging:** Build and publish sdist/wheel distributions on PyPI.
- **Interactive Server/UI Mode:** Optional FastAPI / Gradio interface wrapping CLI phases.
