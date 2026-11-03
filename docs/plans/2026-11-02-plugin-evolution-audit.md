# Audit: `docs/rag_plugin_evolution_architecture.md` (Pluggable RAG Evolution)

Date: 2026-11-02. Auditors: session lead (Fable 5.1) + two independent Opus reviewers (A: over-engineering, B: correctness/regression). Grounded against repo `zautke/phase-rag-cli` at `development@7aab409` / `main@1b617bc` via jcodemunch index (172 symbols, 22 files).

## Verdict

**ADAPT a thin subset. REJECT the doc as written.** The proposed Blackboard Envelope (`PipelinePacket`), async `RAGPhasePlugin`, `PluginRegistry`, JSONL streaming and the re-port of P05/P07 duplicate what the UNIX pipe + `PhaseCLI` + strict Pydantic contracts already provide, and the ported code does not import, wipes the index per chunk, and regresses retrieval. The stated goal ("swap a chunker / insert a GraphRAG stage without breaking adjacent code") is reachable in roughly 40 LOC against the existing architecture.

## Construct-level verdicts (merged A + B)

| Construct | Verdict | Reason | Replacement |
|---|---|---|---|
| `PipelinePacket` envelope | REPLACE | Only real coupling it fixes: P06 embeds whole Phase05 output as `index_snapshot` while P07 reads only `index_snapshot.qdrant_collection`. | `qdrant_collection: str` on `Phase06QueryPlanOutput`. |
| `ArtifactSlot` + 11 slot models | CUT | Weaker copies of `DocumentChunk`, `ParsedSection`, `RetrievedCandidate`; `RetrievedHits.candidates: List[Dict[str, Any]]` drops typing and per-branch scores. | Existing item models. |
| `SLOT_SCHEMA_MAP` | CUT | Third copy of the type map, already out of sync (`EVAL_METRICS` in enum, absent from map → `set_slot` `KeyError`). | None. |
| `get_slot` / `set_slot` / `fork` | CUT | `set_slot` dump→validate→dump; `get_slot` revalidates every read; `fork` shallow-copies (`dict(v)`) so nested lists alias across siblings. | `model_validate` on existing models. |
| `PluginTrace` lineage | REPLACE | `elapsed_ms` cumulative from `t0` across yields; `added_slots` reports declared not actual. `run_id` + on-disk artifacts already give provenance. | Nothing now; optional `producer: str` on `BasePhasePayload` if ever needed. |
| `RAGPhasePlugin` ABC | CUT | Any executable honoring stdin JSON → stdout JSON + strict model is already a plugin. | `PhaseCLI(input_model, output_model)`. |
| `async def transform` | CUT | SentenceTransformer, fastembed ONNX and sync `QdrantClient` block the loop; zero concurrency; per-packet calls make embedding batch-of-1. | Sync functions over lists (existing). |
| `PluginRegistry` | REPLACE | Global mutable class dict filled by import side effects. | `dict[str, Callable]` per phase selected by CLI flag. |
| Topology validation | REPLACE | Its one value: catching miswiring before model weights load. | `rag-check` (~15 LOC) comparing phase N `output_model` with phase N+1 `input_model`. |
| JSONL envelope / `jsonl_stream` | CUT | Module does not exist in repo (zero hits). Streaming per chunk defeats batch encoding; corpus fits in RAM. | One JSON document per hop (existing). |
| Re-port P05/P07 as plugins | CUT | Rewrites verified code (17/17 pytest, both live batteries) and regresses it. | Leave `p05_index.py`, `p07_retrieve.py` alone. |
| `EmptyPluginConfig` (`strict=False, extra="allow"`) | CUT | Violates invariant 2; config typos silently accepted. | Typer options. |

## Defects in the doc's code (Audit B, verified against repo symbols)

| # | Sev | Doc line | Defect | Evidence |
|---|---|---|---|---|
| 1 | H | 40 | `from jsonl_stream import ...` — module does not exist | repo-wide search: 0 hits |
| 2 | H | 321, 357 | `Optional` used, never imported → Pydantic model build error | Phase 3 import block |
| 3 | H | 336-337 | `ensure_hybrid_collection(client, ..., recreate=True)` per chunk packet → deletes collection every chunk; only last chunk survives | `hybrid_engine.ensure_hybrid_collection`: `if exists and recreate: delete_collection` |
| 4 | H | 336, 348, 375 | Qdrant client opened/closed per packet; embedded `QdrantClient(path=)` holds a file lock → concurrent packets collide | `get_qdrant_client` path fallback |
| 5 | H | 123-135 | `SLOT_SCHEMA_MAP` lacks `EVAL_METRICS` → `set_slot` `KeyError` | enum vs map |
| 6 | H | 241-396 | No plugin provides `AST_SECTION`, `QUERY_PLAN`, `RERANKED_CONTEXT`, `GENERATION_RESULT`, `EVAL_METRICS`; the doc's own stdlib chain fails its own validator | `validate_pipeline_topology` |
| 7 | H | 161-221 | Validator is linear set-union; no cardinality. Loader/chunker fan out 1→N; rerank/eval/CRAG need N→1 reduce; index side never joins query side | `fork()`, validator |
| 8 | H | 106-114 | `List[Dict[str, Any]]` candidates/top_items drop strict typing | `RetrievedCandidate`, `RerankedContextItem` |
| 9 | M | 289, 344 | Payload drops `doc_id`/`header_hierarchy`; prefix changes `[Doc: X \| Section: Y]` → `[A > B]` → different embeddings | `p05_index.main` |
| 10 | M | 382 | `RrfQuery` lacks `weights=[dense_weight, sparse_weight]` | `p07_retrieve.main` |
| 11 | M | 388-393 | Per-branch `dense_score`/`sparse_score` diagnostics lost | p07 branch maps |
| 12 | M | 333-334 | Batch-of-1 encode vs whole-corpus batch in p05 | `embed_dense_batch(contextualized_texts)` |
| 13 | M | 143-158 | `PipelinePacket` has no `strict`/`extra="forbid"` | invariant 2 |
| 14 | M | 172-173 | `EmptyPluginConfig` `extra="allow"` | invariant 2 |
| 15 | M | all | async wrappers over sync calls | engine sources |
| 16 | L | 23 | `importlib.metadata` imported, unused | imports |
| 17 | L | 148 | `ControlFlags` PascalCase field | naming |
| 18 | L | 165 | shallow `fork` | `dict(v)` |
| 19 | L | 195-196 | cumulative `elapsed_ms` | `execute_packet` |

## Regressions vs current pipeline (what the doc drops)

- Tri-Plex I/O: no stdout emitter, no stderr Rich panel, no `--out-file` artifacts; `err_console` imported, unused.
- `ensure_utf8_streams()` + `utf-8-sig`/BOM strip (`PhaseCLI.load_upstream`) gone → Windows pipes break.
- Output re-validation before emit (`PhaseCLI.emit`) gone.
- RRF weights, per-branch scores, prefetch telemetry, `route`, `metadata_filters`, `index_snapshot` lineage dropped.
- Whole-corpus batch encode + single upsert lost; `--recreate/--append` choice lost.
- No plugin for reranker backends, Lost-in-the-Middle ordering, parent dedup, CRAG verdict, RAG Triad eval, P00 loop.
- Typer CLIs (short+long switches, `Usage()`) and `rag-pNN` entry points disappear; `p00.invoke_cli_phase` subprocess contract breaks.

## Top 5 risks of adopting as written

1. Data loss (defect 3): only the last chunk survives indexing.
2. Throughput collapse: batch-of-1 embedding, per-chunk client open/close, per-chunk packet deep copy.
3. Weaker contracts: `Dict[str, Any]` slots, `extra="allow"` config, no per-phase `load_upstream`.
4. Breaks the verified surface: battery 2c stdout round-trip, `verify_pipeline.ps1/.sh`, 17 tests, p00 subprocess contract.
5. Retrieval/CRAG regressions: weights and branch diagnostics dropped; fan-out async generators never reconciled with the P00 rewrite loop.

## Adopted minimal architecture (what the implementation plan builds)

1. Keep the pipe, `PhaseCLI`, strict contracts. **The UNIX pipe is the plugin bus.**
2. Chunker swap: `CHUNKERS: dict[str, Callable[[ParsedSection, int, int], list[DocumentChunk]]]` + `--strategy/-s` on `p04_chunk.py`.
3. External stage: any executable reading Phase N JSON and writing Phase N+1 JSON drops in (`rag-p03 | my-chunker | rag-p05`). Zero LOC.
4. Decouple P06 from P05: replace `index_snapshot` with `qdrant_collection: str`.
5. Optional enrichment stage pattern (Phase N in → Phase N in, declared optional field) for GraphRAG; written only when needed.
6. `rag-check`: adjacency contract check across the 10 phases before loading weights.
7. Entry points (`[project.entry-points."rag.chunkers"]`) only when third-party strategies actually exist.

Unverified: neither auditor executed the doc's code; defects 1-5 are from reading; defect 3 is confirmed against `ensure_hybrid_collection` source.
