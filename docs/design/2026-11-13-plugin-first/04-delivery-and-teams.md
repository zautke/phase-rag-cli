# Delivery, teams, and evidence gates

Status: proposed delivery plan; no product implementation is authorized by this document alone. Architecture and public interfaces are specified in [02-architecture.md](02-architecture.md), current implementation evidence in [01-audit.md](01-audit.md), run telemetry and records in [03-observability.md](03-observability.md), and supporting sources in [05-research.md](05-research.md).

## Team model and ownership

Use multiple **teams**, with a named lead and explicit file ownership per worktree. Assign bounded parallel implementation to Luna at extra-high reasoning effort and independent integration, design review, and difficult compatibility decisions to Terra at high reasoning effort. The orchestrator owns integration and acceptance; reviewers must not approve their own changes. Record actual model, effort, agent, assigned scope, worktree, start time, deadline, and result in the run ledger. If those model/effort settings are unavailable, report the mismatch and obtain the lead's disposition; do not label another configuration as the requested one.

| Team | Primary ownership | Gate and independent reviewer |
|---|---|---|
| Contracts and migration | Strict payload envelopes, version registry, migration fixtures, public protocol exports; no provider implementation | Terra reviewer checks historical artifacts, compatibility, and contract isolation |
| Runtime and CLI integration | Discovery, capability resolution, chain/branch/reducer execution, existing phase adapters, error and cancellation paths | Separate Terra reviewer checks boundaries, stdout and behavior parity |
| Provider and storage | Provider entry points, capability implementations, storage identity, idempotent writes; no contracts ownership | Independent reviewer checks provider lifecycle and incompatible-space rejection |
| Quality and live verification | Cross-platform battery, fixtures, real corpus, run evidence and demo script; no implementation approval of own tests | Independent lead reviews evidence against acceptance criteria and source behavior |

The lead assigns exact paths before edits, prevents overlap, verifies branch/worktree and dirty state, and integrates in dependency order. Never reset or overwrite unrelated work. Review findings are checked against actual project rules and implementation before action. Fix genuine defects in the active work; review completion requires resolution, not merely a posted review.

## Waves and stop conditions

### Dispatch roster and path ownership

These are implementation teams, not agents claimed to be running now. Each team has a Terra/high implementer and Luna/xhigh fixture/documentation partner. A separate Terra/high reviewer handles work it did not author. At most eight workers plus lead; sequence teams to respect capacity. Lead alone owns workspace manifests, lockfile, release metadata and top-level integration.

| Team | Terra/high write ownership | Luna/xhigh write ownership | Independent gate |
|---|---|---|---|
| A — contracts | `packages/rag-contracts/**` | `tests/contracts/**`, `tests/fixtures/migration/**` | Runtime reviewer validates external consumer ergonomics |
| B — composition | `packages/rag-runtime/**`, numbered CLI adapter files | `tests/runtime/**`, external plugin fixture distributions | Provider reviewer validates branch and subprocess semantics |
| C — providers | `packages/rag-builtins/**`, existing provider modules during migration | `tests/providers/**`, real-corpus expectation manifest | Contracts reviewer validates spaces, batch bounds and evidence |
| D — diagnostics | `packages/diagnostic-contracts/**`, `packages/phase-rag-logging/**`, `packages/phase-rag-errors/**` | `tests/diagnostics/**`, diagnostic fixture plugins | Independent reviewer validates all six module/lane combinations |
| E — deployment | Packaging/install verification and isolated backend validation, assigned scripts only | `verify_pipeline.ps1`, `verify_pipeline.sh`, walkthrough twins and usage documentation | Lead plus independent Terra assess complete run evidence |

Team A precedes B/C. D may start after shared event contracts are agreed; B integrates D through injection. E follows integrated builds. Contracts changes reopen affected dependent gates. Workers must not edit lead-owned manifests or another team's files; request an interface change through lead.

Dispatch limits: 20 minutes for a bounded implementation slice, 10 minutes for a review, 5 minutes for fixture/documentation slices. Inspect liveness/output every 60 seconds; after two checks without observable progress inspect immediately. A long live model run has a declared limit from recorded baseline, initially 10 minutes per phase and 30 minutes per battery; stop gracefully at limit, record partial evidence, diagnose and change one cause before retrying. Never rerun the historical multi-gigabyte failure without confirming batch bounds first.

1. **Baseline and contract:** inventory existing commands, flags, artifacts and historical payloads against feature branch `41811f9`; define strict schemas, plugin API and fixture-backed migrations. Independent review approves the contract before dependent changes.
2. **Parallel implementation:** runtime/CLI and provider/storage teams build against the approved contract in separate worktrees. Keep existing commands usable. Teams publish small, reviewable changes and tests; resolve interface changes through the lead.
3. **Integration and adversarial review:** integrate compatible work, test actual external package discovery, chain/branch/reducer execution and cross-phase capabilities. Separate reviewer checks migration, storage identity, cleanup, error handling, concurrent branches and side-effect boundaries.
4. **Cross-platform battery:** execute Windows PowerShell and real Linux shell twins against the same defined acceptance matrix and a real, permitted corpus. Keep stdout payloads, stderr diagnostics, exit codes, artifact paths, versions and timestamps as durable evidence. Include all success, failure, aborted and partial runs in the knowledge base (KB) project run ledger, linked to registered metric ledgers.
5. **Live demo and release readiness:** only after the preceding checks pass, perform a user-visible walkthrough of the real commands and inspect the resulting outputs. Capture before/after evidence for each user action where the applicable live protocol requires it; record errors, cleanup, and results. Do not represent a scripted dry run or isolated unit test as live behavior.

Each dispatch has a task-specific worst-case deadline, periodic liveness checks, and observable progress. A lead monitors every running agent within the active turn; on timeout, inspect state, stop a dead or stalled worker safely, preserve its work and evidence, and reassign or complete the work inline. Do not wait indefinitely or call a running status progress. Every handoff records files changed, commands run, evidence and open failures. Failures block their gate until fixed and retested; report precise limitations if a real external dependency cannot be reached.

## Acceptance battery

The same battery runs on both supported hosts, using native PowerShell on adagio and real Linux for the shell script. It exercises the shipped commands, not substitute harnesses; Linux execution from Windows uses the approved Windows Subsystem for Linux (WSL) route or a real Linux host. Both script twins provide matching named options and help behavior. Test cold, user-realistic conditions without pre-warming caches or secretly provisioning packages. No local model or large cache downloads on largo; use the approved hosted providers and record selected endpoint/model identities without introducing duplicate configuration.

| Area | Required evidence |
|---|---|
| Compatibility | Existing numbered commands, arguments, inputs, outputs, artifacts, exit status, and full P01–P10 pipe match documented baseline. P00 retry and convergence behavior is exercised with bounded attempts. |
| Extensibility | Install a separate example plugin package through normal package tooling. Prove discovery, ordered chain, independent branches with explicit reducer, and one capability used across phases. Reject duplicate, missing and incompatible plugins. |
| Contracts | Strict validation at each phase and intermediate boundary; old artifacts migrate through declared versions; future, malformed and ambiguous inputs fail without success output. Retain fixture inputs and expected outputs. |
| I/O and durability | Exactly one valid JSON value on stdout, diagnostics on stderr, matching persisted artifact. Inject artifact-write failure and verify preexisting output survives; inspect exit codes and cleanup. |
| Storage and reliability | Index and retrieve real corpus data; check deterministic identities and rejection of mismatched model/dimension/index space. Exercise provider failure, cancellation, branch failure, timeouts, bounded retry, and partial external write reporting. |
| Quality | Type check, lint, focused unit/integration tests, full pipe, and negative tests. Measure registered subsystem metrics on every applicable run and report warning bands without inventing gates. |

Select a real corpus with documented provenance, permissions, expected query/answer cases and enough content to exercise retrieval; keep a small deterministic fixture for narrow regression tests as well. Record corpus identity and versions, configuration identity, platform, timestamps, commands, exit codes, artifact locations, relevant diagnostics and metric values. Explicitly distinguish test doubles from hosted or production-like dependencies. Failed and interrupted runs receive ledger entries too. Store logs at durable locations before reporting; if the canonical KB is unavailable, stage the required entry under the designated deferred-sync procedure and report its path.

## Release and publication

### Clean installation and deployment

Build wheels from approved integration revision under locked uv dependencies. Install CLI, contracts, both diagnostic packages and an independently built fixture plugin into an empty isolated environment using only declared package metadata. Verify help and import behavior before any model access. This is the actual cold-install test; do not preinstall providers to make it pass. Optional provider extras install only when selected. Run the full pipeline, custom plugin composition and replay commands from outside the repository to catch path/import dependencies.

Use existing organization's OTLP gateway/Grafana only after live configuration and route verification. Keep endpoints in environment source of truth. Verify logs and error records from each package by event ID in backend, then inspect in user-visible viewer. All three lanes are enabled in deployed project. Test outages/disk failures only against isolated test destinations; never disrupt shared Docker services to simulate failure. Collector persistence configuration is a deployment gate, not assumed from health status.

Largest owned corpus is the real transcript under `docs/__test_data__/Obsidian, Basic Memory ERO, and GraphRAG - Verbatim Session Transcript - 2026-10-13.md`, historically 184 chunks. Record current corpus hash and current counts; chunk-count change alone is not failure. Include math/table questions with explicit evidence assertions and unsupported-query negatives. Record peak memory for every phase, pipeline expansion ratios, latencies, registered metrics and error/export drop counts. Keep the built-in toy corpus only for narrow smoke checks.

Rollback retains previous wheels, lockfile, configuration, source corpus and index manifest. New schema/index rollout writes a new namespace; switch configured active namespace only after validation. Failed rollout restores prior package/config/namespace selection, not reverse-converts artifacts or deletes old indexes. Record external partial writes. Remove old namespaces only under a separate explicit retention/deletion decision.

Before visible walkthrough, internally execute all phase and diagnostic gates at exact final revision. During walkthrough stop on first unexpected output, fix and review, rerun through failing phase, then restart visible demonstration from P01. No special warm caches. Close agent-opened windows/processes and record retained services explicitly.

Feature work branches from `development`, uses a draft pull request and independent review, and follows the established live-verification and review-bot gates. Preserve unrelated work; do not commit or push it as session cleanup. Before any version operation, consult the canonical release protocol and current branch state. A merge into `development` bumps the three-number version's minor component and resets patch to zero; its version-bump commit updates the single `CHANGELOG.md`. Promotion from `development` into `main` bumps major and resets minor and patch to zero, with no separate promotion entry. Both release branches and published package versions use exactly `MAJOR.MINOR.PATCH`; release tags follow the existing ecosystem convention without a fourth component. Externally constrained package versions remain ecosystem-valid on feature branches too. No separate changeset file is introduced.

Do not merge until evidence, review findings, review bots, and required live gates are satisfied. Publication or other externally visible irreversible action follows the applicable authorization gate. The lead records exact revision, tests, real demo evidence, remaining risks, and cleanup in the final handoff; do not claim a live or cross-platform result that was not observed.
