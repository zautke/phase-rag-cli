# Implementation Plan: SOTA Hybrid RAG CLI Pipeline

**Spec Authority:** `Gemini-RAG Document Ingestion Pipeline Explained-20261031-1314.md`
**Date:** 2026-10-31

## Global Constraints
1. **Tri-Plex I/O Law:**
   - `stdout`: Strictly raw `model_dump_json(indent=2)` payload (UTF-8). Zero logs, warnings, or ANSI codes on `stdout`.
   - `stderr`: Rich telemetry panels + diagnostics (`Console(stderr=True)`).
   - `disk`: Deterministic persistence to `--out-file` (`artifacts/0X_*.json`).
2. **Strict Contracts:** Every CLI `Phase[N]` must call `PhaseCLI.load_upstream()` to validate `Phase[N-1]` output via Pydantic `ConfigDict(strict=True, extra="forbid")`.
3. **CLI Switch Law:** Every CLI script begins with `#!/usr/bin/env python3`, exposes a `Usage()` helper, and provides both short (`-x`) and long (`--full-name`) flags for all options (no positional args).
4. **Windows & Cross-Platform UTF-8 Safety:** Enforce UTF-8 on `sys.stdin`, `sys.stdout`, and `sys.stderr` (`reconfigure(encoding="utf-8")`) so PowerShell and UNIX pipes never corrupt multi-byte characters.
5. **jCodemunch Indexing:** After creating/editing files, index with `jcodemunch-mcp index` and prefer jCodemunch for all code inspection.
6. **PowerShell Native Execution on `adagio`:** All terminal execution on `adagio` uses native PowerShell (`pwsh`), never Bash. Provide both `verify_pipeline.ps1` (for native Windows execution) and `verify_pipeline.sh` (for POSIX/spec parity).

## Tasks

### Task 1: Foundation Contracts, Package Config & Ingestion Phases 01–04 (`SUBAGENT_CORE_INGEST`)
- **Files:** `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `rag_contracts.py`, `p01_load.py`, `p02_markdown.py`, `p03_parse.py`, `p04_chunk.py`, `tests/test_p01_to_p04.py`
- **Requirements:**
  - `pyproject.toml` with `sota-hybrid-rag-cli`, `hatchling`, `[project.scripts]` (`rag-p00`..`rag-p10`), dependencies (`pydantic>=2.9.0`, `typer>=0.12.5`, `rich>=13.9.0`, `qdrant-client>=1.17.0`, `fastembed>=0.6.0`, `sentence-transformers>=3.3.0`, `einops>=0.8.0`), and `dev` extras (`pytest>=8.3.0`, `ruff>=0.7.0`, `mypy>=1.13.0`).
  - `rag_contracts.py` with `BasePhasePayload(strict=True, extra="forbid")`, all 12 schemas (`RawDocument`, `Phase01LoadedOutput`, `MarkdownDocument`, `Phase02MarkdownOutput`, `ParsedSection`, `Phase03ParsedOutput`, `DocumentChunk`, `Phase04ChunkedOutput`, `EnrichedIndexedChunk`, `Phase05IndexedOutput`, `Phase06QueryPlanOutput`, `RetrievedCandidate`, `Phase07RetrievedOutput`, `RerankedContextItem`, `Phase08RerankedOutput`, `Phase09GenerationOutput`, `Phase10EvalOutput`, `CRAGAttemptRecord`, `PhaseCRAGLoopOutput`), and `PhaseCLI[T_In, T_Out]` with UTF-8 stream reconfiguration.
  - `p01_load.py`, `p02_markdown.py`, `p03_parse.py`, `p04_chunk.py` implementing the exact spec logic + short/long flags + `Usage()`.
  - `tests/test_p01_to_p04.py` testing Phases 01–04 in-process and via CLI subprocess piping.

### Task 2: Hybrid Vector & Cross-Encoder Engine + Phases 05 & 07 (`SUBAGENT_HYBRID_VEC`)
- **Files:** `hybrid_engine.py`, `p05_index.py`, `p07_retrieve.py`, `tests/test_p05_and_p07.py`
- **Requirements:**
  - `hybrid_engine.py` supporting live neural dense (`jinaai/jina-embeddings-v3`, 1024-d, checking FastEmbed or cached HuggingFace/SentenceTransformers `C:\Users\me\.cache\huggingface\hub\models--jinaai--jina-embeddings-v3` or FastEmbed ONNX), sparse (`prithivida/Splade_PP_en_v1` via FastEmbed), and cross-encoder reranking (`BAAI/bge-reranker-v2-m3` via `sentence-transformers` and `jinaai/jina-reranker-v2-base-multilingual` via `fastembed`).
  - Qdrant collection setup (`jina-dense` with Cosine + INT8 `ScalarQuantization`, `splade-sparse` with `SparseIndexParams(on_disk=False)`), deterministic UUIDv5 point IDs, and `client.close()` on exit.
  - `p05_index.py`: Contextual Retrieval prefix `[Doc: {doc_id} | Section: {headers}] `, batch dense + sparse encoding, Qdrant upsert, emit `Phase05IndexedOutput`.
  - `p07_retrieve.py`: Query + HyDE dense encoding, raw query sparse encoding, per-branch diagnostic scores, Qdrant `query_points()` with `models.Prefetch` + `models.RrfQuery(rrf=models.Rrf(k=rrf_k, weights=[dense_weight, sparse_weight]))`, emit `Phase07RetrievedOutput`.
  - `tests/test_p05_and_p07.py` verifying live Qdrant hybrid indexing and RRF retrieval.

### Task 3: Query Orchestration, Reranking, CRAG Generation, Evaluation & Loop Controller (`SUBAGENT_RERANK_CRAG`)
- **Files:** `p06_query.py`, `p08_rerank.py`, `p09_generate.py`, `p10_evaluate.py`, `p00_crag_orchestrator.py`, `AGENTS.md`, `tests/test_p06_p08_p09_p10_p00.py`
- **Requirements:**
  - `p06_query.py`: Multi-query decomposition + HyDE passage generation -> `Phase06QueryPlanOutput`.
  - `p08_rerank.py`: Live Cross-Encoder batch scoring (`rerank_passages_batch`), parent-section deduplication (`--dedupe-parents`), Lost-in-the-Middle XML context ordering (`--reorder-litm`), emit `Phase08RerankedOutput`.
  - `p09_generate.py`: CRAG confidence verification against `--crag-threshold` (`GROUNDED` vs `REWRITE_REQUIRED`), grounded synthesis with citations -> `Phase09GenerationOutput`.
  - `p10_evaluate.py`: RAG Triad metrics (`ndcg_at_k`, `context_precision`, `faithfulness_score`, `answer_relevance`, `hallucination_detected`) -> `Phase10EvalOutput`.
  - `p00_crag_orchestrator.py`: Autonomous CRAG loopback controller (`P06 -> P07 -> P08 -> P09` cycle + query rewriting + per-attempt artifact lineage `artifacts/crag_attempt_N/` + `P10` evaluation + Rich trajectory table) -> `PhaseCRAGLoopOutput`.
  - `AGENTS.md`: High-signal token-efficient multi-agent orchestrator & specialty subagent blueprint from the spec.
  - `tests/test_p06_p08_p09_p10_p00.py` verifying all phases and CRAG loopback convergence.

### Task 4: Post-Implementation Review & Live-Exercise Terminal Test Battery (`SUBAGENT_QA_AUDITOR`)
- **Files:** `verify_pipeline.ps1`, `verify_pipeline.sh`
- **Requirements:**
  - Static AST audit (0 bare `print()` calls on `stdout`, 10/10 Pydantic phase contract continuity `Phase[N].output_model is Phase[N+1].input_model`, strict `ConfigDict(strict=True, extra="forbid")`, `client.close()` verification).
  - Stage 1: Isolated live in-terminal execution of `rag-p01` through `rag-p10` verifying `stderr` Rich panel output, persisted `artifacts/0X_*.json` file, and `stdout` Pydantic round-trip equivalence (`disk_obj.model_dump() == stdout_obj.model_dump()`).
  - Stage 2: Full 10-phase continuous pipe (`rag-p01 | ... | rag-p10`) end-to-end test.
  - Stage 3: Autonomous CRAG Loopback & Query-Rewrite convergence test (`rag-p00`) verifying multi-attempt query expansion and `PhaseCRAGLoopOutput`.
