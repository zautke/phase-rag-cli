# CURRENT TASK STATE

## Status as of 2026-11-03 (development @ 7aab409; PR #3 docs, PR #4 feat/minimal-pluggability 0.2.0 ready for review)

- **Git & Branch Status:**
  - `main`: `1b617bc` (continuity + architecture map docs). `development`: `7aab409`.
  - PR #3 `docs/plugin-evolution-audit-plan` → `development`: audit of `docs/rag_plugin_evolution_architecture.md`, implementation plan rev 2.1, cherry-picked main-only docs (map + continuity) with `index_snapshot` → `qdrant_collection` fix.
  - PR #4 `feat/minimal-pluggability` → `development`: head `1879771` (`chore(release): 0.2.0`) plus in-flight fix commit (fastembed reranker default wired, p00 forwards p07/p08 knobs, leading-stopword strip in entity heuristic).
  - Stacked draft PR `fix/battery-hardening` → `feat/minimal-pluggability` (in flight): `.ps1` checks every phase exit, `.sh` gains `Usage()`/switches/BOM strip, `client.close()` audit in both, default-threshold CRAG convergence assertion, `-Quiet` wired, logs persisted to `artifacts/verify_*.log`.
- **Core Implementation State (0.2.0):**
  - 10 phases + `rag-p00` unchanged in contract except `Phase06QueryPlanOutput.qdrant_collection: str` (replaces embedded `index_snapshot`).
  - `chunkers.py` registry: `--strategy sliding_window|recursive` on `rag-p04`; `Phase04ChunkedOutput.chunk_strategy` (defaulted).
  - `rag-p04b` GraphRAG entity co-occurrence pass-through stage with `GraphArtifact` side artifact (no consumer yet).
  - Tests 30 passing; `verify_pipeline.ps1` Stages 0-3 PASS; `verify_pipeline.sh` Stages 0-3 PASS under WSL Ubuntu-24.04 (parity YES).
  - `docs/MASTER_MANUAL.md` (complete manual, two-opus-reviewed) mirrored to kb `projects/phase-rag-cli/phase-rag-cli-master-manual`.
- **kb:** run ledger `projects/phase-rag-cli/phase-rag-cli-run-ledger-append-only` (RUN #1, #3, reviews; #2, #4 in flight); audit/plan note; blocker-solutions ledger entries (WSL route for bash batteries: `wsl -d Ubuntu-24.04 --exec bash -lc "..."`).
- **Next Resume Points:**
  - Land RUN #2 (`live-qa-1b`) and RUN #4 (`live-qa-2b`, battery hardening) + their `evaluate-live-qa` reviews; merge `fix/battery-hardening` into `feat/minimal-pluggability`; then merge PR #3 and PR #4 into `development` (0.2.0).
  - Promote `development` → `main` as 1.0.0 (MAJOR) after the 100% gate.
