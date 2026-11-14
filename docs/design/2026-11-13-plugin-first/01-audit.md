# Plugin-first pipeline: evidence and systematic triage

Date: 2026-11-13. Status: design audit, not runtime certification.

## Scope and provenance

This review evaluates whether the existing retrieval-augmented generation (RAG) pipeline can satisfy the user's newly explicit requirements: multiple plugins within a phase, reuse across phases, independently installed plugin packages, chains and branches, versioned migration, and independent logging/error packages with file, console and official OpenTelemetry lanes.

Three Git states must not be confused:

| Checkout | Revision observed | Meaning |
|---|---|---|
| `C:/Users/me/dev/phase-rag-cli` | `1b617bc530be3eef5a4de3583186c72ce1b14c91` | Main, with unrelated uncommitted continuity, diagrams, corpus and test work |
| `C:/Users/me/dev/phase-rag-cli-wt-feat` | `41811f98055a8eb66f673364768b34b8bbc2a7c7` | Feature implementation inspected for this review |
| `C:/Users/me/dev/phase-rag-cli-wt-design` | branched from development `7aab409` | Documentation-only delivery; its inherited source is NOT the audited feature implementation |

CodeMunch refreshed the main and feature indexes, then supplied symbol outlines and verified source for the findings below. Feature index contains 44 Python files; generated artifacts also entered the index, so search rankings are not exhaustive proof of absence. Large artifact files were excluded by index size limits.

DocMunch initially refused cross-worktree reuse with `equivalent_corpus_stale`. Resolution: invoke its installed MCP server through its own Python environment and call `index_local(worktree_mode="branch_local", use_ai_summaries=false, use_embeddings=false)`. Result: `local/phase-rag-feature-docs`, 18 files, 324 sections, SHA-certified at `41811f9`, no truncation. Retrieved and source-hash-verified MASTER_MANUAL sections 7 and 7.3 plus the normative plugin blueprint in `docs/architecture/PLUGGABLE_INTERFACE_UML.md`.

Knowledge-base sources read: Plugin Evolution Audit and Minimal Pluggability Plan (2026-11-02); Session 2026-11-08..10 demo/failure/recovery handoff; TraceDeck integration manual and October trace-estate inventory. Historical run results below remain historical, not newly executed checks.

## Findings

### A01 — High: selection is not composition

Evidence: feature `chunkers.py:60-64` returns exactly `CHUNKERS[name]`; `hybrid_engine.py:48-53` returns exactly `registry[name]`. MASTER_MANUAL section 7 explicitly describes four seams as a name, registry and CLI switch, without entry-point discovery. The normative blueprint requires repository dictionary edits for in-process additions.

Trigger: configure two retrievers in one phase with an explicit merge, or install a third-party chunker without editing core. Existing selection seams do not provide that composition contract. External executable stages allow replacement but do not define within-phase fan-out or joining.

Disposition: requirement gap, not an undisclosed regression against the old manual. Fix with phase-independent capabilities, configured instances, explicit typed edges and reducer nodes. Acceptance: two external packages compose in one phase; same capability executes in two phase groups with distinct instance IDs and configurations.

### A02 — High: sparse backend cannot actually be swapped through resolver

Evidence: `hybrid_engine.py:149-151`, `get_sparse_embedder(model_name)` calls `resolve_backend(SPARSE_BACKENDS, "fastembed", "sparse")`. MASTER_MANUAL section 7.3 explicitly acknowledges the limitation and additional CLI/payload changes required.

Trigger: register a second sparse backend and select it. Model choice changes, backend still resolves fastembed. Fix common capability selection and carry its instance/space identity through indexing and query paths. Acceptance: fake second backend is selected by configuration and observed in both paths without core edits; unsupported names fail before input consumption or side effects.

### A03 — High: collection reuse does not validate embedding identity here

Evidence: `hybrid_engine.py:180-210`, `ensure_hybrid_collection`: existing collection with `recreate=False` bypasses creation and returns without configuration checks. New collections use named dense/sparse vectors and supplied dimension.

Trigger: reuse collection after changing embedding model, task prefix, normalization or preprocessing. Different dimensions may be rejected downstream; same-dimensional but semantically incompatible spaces may pass transport checks. This helper provides no protection. This finding does not assert no other check exists anywhere in the repository.

Fix: persist embedding-space manifest; compare complete identity before querying/appending; explicit rebuild into new collection for incompatible space. Acceptance: same-dimension different-model negative, dimension mismatch, missing legacy manifest, compatible append, and explicit migration.

### A04 — Medium: core schema encodes one retrieval arrangement

Evidence: `rag_contracts.py:246-254` RetrievedCandidate has dense_score, sparse_score and rrf_fused_score; `:211-220` EnrichedIndexedChunk transports dense vectors and sparse indices/values.

Trigger: add lexical-only, graph, or three-provider ensemble. Plugins must pretend to provide unrelated scores or extend central phase schemas and consumers. Fix domain candidate records with typed named score provenance and explicit reducer output; provider implementation details stay in provider contracts. Acceptance: three retrieval providers merge without adding provider-specific fields to core candidate schema.

### A05 — Medium: section content grows with chunk count

Evidence: `chunkers.py:18-27`, `_make_chunk` copies full `sec.body` into every chunk's parent_markdown. Contracts repeat parent_markdown in chunks, enriched chunks and retrieved candidates. Historical handoff records 1,010,402 repeated bytes inside a 1,203,621-byte chunk artifact for a 66.7 KB input.

Trigger: long section split into many overlapping chunks. Fix parent table once per artifact/store plus stable section references; resolve only selected contexts. Acceptance: increasing chunk count does not multiply stored full parent bodies; references survive store/retrieval boundaries; exact math/table evidence remains available.

### A06 — High: subprocess failure discards structured cause

Evidence: `p00_crag_orchestrator.py:55-84`, `invoke_cli_phase` inherits stderr, captures stdout, then raises generic RuntimeError with script/exit code and “see its stderr above.”

Trigger: child fails inside a remote provider; consumer needs stable classification, original causal chain, retry decision and committed-artifact state. Those cannot be recovered reliably from the wrapper's exception. Fix separate versioned error report channel/artifact, stable error ID and parent-child correlation; preserve stdout's success-payload contract. Acceptance: child failure is inspectable in local file, stderr and remote logs with same error ID, while parent retains meaningful exit status and provenance.

### A07 — Medium: output preview is not an execution event trail

Evidence: `rag_contracts.py:388-422`, `PhaseCLI.emit` serializes, atomically writes artifact, prints preview panel, then writes stdout; StdoutClosed distinguishes broken delivery after commit. This sequencing is valuable and must survive migration.

Trigger: trace time spent within a plugin, retries, branch outcomes or sink degradation. Preview alone cannot establish lifecycle. Add injected logging and error boundaries around execution; preserve explicit artifact-committed versus stdout-delivered states. Acceptance: a broken stdout leaves committed artifact and a delivery error, never a falsely reported rollback.

### A08 — High validation debt: real-corpus failures cannot be closed by small fixtures

Historical evidence only: KB handoff records RUN #130 failing at 184 chunks with a 7.80 GiB SPLADE allocation, and earlier output losing math evidence while evaluation returned perfect metrics. It records subsequent batching/evidence fixes at `a134d95`, 136 tests passing, but live verification outstanding then. Feature HEAD has since advanced; this review does not label those repaired paths as currently broken.

Fix process and verify current behavior: run largest owned corpus under cold field conditions, bound provider batches, preserve math/tables, use independent relevance judgements instead of self-confirming scores. Acceptance: current revision completes all phases with measured peak memory and truthful unsupported-answer negatives. No historical pass substitutes for this gate.

## Keep versus replace

Keep strict trust-boundary validation, pure stdout, independent CLI stages, deterministic point identity where semantics remain unchanged, atomic artifact writes, explicit exit codes, provider laziness, and bounded batching already introduced.

Replace phase-owned plugin identity, hardcoded backend resolution, provider-shaped common schemas, parent duplication, string-only subprocess errors, and reliance on preview panels as observability.

Do not port the previously rejected blackboard proposal wholesale. The November 2 audit identified destructive collection recreation per packet, missing symbols and lost invariants in that proposal. Those are historical proposal defects, not evidence that current executable code recreates per packet. New design must retain strict types and explicit composition without that shared mutable envelope.

## Triage order and closure evidence

1. A01/A02/A04: define and prove plugin contracts with independently installed fixture packages before migrating model code.
2. A06/A07: instrument shared boundaries with the two diagnostics packages and three independent lanes.
3. A03/A05: migrate storage identities and section references with explicit legacy handling.
4. A08: rerun current real-corpus acceptance; fix every reproduced defect before release.
5. Independent review checks both positive tests and expected failures. Every finding closes with changed revision, test/run ID, evidence path, and reviewer; no “fixed” based on source inspection alone.

## Audit limits

This is a targeted source/documentation architecture review, not a whole-repository security, performance or runtime certification. No new model inference, pipeline battery, package installation or remote telemetry emission occurred. Documentation indexing is local lexical indexing, not a model download. Context7 was attempted by both research agents but sign-in expired; primary official sources and GitHub code search were used instead. No current backend health claim is made.

See [architecture](02-architecture.md), [observability](03-observability.md), [delivery and teams](04-delivery-and-teams.md), and [research](05-research.md).

## Evolution log

- 2026-11-13: created from current CodeMunch source, branch-local DocMunch sections, historical KB evidence and user-approved composition requirements; explicitly corrected earlier conflation of branch states and stale document indexing.
