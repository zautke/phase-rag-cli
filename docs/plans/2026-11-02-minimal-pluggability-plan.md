# Minimal Pluggability (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chunking swappable (built-in + third-party), decouple P06 from the P05 payload, add a startup contract-topology check, and add a drop-in GraphRAG side-artifact stage, without touching the verified Tri-Plex pipe, `PhaseCLI`, or the strict contracts.

**Architecture:** The UNIX pipe stays the plugin bus: any executable reading Phase N JSON and writing Phase N+1 JSON is a plugin. Inside a phase, a strategy is a plain function in a name→callable registry selected by a CLI flag, with third-party discovery via `importlib.metadata.entry_points`. New stages are pass-through CLIs (Phase N in → Phase N out) that write a side artifact. Everything is synchronous and corpus-level batched.

**Tech Stack:** Python ≥3.11, `uv`, Pydantic v2 (strict, `extra="forbid"`), Typer, Rich (stderr only), stdlib `importlib.metadata` + `re` + `urllib`. No new runtime dependencies.

**Spec:** `docs/rag_plugin_evolution_architecture.md` (original proposal) as amended by `docs/plans/2026-11-02-plugin-evolution-audit.md` (binding: the audit's "Adopted minimal architecture" section is the spec; the proposal's `PipelinePacket`/async/registry/JSONL constructs are rejected).

## Global Constraints

- Tri-Plex I/O law: stdout = raw `model_dump_json(indent=2)` only; stderr = Rich (`Console(stderr=True)`); disk = `--out-file`. Zero bare `print()`.
- Every CLI: `#!/usr/bin/env python`, `Usage()` function, every option has short + long switch, no positional args.
- All Phase payloads: `ConfigDict(strict=True, extra="forbid")`. New fields on existing payloads must carry a default so prior producers still validate.
- Every phase calls `cli_engine.load_upstream()` and `cli_engine.emit()`; P04 → P05 contract stays `Phase04ChunkedOutput`.
- No new runtime dependency. No local LLM weights. LLM calls go to `RAG_OLLAMA_URL` from `.env` (SSoT; default in `.env.example` is `https://ollama2.braisenly.com`).
- Windows (adagio): PowerShell only for commands; `verify_pipeline.ps1` and `.sh` must stay behavior-identical.
- Existing 17 tests, `verify_pipeline.ps1` Stages 0-3 and `verify_pipeline.sh` must pass unchanged at every commit.
- Conventional Commits with scope. Implementation runs on a new worktree branch `feat/minimal-pluggability` off `development`, draft PR into `development`, every commit pushed. Version bump `0.1.0 → 0.2.0` in the merge to `development` (MINOR, three numbers, no build suffix).

## Review Focus

1. `--strategy` given an unknown name (typo, uninstalled third-party): must exit non-zero with the list of known names on stderr, nothing on stdout. Test in Task 1.
2. Old `artifacts/04_chunked.json` (no `chunk_strategy` field) piped into P05: must still validate. Test in Task 1.
3. Old `artifacts/06_query_plan.json` containing `index_snapshot`: must be rejected by `extra="forbid"` with a clear Pydantic error, not silently accepted. Test in Task 2.
4. Section with empty body or a single very long sentence under `recursive`: must yield ≥1 chunk and never an empty-text chunk. Test in Task 1.
5. `rag-p04b` with a corpus that yields zero entities: must still pass the Phase04 payload through unchanged and write a graph artifact with empty lists. Test in Task 4.

---

### Task 1: Chunker registry + `--strategy` on P04

**Files:**
- Create: `chunkers.py`
- Modify: `rag_contracts.py:93-95` (`Phase04ChunkedOutput`)
- Modify: `p04_chunk.py:33-78` (`main`)
- Modify: `pyproject.toml` (`[tool.hatch.build.targets.wheel].include` add `chunkers.py`; add `[project.entry-points."phase_rag.chunkers"]` with the built-ins so the entry-point path is exercised)
- Test: `tests/test_chunkers.py`

**Interfaces:**
- Produces in `chunkers.py`:
  - `Chunker = Callable[[ParsedSection, int, int], list[DocumentChunk]]` (args: section, max_words, overlap)
  - `def chunk_sliding_window(sec: ParsedSection, max_words: int, overlap: int) -> list[DocumentChunk]` (verbatim move of the loop body at `p04_chunk.py:56-73`)
  - `def chunk_recursive(sec: ParsedSection, max_words: int, overlap: int) -> list[DocumentChunk]` (split on `\n\n`; paragraphs over `max_words` split on `(?<=[.!?])\s+`; sentences over `max_words` fall back to `chunk_sliding_window`; `overlap` ignored; `chunk_id=f"{sec.section_id}_rec_{idx}"`)
  - `BUILTIN_CHUNKERS: dict[str, Chunker] = {"sliding_window": ..., "recursive": ...}`
  - `def resolve_chunker(name: str) -> Chunker` (built-ins first, then `importlib.metadata.entry_points(group="phase_rag.chunkers")` by name, each `.load()` in its own try/except; raise `KeyError(f"Unknown chunker '{name}'. Known: {sorted(...)}")`)
  - `def available_chunkers() -> list[str]`
- Produces in `rag_contracts.py`: `Phase04ChunkedOutput.chunk_strategy: str = "sliding_window"`
- Produces in `p04_chunk.py`: option `--strategy/-s` (default `"sliding_window"`); on `KeyError` from `resolve_chunker` → `typer.BadParameter` (exit 2, message to stderr).

- [ ] **Step 1: Write failing tests** in `tests/test_chunkers.py`

```python
def test_sliding_window_matches_legacy_output(): ...   # same chunk_ids/text as current p04 for a fixed section (max_words=8, overlap=2)
def test_recursive_splits_paragraphs_then_sentences(): ...  # 2 paragraphs, 2nd has 3 sentences > max_words -> chunk per sentence, no empty text
def test_recursive_empty_body_yields_one_chunk(): ...
def test_resolve_chunker_unknown_lists_known_names(): ...  # KeyError message contains "sliding_window"
def test_resolve_chunker_via_entry_point(): ...  # entry point "sliding_window" resolves to chunk_sliding_window (requires `uv sync`)
def test_phase04_output_without_chunk_strategy_still_validates(): ...
def test_p04_cli_unknown_strategy_exit_nonzero_clean_stdout(tmp_path): ...  # subprocess: stdout == b"", exit != 0, "Known" in stderr
```

- [ ] **Step 2:** `uv run pytest tests/test_chunkers.py -v` → FAIL (`ModuleNotFoundError: chunkers`)
- [ ] **Step 3:** Implement `chunkers.py` and the three modifications above. `p04_chunk.main` body becomes: resolve chunker → `chunks = [c for sec in upstream.sections for c in chunker(sec, max_words, overlap)]` → `Phase04ChunkedOutput(run_id=..., chunks=chunks, chunk_strategy=strategy)`.
- [ ] **Step 4:** `uv sync && uv run pytest -q` → all pass (17 existing + 7 new).
- [ ] **Step 5:** `uv run ruff check .` → clean.
- [ ] **Step 6: Commit** `feat(p04): chunker registry with --strategy and entry-point discovery`

### Task 2: Decouple P06 from the P05 payload

**Files:**
- Modify: `rag_contracts.py:124` (replace `index_snapshot: Phase05IndexedOutput` with `qdrant_collection: str`)
- Modify: `p06_query.py:80` (`qdrant_collection=upstream.qdrant_collection`)
- Modify: `p07_retrieve.py:86` (`collection = upstream.qdrant_collection`)
- Modify: `tests/test_p05_and_p07.py:192`
- Modify: `p00_crag_orchestrator.py` only if it reads `index_snapshot` (audit found no reference; confirm with `rg index_snapshot`)
- Test: `tests/test_p06_decoupled.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `Phase06QueryPlanOutput.qdrant_collection: str`. P06 input model stays `Phase05IndexedOutput` (so `rag-p05 | rag-p06` is unchanged); `p06` may also be run with a hand-written minimal Phase05 payload (`indexed_records: []`).

- [ ] **Step 1: Failing tests**

```python
def test_phase06_rejects_legacy_index_snapshot(): ...  # ValidationError, "extra_forbidden"
def test_phase06_payload_is_small(): ...  # model_dump_json() of a plan has no "indexed_records" key
```

- [ ] **Step 2:** `uv run pytest tests/test_p06_decoupled.py -v` → FAIL.
- [ ] **Step 3:** Apply the four edits.
- [ ] **Step 4:** `uv run pytest -q` → pass (live p05/p07 test included).
- [ ] **Step 5: Commit** `refactor(contracts): P06 carries qdrant_collection instead of full P05 snapshot`

### Task 3: `rag-check` topology command

**Files:**
- Create: `rag_check.py`
- Modify: `pyproject.toml` (`[project.scripts] rag-check = "rag_check:app"`, wheel include)
- Test: `tests/test_rag_check.py`

**Interfaces:**
- Produces: `PHASE_MODULES: list[str] = ["p01_load", ..., "p10_evaluate"]`; `def check_chain(modules: list[str]) -> list[str]` returning human-readable mismatch lines (empty = OK), comparing `importlib.import_module(m).cli_engine.output_model` with `import_module(next).cli_engine.input_model` (identity). CLI: `--json/-j` (emit `{"ok": bool, "chain": [...], "errors": [...]}` on stdout), `--quiet/-q`. Exit 1 on any error. Must not instantiate embedders (imports only; `hybrid_engine` loaders are lazy singletons, confirmed).

- [ ] **Step 1: Failing tests**

```python
def test_check_chain_ok_on_real_modules(): assert check_chain(PHASE_MODULES) == []
def test_check_chain_reports_mismatch(): ...  # monkeypatch p04.cli_engine.output_model to Phase03ParsedOutput -> one error naming "p04_chunk -> p05_index"
def test_rag_check_cli_json_stdout_only(tmp_path): ...  # subprocess --json: stdout parses, "ok": true
```

- [ ] **Step 2:** run → FAIL. **Step 3:** implement (~40 LOC). **Step 4:** `uv run pytest -q`; `uv run rag-check` exit 0.
- [ ] **Step 5: Commit** `feat(cli): rag-check adjacency contract validator`

### Task 4: GraphRAG side-artifact stage `rag-p04b`

**Files:**
- Create: `p04b_graph.py`
- Modify: `rag_contracts.py` (append `GraphNode`, `GraphEdge`, `GraphArtifact(BasePhasePayload)` with `phase_name="04b_graph"`, `nodes: list[GraphNode]`, `edges: list[GraphEdge]`, `extractor: str`)
- Modify: `pyproject.toml` (`rag-p04b = "p04b_graph:app"`, wheel include)
- Test: `tests/test_p04b_graph.py`

**Interfaces:**
- `GraphNode(entity: str, chunk_ids: list[str])`, `GraphEdge(source: str, target: str, weight: int, chunk_ids: list[str])`.
- CLI options: `--in-file/-i`, `--out-file/-o` (default `artifacts/04b_passthrough.json`, Phase04 payload unchanged), `--graph-file/-g` (default `artifacts/04b_graph.json`), `--extractor/-e` (`heuristic` default), `--min-weight/-w` (default 1), `--quiet/-q`.
- `def extract_entities_heuristic(text: str) -> list[str]`: regex `\b[A-Z][A-Za-z0-9\-]+(?:\s+[A-Z][A-Za-z0-9\-]+)*\b`, drop single-token matches that are sentence-initial stopwords (`The, A, An, This, It, In, On, For`), dedupe, keep ≥2 chars.
- Edges: all unordered entity pairs co-occurring in one chunk; weight = number of chunks.
- `cli_engine = PhaseCLI("Phase 04b: Entity Graph (pass-through)", Phase04ChunkedOutput, Phase04ChunkedOutput, "artifacts/04b_passthrough.json")`; graph artifact written with `GraphArtifact.model_dump_json(indent=2)` to `--graph-file` and a second Rich panel on stderr (node/edge counts, top-5 entities).
- `# ponytail: heuristic NER; upgrade path = --extractor ollama (Task 6 pattern) or spaCy`.

- [ ] **Step 1: Failing tests**

```python
def test_extract_entities_heuristic_basic(): ...  # "Qdrant fuses Jina-v3 with SPLADE." -> {"Qdrant","Jina-v3","SPLADE"}
def test_graph_edges_from_cooccurrence(): ...  # 2 chunks sharing entities -> weight 2
def test_p04b_passthrough_unchanged_and_graph_written(tmp_path): ...  # subprocess: stdout JSON == input JSON (modulo timestamp), graph file validates GraphArtifact
def test_p04b_zero_entities_still_passes_through(tmp_path): ...
```

- [ ] **Step 2-4:** FAIL → implement (~90 LOC) → `uv run pytest -q`; pipe smoke: `uv run rag-p03 -i artifacts/02_markdown.json | uv run rag-p04 | uv run rag-p04b | uv run rag-p05 --quiet` exit 0.
- [ ] **Step 5: Commit** `feat(p04b): GraphRAG entity co-occurrence side-artifact stage`

### Task 5: Verification batteries + docs

**Files:**
- Modify: `verify_pipeline.ps1` (Stage 0: add `uv run rag-check`; Stage 1: after Phase 04, exercise `rag-p04 --strategy recursive` and `rag-p04b`; Stage 2 pipe unchanged)
- Modify: `verify_pipeline.sh` (identical additions)
- Modify: `README.md` (section "Pluggability": strategy flag, entry-point group, pass-through stage pattern, `rag-check`)
- Modify: `docs/continuity/CURRENT_TASK_STATE.md`, `PLANS.md`
- Modify: `pyproject.toml` version stays `0.1.0` on the feature branch; MINOR bump happens in the merge commit to `development` per policy.

- [ ] **Step 1:** Edit both scripts; keep the `$proc = Start-Process ... -RedirectStandardOutput/Error` pattern used at `verify_pipeline.ps1:165`.
- [ ] **Step 2:** `pwsh -File verify_pipeline.ps1` → Stages 0-3 PASS with new sub-steps visible. (`verify_pipeline.sh` run by the Bash-capable reviewer on largo or Git-Bash only as a parity check, never as the adagio gate.)
- [ ] **Step 3: Commit** `test(verify): exercise rag-check, --strategy recursive, rag-p04b in batteries`

### Task 6 (optional, last): `contextual` chunker via cloud Ollama

**Files:** `chunkers.py` (+`chunk_contextual`), `.env.example` (`RAG_OLLAMA_URL`, `RAG_OLLAMA_MODEL=gpt-oss:20b-cloud`), `tests/test_chunkers_live.py` (marked `live`, skipped without `RAG_OLLAMA_URL`).

**Interfaces:** `chunk_contextual` = `chunk_sliding_window` then one HTTP call per chunk (`urllib.request`, `POST {RAG_OLLAMA_URL}/api/generate`, prompt from Anthropic's contextual-retrieval recipe) prepending a one-sentence situating prefix to `text`; `parent_markdown` unchanged. Registered as `"contextual"`. On HTTP failure: fall back to the un-prefixed chunk and log once to stderr.

- [ ] Steps: failing live test → implement (~40 LOC) → `uv run pytest -m live -q` → commit `feat(p04): contextual chunker via RAG_OLLAMA_URL`.

---

## Orchestration: implementation → review → live exercise

Token-efficiency rules (all agents): brief = this plan's task section + the Interfaces blocks it consumes, nothing else; use codemunch for all code reads (`repo zautke/phase-rag-cli`, re-index after edits with `register_edit`); report ≤250 words: files touched, test command + pass count, ruff result, open questions. No file dumps back to lead. Lead monitors every agent with a 20-min deadline and does the work inline on timeout.

| Wave | Agent | Model | Scope (file lock) | Gate |
|---|---|---|---|---|
| 0 | lead | — | worktree `feat/minimal-pluggability` off `development`, draft PR, `.env.example` | `uv sync`, `uv run pytest -q` = 17 pass |
| 1 (parallel) | impl-A | sonnet | Task 1: `chunkers.py`, `p04_chunk.py`, `rag_contracts.py` (Phase04 only), `pyproject.toml` (entry-points + include), `tests/test_chunkers.py` | its tests + full suite green, ruff clean |
| 1 (parallel) | impl-B | sonnet | Task 2: `rag_contracts.py` (Phase06 only), `p06_query.py`, `p07_retrieve.py`, `tests/test_p05_and_p07.py`, `tests/test_p06_decoupled.py` | same |
| 1 (parallel) | impl-C | sonnet | Task 3: `rag_check.py`, `pyproject.toml` (scripts), `tests/test_rag_check.py` | same |
| 1 → merge | lead | — | resolve `rag_contracts.py`/`pyproject.toml` overlaps (disjoint hunks; rebase order A, B, C) | full suite green |
| 2 | impl-D | sonnet | Task 4: `p04b_graph.py`, `rag_contracts.py` (Graph models), `pyproject.toml`, `tests/test_p04b_graph.py` | same + pipe smoke |
| 2 (parallel) | impl-E | sonnet | Task 5 scripts + README + continuity | `verify_pipeline.ps1` Stages 0-3 PASS |
| 3 | review-1 | opus | whole-branch diff review: correctness vs plan Interfaces, Tri-Plex law, strict contracts, Windows BOM path | findings list; impl agents fix; re-review |
| 3 (parallel) | review-2 | opus | `ponytail-review` (over-engineering only) + `rag-check`/`chunkers` API reuse audit | findings; fixes |
| 4 | live-QA | opus | adagio PowerShell: `pwsh -File verify_pipeline.ps1`; isolated runs of `rag-p04 -s recursive`, `rag-p04b`, `rag-check --json`, unknown-strategy negative test (expected exit 2, empty stdout); full pipe `rag-p01 | … | rag-p10`; `rag-p00 --crag-threshold 0.92` convergence; capture stderr panels + artifact listings into kb run-ledger note `projects/phase-rag-cli/run-ledger` | all PASS; negatives PASS = declared failure |
| 5 | lead | — | Task 6 only if Waves 1-4 green; then PR ready-for-review, wait for review bots, address, merge to `development` with `pyproject.toml` version `0.2.0` + `changeset.md` entry | PR merged |

Metrics registry (hard test metrics directive): register `chunk_count_sliding`, `chunk_count_recursive`, `graph_nodes`, `graph_edges`, `p04_wall_ms`, `p04b_wall_ms`, `rag_check_wall_ms` on the Wave 4 run; bands reported, not gating.

## Self-review

- Spec coverage: audit §"Adopted minimal architecture" items 1-7 → Tasks 1 (2, 3, 7), 2 (4), 3 (6), 4 (5), 5 (batteries); item 1 (keep pipe) is a constraint. Contextual chunking (SOTA research §5) → Task 6.
- Type consistency: `Chunker` signature identical in Task 1 Interfaces, `chunk_recursive`, Task 6; `qdrant_collection: str` used identically in Tasks 2 and 4b smoke; `cli_engine` module attribute confirmed present in all 11 phase modules.
- Not planned (YAGNI, recorded): P07 one-hop graph expansion; late chunking; ColBERT slot; `FormulaQuery` boosting (local-mode support unverified); pluggy.
