# Minimal Pluggability (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Revision 2 (2026-11-02): incorporates three independent Opus plan reviews (executability, regression/platform risk, orchestration/simplicity). Changes from rev 1: `rag-check` task cut (duplicates `verify_pipeline.ps1:69-83`); entry-point discovery and contextual chunker deferred (spec item 7, YAGNI); `chunk_recursive` chunk-id collision fixed; strategy resolved before `load_upstream`; `rag-p04b` emits `upstream` unchanged; `uv sync --all-extras` everywhere; single sequential sonnet implementer; single opus reviewer; live-QA negatives added; version bump + `changeset.md` as last branch commit.

**Goal:** Make chunking swappable, decouple P06 from the P05 payload, and add a drop-in GraphRAG side-artifact stage, without touching the verified Tri-Plex pipe, `PhaseCLI`, or the strict contracts.

**Architecture:** The UNIX pipe stays the plugin bus: any executable reading Phase N JSON and writing Phase N+1 JSON is a plugin (no code needed). Inside a phase, a strategy is a plain function in a name→callable dict selected by a CLI flag. New stages are pass-through CLIs (Phase N in → Phase N out, byte-identical) that write a side artifact. Everything synchronous and corpus-level batched.

**Tech Stack:** Python ≥3.11, `uv`, Pydantic v2 (strict, `extra="forbid"`), Typer, Rich (stderr only), stdlib `re`. No new runtime dependencies.

**Spec:** `docs/plans/2026-11-02-plugin-evolution-audit.md` §"Adopted minimal architecture" (binding). `docs/rag_plugin_evolution_architecture.md` is the rejected original proposal.

## Global Constraints

- Tri-Plex I/O law: stdout = raw `model_dump_json(indent=2)` only; stderr = Rich (`err_console`); disk = `--out-file`. Zero bare `print()`.
- Every CLI: `#!/usr/bin/env python`, `Usage()` function, every option has short + long switch, no positional args.
- All payloads: `ConfigDict(strict=True, extra="forbid")`. New fields on existing payloads carry a default so prior producers still validate.
- Every phase calls `cli_engine.load_upstream()` and `cli_engine.emit()`. P04 → P05 contract stays `Phase04ChunkedOutput`.
- All file writes `encoding="utf-8"` (no BOM). New CLIs instantiate `PhaseCLI` at module level as `cli_engine` (this calls `ensure_utf8_streams()`).
- Environment: always `uv sync --all-extras` (bare `uv sync` uninstalls the `dev` extra: pytest, ruff). Test gate: `uv run pytest -q` (currently 17 pass = 7 + 4 + 6). Lint gate: `uv run ruff check .`.
- adagio (Windows): PowerShell only. `verify_pipeline.sh` parity is NOT run on adagio (Git-Bash banned); mark "not run" in the ledger.
- No new runtime dependency. No local LLM weights.
- Conventional Commits with scope. Work on worktree branch `feat/minimal-pluggability` off `development`, draft PR into `development`, every commit pushed. Last commit on the branch: `pyproject.toml` version `0.1.0 → 0.2.0` (MINOR, three numbers) + create `changeset.md` with the entry.

## Review Focus

1. `--strategy` unknown name: exit 2, stderr lists known names, stdout empty, and this happens before any stdin read. Test: Task 1 `test_p04_cli_unknown_strategy_exit2_clean_stdout`.
2. Legacy `artifacts/04_chunked.json` (no `chunk_strategy`) piped into P05: validates. Test: Task 1 `test_phase04_output_without_chunk_strategy_still_validates`.
3. Legacy Phase06 JSON with `index_snapshot`: rejected with `extra_forbidden`. Test: Task 2 `test_phase06_rejects_legacy_index_snapshot`. Note cascade: `Phase07RetrievedOutput.query_plan` nests Phase06, so legacy 07 artifacts also stop validating into P08 (accepted; artifacts are regenerated per run).
4. `recursive` on a section with two sentences each longer than `max_words`: all `chunk_id`s unique (UUIDv5 collision = silent Qdrant overwrite). Test: Task 1 `test_recursive_chunk_ids_unique_for_long_sentences`.
5. `rag-p04b` must not relabel `chunk_strategy` or regenerate `run_id`: stdout byte-equal to input. Test: Task 4 `test_p04b_passthrough_byte_identical`.

---

### Task 1: Chunker registry + `--strategy` on P04

**Files:**
- Create: `chunkers.py`
- Modify: `rag_contracts.py:93-95` (`Phase04ChunkedOutput`)
- Modify: `p04_chunk.py:33-78` (`main`), `p04_chunk.py:24-29` (`Usage`)
- Modify: `pyproject.toml:42-56` (wheel `include`: add `chunkers.py` and `p04b_graph.py` now, so Task 4 does not touch this hunk)
- Test: `tests/test_chunkers.py`

**Interfaces:**
- `chunkers.py`:
  - `Chunker = Callable[[ParsedSection, int, int], list[DocumentChunk]]` (section, max_words, overlap)
  - `def _windows(words: list[str], max_words: int, overlap: int) -> list[list[str]]` (step `max(1, max_words - overlap)`; identical slicing to the legacy loop at `p04_chunk.py:56-64`; empty `words` → `[]`)
  - `def _make_chunk(sec: ParsedSection, chunk_id: str, words: list[str]) -> DocumentChunk` with `token_count=len(words)`, `header_hierarchy=sec.header_path`, `parent_markdown=f"### {' > '.join(sec.header_path)}\n{sec.body}"`
  - `def chunk_sliding_window(sec, max_words, overlap) -> list[DocumentChunk]`: `chunk_id=f"{sec.section_id}_chk_{idx}"` (legacy parity, including the legacy quirk that an empty body yields zero chunks)
  - `def chunk_recursive(sec, max_words, overlap) -> list[DocumentChunk]`: split `sec.body` on `\n\n` (strip, drop empties); no packing of short paragraphs; a paragraph with more than `max_words` words is split on `(?<=[.!?])\s+`; a sentence with more than `max_words` words is split by `_windows(words, max_words, 0)`; ONE running counter across the whole section: `chunk_id=f"{sec.section_id}_rec_{n}"`; `overlap` ignored; empty/whitespace body → `[]`.
  - `CHUNKERS: dict[str, Chunker] = {"sliding_window": chunk_sliding_window, "recursive": chunk_recursive}`
  - `def resolve_chunker(name: str) -> Chunker`: `KeyError(f"Unknown chunker '{name}'. Known: {', '.join(sorted(CHUNKERS))}")`
- `rag_contracts.py`: `Phase04ChunkedOutput.chunk_strategy: str = "sliding_window"`
- `p04_chunk.py`: option `--strategy/-s` default `"sliding_window"`; FIRST statement of `main` is `try: chunker = resolve_chunker(strategy) except KeyError as e: raise typer.BadParameter(e.args[0])` (exit 2, stderr, before `load_upstream`); then `upstream = cli_engine.load_upstream(in_file)`; `chunks = [c for sec in upstream.sections for c in chunker(sec, max_words, overlap)]`; `Phase04ChunkedOutput(run_id=upstream.run_id, chunks=chunks, chunk_strategy=strategy)`. `Usage()` gains the `--strategy / -s` line.

- [ ] **Step 1: Write failing tests** in `tests/test_chunkers.py` (fixture: `ParsedSection(section_id="s", doc_id="d", header_path=["H1","H2"], body=..., metadata={})`)

```python
def test_sliding_window_legacy_parity():
    # body = " ".join(f"w{i}" for i in range(20)), max_words=8, overlap=2
    # ids == ["s_chk_0","s_chk_1","s_chk_2","s_chk_3"]; starts 0,6,12,18; last text == "w18 w19"
def test_recursive_paragraphs_then_sentences():
    # body = "Alpha beta gamma.\n\nOne two three. Four five six. Seven eight nine.", max_words=5
    # texts == ["Alpha beta gamma.","One two three.","Four five six.","Seven eight nine."]; ids s_rec_0..s_rec_3
def test_recursive_chunk_ids_unique_for_long_sentences():
    # two sentences of 12 words each, max_words=5 -> 6 chunks, len(set(ids)) == 6, no empty text
def test_recursive_empty_body_yields_no_chunks():  # body="  \n\n " -> []
def test_resolve_chunker_unknown_lists_known_names():  # KeyError, "sliding_window" and "recursive" in e.args[0]
def test_phase04_output_without_chunk_strategy_still_validates():  # model_validate(dict without the key).chunk_strategy == "sliding_window"
def test_p04_cli_unknown_strategy_exit2_clean_stdout(tmp_path):
    # subprocess [sys.executable, "p04_chunk.py", "-s", "nope", "-i", <valid 03 json>, "-o", tmp], stdin=DEVNULL
    # returncode == 2, stdout == b"", b"Known:" in stderr
```

- [ ] **Step 2:** `uv run pytest tests/test_chunkers.py -v` → FAIL (`ModuleNotFoundError: chunkers`).
- [ ] **Step 3:** Implement `chunkers.py` and the modifications above.
- [ ] **Step 4:** `uv sync --all-extras && uv run pytest -q` → 24 pass. `uv run ruff check .` → clean.
- [ ] **Step 5: Commit** `feat(p04): chunker registry with --strategy (sliding_window|recursive)`

### Task 2: Decouple P06 from the P05 payload

**Files:**
- Modify: `rag_contracts.py:124` (`index_snapshot: Phase05IndexedOutput` → `qdrant_collection: str`)
- Modify: `p06_query.py:80` (`index_snapshot=upstream` → `qdrant_collection=upstream.qdrant_collection`; line 79 `metadata_filters={"collection": ...}` stays, `tests/test_p06_p08_p09_p10_p00.py:301` asserts it)
- Modify: `p07_retrieve.py:86` (`collection = upstream.qdrant_collection`)
- Modify: `tests/test_p05_and_p07.py:192` (`qdrant_collection=out05_disk.qdrant_collection`)
- Modify: `docs/architecture/phase_rag_pipeline_map.md` Phase 06 §6-7 (replace `index_snapshot` mentions)
- Test: `tests/test_p06_decoupled.py`

**Interfaces:** Produces `Phase06QueryPlanOutput.qdrant_collection: str`. P06 `input_model` stays `Phase05IndexedOutput`; `p00_crag_orchestrator.py` feeds full P05 JSON to P06 each attempt (unchanged, verified: no `index_snapshot` reader remains besides the two lines above).

- [ ] **Step 1: Failing tests**

```python
def test_phase06_rejects_legacy_index_snapshot():
    # valid plan dict + {"index_snapshot": {}} -> ValidationError; "extra_forbidden" in {e["type"] for e in exc.errors()}
def test_phase06_payload_has_no_indexed_records():  # "indexed_records" not in plan.model_dump_json()
```

- [ ] **Step 2:** FAIL. **Step 3:** apply the edits. **Step 4:** `uv run pytest -q` → 26 pass (includes live p05/p07). **Step 5: Commit** `refactor(contracts): P06 carries qdrant_collection instead of full P05 snapshot`

### Task 3: GraphRAG side-artifact stage `rag-p04b`

**Files:**
- Create: `p04b_graph.py`
- Modify: `rag_contracts.py` (append `GraphNode`, `GraphEdge`, `GraphArtifact`)
- Modify: `pyproject.toml:28-40` (`rag-p04b = "p04b_graph:app"`)
- Test: `tests/test_p04b_graph.py`

**Interfaces:**
- `GraphNode(BaseModel)`: `entity: str`, `chunk_ids: list[str]`. `GraphEdge(BaseModel)`: `source: str`, `target: str`, `weight: int`, `chunk_ids: list[str]`. Both strict/forbid like the other item models.
- `GraphArtifact(BasePhasePayload)`: `phase_name: str = "04b_graph"`, `extractor: str`, `nodes: list[GraphNode]`, `edges: list[GraphEdge]`; constructed with `run_id=upstream.run_id`.
- `def extract_entities_heuristic(text: str) -> list[str]`: regex `\b[A-Z][A-Za-z0-9\-]+(?:\s+[A-Z][A-Za-z0-9\-]+)*\b`; drop matches in `{"The","A","An","This","It","In","On","For","And","But"}`; dedupe preserving order. `# ponytail: heuristic NER; upgrade = --extractor ollama|spacy`.
- `def build_graph(chunks: list[DocumentChunk]) -> tuple[list[GraphNode], list[GraphEdge]]`: edges = unordered pairs co-occurring in a chunk; `weight` = number of chunks; `source < target` lexically; sorted by `-weight, source, target`.
- CLI options: `--in-file/-i`, `--out-file/-o` (default `artifacts/04b_passthrough.json`), `--graph-file/-g` (default `artifacts/04b_graph.json`), `--extractor/-e` (`heuristic`; any other value → `typer.BadParameter`), `--min-weight/-w` (default 1, drop edges below), `--quiet/-q`.
- `cli_engine = PhaseCLI("Phase 04b: Entity Graph (pass-through)", Phase04ChunkedOutput, Phase04ChunkedOutput, "artifacts/04b_passthrough.json")`. `main`: `upstream = cli_engine.load_upstream(in_file)`; build graph; `graph_file.write_text(GraphArtifact(...).model_dump_json(indent=2), encoding="utf-8")`; second Rich panel on stderr (node/edge counts, top-5 entities) unless quiet; **`cli_engine.emit(upstream, out_file, quiet)`** (pass the upstream object itself; never rebuild it, so `chunk_strategy`, `run_id`, `timestamp` survive and stdout is byte-identical).
- Consumer of `04b_graph.json`: none yet (P07 one-hop expansion deferred, YAGNI). README states this.

- [ ] **Step 1: Failing tests**

```python
def test_extract_entities_heuristic_basic():  # "Qdrant fuses Jina-v3 with SPLADE. The end." -> ["Qdrant","Jina-v3","SPLADE"]
def test_build_graph_cooccurrence_weight():  # 2 chunks both mention Qdrant+SPLADE -> one edge weight 2, chunk_ids len 2
def test_p04b_passthrough_byte_identical(tmp_path):
    # input = rag-p04 -s recursive output JSON (so chunk_strategy != default); subprocess rag-p04b -i in -o out -g g
    # stdout == input bytes (+ trailing "\n" per PhaseCLI.emit); GraphArtifact.model_validate_json(g) ok; run_id equal
def test_p04b_zero_entities_still_passes_through(tmp_path):  # lowercase-only corpus -> nodes == [] and edges == [], exit 0
```

- [ ] **Step 2:** FAIL. **Step 3:** implement (~90 LOC). **Step 4:** `uv run pytest -q` → 30 pass; ruff clean; smoke: `uv run rag-p03 -i artifacts/02_markdown.json | uv run rag-p04 | uv run rag-p04b | uv run rag-p05 -q` exit 0.
- [ ] **Step 5: Commit** `feat(p04b): GraphRAG entity co-occurrence side-artifact stage`

### Task 4: Verification batteries + docs + version

**Files:**
- Modify: `verify_pipeline.ps1` and `verify_pipeline.sh` identically:
  - Stage 0 print-audit file list (`.ps1:53-58`): add `chunkers.py`, `p04b_graph.py`.
  - Stage 0 chain (`.ps1:69-83`): insert `p04b_graph` between `p04_chunk` and `p05_index` (its in/out are both `Phase04ChunkedOutput`, so the identity assertion holds).
  - Stage 1 after Phase 04 (`.ps1:162-171`): (a) `rag-p04 -i artifacts/03_parsed.json -o artifacts/04_chunked_recursive.json -s recursive` (separate file; canonical `04_chunked.json` untouched so Stages 2-3 are unchanged), validate; (b) `rag-p04b -i artifacts/04_chunked.json -o artifacts/04b_passthrough.json -g artifacts/04b_graph.json`, validate both; (c) negative: `rag-p04 -s nope -i artifacts/03_parsed.json -o artifacts/_neg.json` with `-RedirectStandardError`, assert `$proc.ExitCode -eq 2` and stderr contains `Known:` (PASS = declared failure).
- Modify: `README.md` (section "Pluggability": `--strategy`, external stage drop-in via pipe, pass-through stage pattern, `04b_graph.json` consumer deferred).
- Modify: `docs/continuity/CURRENT_TASK_STATE.md`, `docs/continuity/PLANS.md`.
- Final commit only: `pyproject.toml:7` `version = "0.2.0"`; create `changeset.md` with a `## 0.2.0` entry listing Tasks 1-3.

- [ ] **Step 1:** Edit both scripts (keep the `Start-Process … -RedirectStandardOutput/-RedirectStandardError` pattern; add `$proc.ExitCode` checks to the new steps).
- [ ] **Step 2:** `pwsh -File verify_pipeline.ps1` → Stages 0-3 PASS with the new sub-steps visible.
- [ ] **Step 3: Commit** `test(verify): rag-p04 --strategy recursive, rag-p04b and negative strategy test in batteries`
- [ ] **Step 4:** README + continuity → commit `docs: pluggability section and continuity update`.
- [ ] **Step 5:** version + changeset → commit `chore(release): 0.2.0`.

---

## Orchestration: implementation → review → live exercise

Token rules: brief = one task section + the Interfaces blocks it consumes; code reads via codemunch (`repo zautke/phase-rag-cli`, `register_edit` after edits); reports ≤250 words (files, test command + count, ruff, open questions); no file dumps. Lead arms a 20-min deadline per wave and does the work inline on timeout. One worktree, one implementer: no concurrent `uv sync`/pytest on Windows (`.venv` file locks, fastembed cache race).

| W | Agent | Model | Scope | Gate |
|---|---|---|---|---|
| 0 | lead | — | worktree `feat/minimal-pluggability` off `development`, draft PR, `uv sync --all-extras` | `uv run pytest -q` = 17 pass |
| 1 | impl-1 | sonnet | Task 1 then Task 2 (sequential, same context) | 26 pass, ruff clean, pushed |
| 2 | impl-1 (SendMessage, context kept) | sonnet | Task 3 | 30 pass, p03→p05 pipe smoke |
| 3 | impl-1 | sonnet | Task 4 steps 1-4 | `verify_pipeline.ps1` Stages 0-3 PASS |
| 4 | review-1 | opus | whole-branch diff: correctness vs Interfaces, Tri-Plex, strict contracts, Windows UTF-8, AND over-engineering (ponytail lens) | findings → impl-1 fixes → re-review PASS |
| 5 | live-QA | opus | adagio PowerShell: `pwsh -File verify_pipeline.ps1`; goal pipe `rag-p01 \| rag-p02 \| rag-p03 \| rag-p04 -s recursive \| rag-p04b \| rag-p05 \| rag-p06 \| rag-p07 \| rag-p08 \| rag-p09 \| rag-p10`; `rag-p00 --crag-threshold 0.92` convergence; three negatives (unknown strategy exit 2; legacy 04 JSON without `chunk_strategy` into `rag-p05` validates; legacy 06 JSON with `index_snapshot` into `rag-p07` rejected); metrics baseline; kb run-ledger note `projects/phase-rag-cli/run-ledger` (kb down → stage to `~/.claude/deferred-kb-sync/`); `.sh` parity marked "not run on adagio" | all PASS, negatives PASS = declared failure |
| 6 | lead | — | Task 4 step 5 (0.2.0 + changeset), PR ready-for-review, wait for review bots, address per org rules, merge to `development` | merged |

Metrics registry (binding directive; recorded every later run): `chunk_count_sliding`, `chunk_count_recursive`, `graph_nodes`, `graph_edges`, `p04_wall_ms`, `p04b_wall_ms`. Warning bands set from the Wave 5 first-run baseline (±25% moderate, ±50% high, ±100% critical), reported not gating.

## Deferred (recorded, not planned)

- Entry-point discovery `importlib.metadata.entry_points(group="rag.chunkers")`: spec item 7, only when a third-party chunker exists.
- `contextual` chunker via cloud Ollama: one HTTP call per chunk, live-only test; revisit with a budget.
- P07 one-hop graph expansion (consumer of `04b_graph.json`); late chunking; ColBERT slot; Qdrant `FormulaQuery` (local-mode support unverified).

## Self-review

- Spec coverage: audit items 1 (constraint), 2 (Task 1), 3 (README, Task 4), 4 (Task 2), 5 (Task 3), 6 (cut: already in Stage 0), 7 (deferred).
- Type consistency: `Chunker` signature used identically in Task 1 and `p04.main`; `qdrant_collection: str` in Tasks 2 and 3 smoke; `GraphArtifact.run_id` sourced from `upstream.run_id`; `cli_engine` attribute present in all 11 phase modules (verified) and required in `p04b_graph.py` for the Stage 0 chain import.
- Test counts: 17 → 24 → 26 → 30.
