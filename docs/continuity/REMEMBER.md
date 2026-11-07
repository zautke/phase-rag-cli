# REMEMBER

## Invariants & Architecture Constraints

### 1. Tri-Plex I/O Law (Critical Pipeline Invariant)
- **`stdout`**: Strictly raw `model_dump_json(indent=2)` payload. Zero logs, warnings, debug statements or prints. Since D-A1 (`4057648`) stdout bytes are byte-identical to the `--out-file` artifact (UTF-8, LF, no BOM, no CRLF).
- **`stderr`**: Rich telemetry (`Console(stderr=True)`); child processes of p00 inherit stderr (live progress).
- **`disk`**: Deterministic persistence to `--out-file` (`artifacts/0X_*.json`).

### 2. Strict Contract Enforcement
- All phase outputs inherit `BasePhasePayload` (`ConfigDict(strict=True, extra="forbid")`). Every phase reads upstream through `PhaseCLI.load_upstream()`. `crag_verdict` is `Literal["GROUNDED", "REWRITE_REQUIRED"]`.
- P05 output and P06 plan carry `dense_backend`, `dense_model`, `sparse_model`; P07 retrieves with exactly those (no override). Old P05/P06 artifacts are rejected: regenerate.

### 3. Plugin seams (0.2.0)
- External pipe stage; `--strategy` chunker registry; dense (`sentence_transformers` default | `fastembed`), sparse (`fastembed` SPLADE, `--sparse-model` only), rerank (`sentence_transformers`/bge default | `fastembed`) backends as name -> loader dicts in `hybrid_engine.py`. Unknown name -> `ValueError` "Known: ..." -> exit 2, empty stdout.
- Defaults live in `.env.example` (`RAG_DENSE_BACKEND`, `RAG_DENSE_MODEL`, `RAG_SPARSE_MODEL`, `RAG_RERANK_BACKEND`, `RAG_RERANK_MODEL`, `RAG_CRAG_THRESHOLD` = 0.65 single source, `QDRANT_PATH`).

### 4. Model downloads
- Only through `model_fetch.ensure_model`: aria2c (resumable, 8 connections), announced, live progress on stderr, HF cache layout (`HF_HUB_CACHE` is the single cache root), `.complete` marker, `refs/main` only after verified fetch. aria2c missing = fail fast with install hint, no fallback. Re-index required after 0.2.0 (SPLADE 128 -> 512 tokens).

### 5. Qdrant topology & point identity
- Default embedded `QdrantClient(path=qdrant_path)`; remote via `--qdrant-url`/`QDRANT_URL` with `check_compatibility=False` and one stderr line on fallback. Point ids: `deterministic_point_uuid(chunk_id)` UUIDv5, idempotent upserts.

### 6. Context assembly & evaluation
- P08 Lost-in-the-Middle ordering in `<retrieved_context>`; each context carries `rank="N"` (cross-encoder rank); `top_contexts` stay sorted by score descending. P10 nDCG is computed in rank order. P09 extractive answer skips headings and unpunctuated bullets. `--max-retries N` = N retries after the first attempt.

### 7. Git, versions, KB
- `main` receives only verified `development` by PR; `development` and `main` use exactly `MAJOR.MINOR.PATCH`: 0.2.0 into development (MINOR+1), 1.0.0 into main (MAJOR+1). Changelog is `CHANGELOG.md` only. Commit trailers: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` + `Claude-Session: https://claude.ai/code/session_016DhoU1zVvNyBASGn1qtQf4`.
- All kb writes go to `master-kb` only. If the kb MCP is dead, write straight into `C:\Users\me\master-kb` (no `:` in filenames).
- adagio: PowerShell tool only, never Bash; a `.sh` is proven in WSL via `wsl -d Ubuntu-24.04 --exec bash -lc ...`.

## Binding rulings (copied verbatim from `.superpowers/sdd/release-1.0.0/progress.md`; bracketed prefix = pre-flight row key)
- [T2 vs user] Ruling: default dense backend = sentence_transformers (only verified path), fastembed selectable — why: user demands plugins, ST is the verified default — cost if wrong: flip one env default
- [T2 vs my PM note] Ruling: D5 (HF_HUB_CACHE always, knob deleted) — cost if wrong: re-add one env knob
- [T3 D14 vs org download rule] Ruling: no fallback; fail fast with install hint — cost if wrong: users without aria2c must install it
- [T5 vs one-script-per-host rule] Ruling: proceed
- [T6 docs eviction vs SessionStart continuity hook (reads docs/continuity/)] Ruling: evict; hook degrades to nothing for this repo — cost if wrong: restore docs/continuity from git history
- [T6 merge origin/main] Ruling: merge then delete — makes main an ancestor of development, promotion conflict-free
- Ruling: main checkout (C:\Users\me\dev\phase-rag-cli) is being edited by concurrent Codex CLI sessions (pids 70128 `codex resume` 12:28:19, 219744, 103340): they rewrote docs/continuity/* at 12:29 and restored UML mirror files. Leave main checkout untouched; all work in -wt-feat — why: it is another live session's workspace — cost if wrong: their continuity edits never land (they own them).
- Ruling: D8 stray QDRANT_URL=http://localhost:6333 exists only in the terminal process env (not User/Machine scope, not in pwsh profiles); fix via code (check_compatibility=False + one stderr line), no env mutation — cost if wrong: stray var persists in that terminal only.
- Ruling: rerank backend key 'transformers' vs dense 'sentence_transformers' naming split — rename rerank key to 'sentence_transformers' in Task 4 (p00 default touched there) — cost if wrong: one more rename
- Ruling: sparse seam exposes --sparse-model only (single backend fastembed); no --sparse-backend flag until a second sparse backend exists — why: YAGNI, still a named-dict seam — cost if wrong: add one option
- Task 3: minor (parked): refs/main shared across filter sets → offline refusal after upstream move; online recovers — Ruling: acceptable, real but no dependent work — cost if wrong: one re-download online
- Task 3: minor (parked): size None skipped in verification — Ruling: theoretical (files_metadata=True) — cost if wrong: marker over-claims on exotic repo
- Ruling: --query demo-corpus defaults in p00:171/p06:36 stay — demo defaults, not rewrite fallbacks — cost if wrong: two string edits
- Ruling: p08 default backend stays sentence_transformers/bge (d08c0e0 "fastembed reranker default" only swapped the model under -b fastembed; AGENTS.md names bge via ST) — cost if wrong: flip one constant
- Ruling: CODE FREEZE at 414d66e for the live gate; doc-only/CI-only follow-up commits allowed without re-running phases — cost if wrong: a doc commit never changes runtime
- Ruling: RAG_RERANK_BACKEND/RAG_RERANK_MODEL envvar symmetry on p08 is a code change → deferred to the final-review fix wave after the live gate, then p08 re-run only — cost if wrong: one extra p08 live run
- Ruling: D-A1 is fixed NOW in PhaseCLI.emit (shared path) despite the code freeze; Waves B-D run on the fixed head and p01-p04 are re-run there first — why: the user demo must show the SSoT promise true; cost: one extra 1-minute wave-A re-run
- Ruling D-D1: battery assertion is stale, not the product — stress threshold 0.92 → 0.99, assert converged=False, total_attempts==3, and all 3 attempt queries distinct (rewrite proven); update README/MANUAL/CHANGELOG mentions of 0.92 — cost if wrong: a reranker that scores >0.99 would flip it; then raise to a semantic assertion
- Ruling: docs/continuity/* restored on feat (reverses that part of the eviction) because the SessionStart hook reads it — cost if wrong: six small docs back in repo

## User directives of 2026-11-07 (binding)
- Plugins everywhere: dense, sparse and reranker are named backend plugins; no hard-wired backend, no dead branch.
- Delete the `rag-p04b` GraphRAG stage; KEEP the `--strategy` chunker registry.
- Consolidate batteries: one `verify_pipeline.py` core, thin `.ps1`/`.sh` wrappers with identical flags.
- Evict non-product docs to the kb; the repo keeps README, AGENTS.md, CHANGELOG, `docs/MASTER_MANUAL.md`, the `docs/architecture/` UML mirror and (restored for the SessionStart hook) `docs/continuity/`.
- Per-phase live exercise as a first-time user would meet it, then real-time demo signoff (`demo_phase.ps1 -p pNN`); signoff recorded in the ledger block.
- Sonnet teams: kb recording by a sonnet team; demos and live runs by sonnet at high effort.
- Real corpus: `docs/__test_data__/Obsidian, Basic Memory ERO, and GraphRAG - Verbatim Session Transcript - 2026-10-13.md` runs through all phases first ("bet it fails in phase 0").
- Nobody is done until the user has seen it run.
- Standing org rules in force: every run (failed/killed included) goes in the kb run ledger with logs copied to `C:\Users\me\dev\phase-rag-cli-run-evidence\RUN-<n>\`; found defects are fixed in the same run; no cut or descoped requirements; field conditions (no pre-warmed caches); clean up every window/process agents opened.