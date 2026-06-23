# REMEMBER

## Invariants & Architecture Constraints

### 1. Tri-Plex I/O Law (Critical Pipeline Invariant)
- **`stdout`**: Strictly raw `model_dump_json(indent=2)` payload. Zero logs, warnings, debug statements, or prints may pollute stdout. This preserves clean UNIX piping (`|`) between phases.
- **`stderr`**: Rich telemetry panels, tables, metrics, and diagnostics. Always construct Rich consoles with `Console(stderr=True)`.
- **`disk`**: Deterministic persistence to `--out-file` (e.g. `artifacts/0X_*.json`).

### 2. Strict Contract Enforcement
- All phase outputs inherit from `BasePhasePayload` in `rag_contracts.py`.
- Enforces `model_config = ConfigDict(strict=True, extra="forbid")`. Any extra or mis-typed field will trigger an immediate schema validation failure.
- Every phase CLI must call `cli_engine.load_upstream()` to validate input from `--in-file` or `stdin`.

### 3. Qdrant Embedded Topology & Point Identity
- **Default Mode**: Embedded on-disk storage (`QdrantClient(path=qdrant_path)`). Does not require an external Docker container or running daemon.
- **Remote Mode**: Pass `--qdrant-url` or set `QDRANT_URL`. The engine tests connection with a 2-second timeout and gracefully falls back to local disk if unavailable.
- **Deterministic Point IDs**: `deterministic_point_uuid(chunk_id)` derives a UUIDv5 from `uuid.NAMESPACE_DNS` and `chunk_id`. This guarantees idempotency: re-running indexing updates existing points rather than generating duplicates.

### 4. Document Stem Disambiguation & HTML Parsing
- When indexing directories with multi-format files of identical stems (e.g., `guide.md` and `guide.html`), `doc_id` must include suffix disambiguation (`guide_md`, `guide_html`).
- Files with `.html` or `.htm` must explicitly receive `text/html` in `p01_load.py` so that `p02_markdown.py` triggers BeautifulSoup Markdown normalization rather than treating them as plain text.

### 5. Context Assembly: Lost-in-the-Middle Strategy
- `p08_rerank.py` reorders top-k chunks in `<retrieved_context>` blocks:
  - Rank 1 (highest score) &rarr; beginning of context block ($\pi(1) = 1$).
  - Rank 2 (second highest) &rarr; end of context block ($\pi(2) = N$).
  - Ranks 3..N &rarr; alternating distribution via closed-form piecewise formula:
    $$\pi(r) = \begin{cases} \frac{r + 1}{2}, & \text{if } r \text{ is odd} \\ N - \frac{r}{2} + 1, & \text{if } r \text{ is even} \end{cases}$$
  - Payloads in `top_contexts` remain strictly sorted by cross-encoder score descending for programmatic consumers.

### 6. Git Branching Hierarchy
- `main`: Production release branch (default branch on GitHub).
- `development`: Primary integration branch.
- Feature branches (`feat/*`): Target `development` via PR. Once validated in `development`, a release PR merges `development` into `main`.

### 7. Knowledge Base Singularity (`basic-memory`)
- **`master-kb` Invariant:** `basic-memory` MCP operations MUST strictly and exclusively target `master-kb` (`UUID: 6232ec65-5648-469e-8ea1-7ab6ab622ab9`). Never create or route to secondary KB projects.

### 8. Phase Threshold & Evaluation Realities
- **CRAG Threshold Defaults:** `p09_generate.py` CLI default is `--crag-threshold 0.60`. `p00_crag_orchestrator.py` overrides this when calling child processes to `--crag-threshold 0.65`.
- **P10 Context Precision:** Implemented as `round(upstream.grounded_confidence, 4)`, reflecting peak retrieval grounding confidence rather than thresholded count fraction.
- **P10 Faithfulness Smoothing:** Computed as `round(min(1.0, overlap_ratio + 0.25), 4)`. Hallucination triggers at `faithfulness < 0.75` (corresponding to raw `overlap_ratio < 0.50`).
