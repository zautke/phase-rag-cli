# ROLE: SOTA_RAG_ORCHESTRATOR (Session Lead)
OBJECTIVE: Coordinate 4 Specialty Subagents to implement, type-check, and live-verify a 10-phase UNIX-piped Hybrid RAG CLI suite + P00 CRAG Loop Controller under `uv`.

## GLOBAL INVARIANTS (ENFORCE ACROSS ALL SUBAGENTS)
1. TRI-PLEX I/O LAW:
   - `stdout`: STRICTLY raw `model_dump_json(indent=2)` payload. ZERO logs/warnings on stdout.
   - `stderr`: Rich telemetry panels + diagnostics (`Console(stderr=True)`).
   - `disk`: Deterministic persistence to `--out-file` (`artifacts/0X_*.json`).
2. STRICT CONTRACTS: Every CLI `Phase[N]` MUST call `PhaseCLI.load_upstream()` to validate `Phase[N-1]` output via Pydantic `ConfigDict(strict=True, extra="forbid")`.
3. FILE OWNERSHIP LOCK:
   - `SUBAGENT_CORE_INGEST`: `pyproject.toml`, `rag_contracts.py`, `p01_load.py`..`p04_chunk.py`
   - `SUBAGENT_HYBRID_VEC`: `hybrid_engine.py`, `p05_index.py`, `p07_retrieve.py`
   - `SUBAGENT_RERANK_CRAG`: `p06_query.py`, `p08_rerank.py`, `p09_generate.py`, `p10_evaluate.py`, `p00_crag_orchestrator.py`
   - `SUBAGENT_QA_AUDITOR`: `verify_pipeline.py` (core) + thin `verify_pipeline.ps1` / `verify_pipeline.sh` wrappers (Post-Implementation Review + Live Terminal Test Battery)

## EXECUTION DAG & GATES
- WAVE 1 (Blocking Foundation): Dispatch `SUBAGENT_CORE_INGEST` to emit `pyproject.toml` + `rag_contracts.py`. Gate: `uv run python -c "import rag_contracts"`.
- WAVE 2 (Parallel Implementation): Dispatch `SUBAGENT_CORE_INGEST` (P01-P04), `SUBAGENT_HYBRID_VEC` (Engine + P05, P07), and `SUBAGENT_RERANK_CRAG` (P06, P08-P10, P00) concurrently.
- WAVE 3 (Review & Live Terminal Battery): Dispatch `SUBAGENT_QA_AUDITOR` to run static audit, per-phase CLI smoke tests, pipe-integrity verification, and CRAG loopback convergence test.

---

## Specialty Subagent Specifications (Token-Compressed Prompts)

### Subagent 1: `SUBAGENT_CORE_INGEST` (Contracts & Phases 01–04)
- **OWNERSHIP:** `pyproject.toml`, `rag_contracts.py`, `p01_load.py`, `p02_markdown.py`, `p03_parse.py`, `p04_chunk.py`
- **TASK:**
  1. Implement `BasePhasePayload(strict=True, extra="forbid")` and all 11 Pydantic output schemas (`Phase01LoadedOutput`..`Phase10EvalOutput`, `PhaseCRAGLoopOutput`) plus generic `PhaseCLI[T_In, T_Out]` in `rag_contracts.py`.
  2. Implement `p01_load.py` (raw files/built-in HTML+MD corpus -> `Phase01LoadedOutput`).
  3. Implement `p02_markdown.py` (`Phase01LoadedOutput` -> HTML-to-MD normalization -> `Phase02MarkdownOutput`).
  4. Implement `p03_parse.py` (`Phase02MarkdownOutput` -> AST header-path splitting -> `Phase03ParsedOutput`).
  5. Implement `p04_chunk.py` (`Phase03ParsedOutput` -> sliding-window word chunker preserving `parent_markdown` -> `Phase04ChunkedOutput`).
- **EXIT CRITERIA:** `uv run rag-p01 | uv run rag-p02 | uv run rag-p03 | uv run rag-p04` exits 0 and emits valid JSON on stdout.

### Subagent 2: `SUBAGENT_HYBRID_VEC` (Qdrant + plugin backends, Phases 05 & 07)
- **OWNERSHIP:** `hybrid_engine.py`, `model_fetch.py`, `p05_index.py`, `p07_retrieve.py`
- **UPSTREAM DEP:** `rag_contracts.py` (Read-Only)
- **TASK:**
  1. In `hybrid_engine.py`, dense/sparse/rerank are named backend plugins (default dense: sentence-transformers jina-v3) held in `DENSE_BACKENDS`, `SPARSE_BACKENDS`, `RERANK_BACKENDS` (name -> loader dicts, lazy singletons). Built in: dense `sentence_transformers` (`jinaai/jina-embeddings-v3`, default) and `fastembed`; sparse `fastembed` (`prithivida/Splade_PP_en_v1`); rerank `sentence_transformers` (`BAAI/bge-reranker-v2-m3`, default) and `fastembed` (`jinaai/jina-reranker-v2-base-multilingual`). Selected by `rag-p05 -b/-m/-s` and `rag-p08 -b/-m`; defaults live in `.env.example` (`RAG_DENSE_BACKEND`, `RAG_DENSE_MODEL`, `RAG_SPARSE_MODEL`). Every model download goes through `model_fetch.ensure_model` (aria2c, announced, progress on stderr).
  2. Configure Qdrant collection with named vectors `jina-dense` (Cosine + INT8 ScalarQuantization) and `splade-sparse` (`SparseIndexParams(on_disk=False)`), plus UUIDv5 deterministic point IDs.
  3. Implement `p05_index.py`: prepend contextual header prefix `[Doc: X | Section: Y]`, batch-encode dense+sparse, upsert to Qdrant, emit `Phase05IndexedOutput` (records `dense_backend`, `dense_model`, `sparse_model`; P06 copies them and P07 encodes the query with exactly those).
  4. Implement `p07_retrieve.py`: encode query+HyDE (dense) and raw query (sparse), capture per-branch diagnostic scores, execute Qdrant `query_points()` with `Prefetch` + `RrfQuery(rrf=Rrf(k=rrf_k, weights=[dense_weight, sparse_weight]))`, emit `Phase07RetrievedOutput`.
- **EXIT CRITERIA:** `uv run rag-p05 -i artifacts/04_chunked.json` and `uv run rag-p07 -i artifacts/06_query_plan.json` pass schema validation.

### Subagent 3: `SUBAGENT_RERANK_CRAG` (Query, Cross-Encoder, CRAG & Loop Controller: Phases 06, 08–10, 00)
- **OWNERSHIP:** `p06_query.py`, `p08_rerank.py`, `p09_generate.py`, `p10_evaluate.py`, `p00_crag_orchestrator.py`
- **UPSTREAM DEP:** `rag_contracts.py`, `hybrid_engine.py` (Read-Only)
- **TASK:**
  1. `p06_query.py`: Decompose multi-clause query + synthesize HyDE passage -> `Phase06QueryPlanOutput`.
  2. `p08_rerank.py`: Batch-score candidates via `rerank_passages_batch()`, deduplicate identical `parent_markdown` sections, apply Lost-in-the-Middle ordering to `<retrieved_context>` XML block, keep `top_contexts` sorted descending -> `Phase08RerankedOutput`.
  3. `p09_generate.py`: Compare `max(cross_encoder_score)` against `--crag-threshold`; emit `GROUNDED` or `REWRITE_REQUIRED` with inline citations -> `Phase09GenerationOutput`.
  4. `p10_evaluate.py`: Compute RAG Triad metrics (`ndcg_at_k`, `context_precision`, `faithfulness_score`, `answer_relevance`) -> `Phase10EvalOutput`.
  5. `p00_crag_orchestrator.py`: Subprocess loop controller executing `P06 -> P07 -> P08 -> P09`; when `crag_verdict == "REWRITE_REQUIRED"`, extract corpus anchor terms from `p08_out`, rewrite query, persist `artifacts/crag_attempt_N/`, and retry up to `--max-retries` before running `P10` -> `PhaseCRAGLoopOutput`.
- **EXIT CRITERIA:** `uv run rag-p00` converges from `REWRITE_REQUIRED` to `GROUNDED` and writes `artifacts/00_crag_loop_summary.json`.

### Subagent 4: `SUBAGENT_QA_AUDITOR` (Post-Implementation Review & Terminal Test Battery)
- **OWNERSHIP:** `verify_pipeline.py`, `verify_pipeline.sh`, `verify_pipeline.ps1`
- **TASK:**
  1. Run static post-implementation review: verify zero `print()` calls pollute `stdout`, verify every `Phase0X` schema sets `ConfigDict(strict=True, extra="forbid")`, and run `ruff check` + AST syntax verification.
  2. Execute isolated per-phase live terminal tests (`rag-p01` through `rag-p10`) verifying:
     (a) Non-empty `stderr` Rich panel output,
     (b) Persisted JSON artifact on disk (`artifacts/0X_*.json`),
     (c) Validated Pydantic round-trip via `model_validate_json()` on `stdout`.
  3. Execute full 10-phase linear UNIX pipe battery (`rag-p01 | ... | rag-p10`).
  4. Execute cyclic CRAG loopback battery (`rag-p00 --crag-threshold 0.92`) verifying multi-attempt query rewriting.
