# Plugin-first RAG redesign dossier

Date: 2026-11-13. Status: reviewable design; product implementation not authorized by document delivery alone.

## Read in order

1. [Evidence-backed audit and triage](01-audit.md): current source findings, historical failures, retained behavior and closure criteria.
2. [Architecture](02-architecture.md): plugin contracts, composition, migration, packaging and interfaces.
3. [Logging and error reporting](03-observability.md): two independent modules, each with file, console and official OpenTelemetry export.
4. [Zero-to-deploy plan and agent teams](04-delivery-and-teams.md): ownership, dependencies, review, real-corpus tests and deployment gates.
5. [Research](05-research.md): dated primary sources, alternatives and limitations.

## Requirement traceability

| User requirement | Design location | Acceptance evidence required |
|---|---|---|
| Plugin-first rather than phase-first | Architecture | External plugin installs without core edit |
| Multiple plugins in phase | Architecture / delivery | Chain and explicit branch/reducer tests |
| Reuse across phases | Architecture / delivery | Same capability in two phase groups |
| Versioned payload migration | Architecture | Legacy conversion and incompatible-version negatives |
| Logging as standalone package/decorator | Observability | Standalone and runner usage parity |
| Error reporting as standalone package/decorator | Observability | Causal chain, classification, cancellation tests |
| File lane for both modules | Observability | Independent lane and rotation/failure tests |
| Console lane for both modules | Observability | stderr output, stdout unaffected |
| Official OTel lane for both modules | Observability / research | Actual backend record lookup and correlation |
| Extensive review and current research | Audit / research | Evidence classification and source links |
| Luna/xhigh and Terra/high teams | Delivery | Disjoint ownership, independent review, monitored deadlines |
| Zero-to-deploy / live testing | Delivery | Clean install, real corpus, both shell batteries, visible walkthrough |

## Decisions accepted in conversation

- Ordered chains and branches with explicit reducers, rather than arbitrary graph cycles.
- External plugin packages and discovery are required now.
- Versioned schema migration is allowed; numbered command entry points remain.
- Metadata is default diagnostic content; bounded payload capture is opt-in.
- Local reporting and an operational remote backend are required; reuse existing organization observability infrastructure after verifying it.
- Both logging and errors independently support all three output lanes simultaneously.

## Delivery boundary

This branch changes documentation only. The root checkout's dirty work and feature implementation remain intact. The feature revision audited is `41811f9`; documentation branch was created from development `7aab409`. Do not run product acceptance against this documentation branch's old inherited code and call it verification of the feature revision.

Canonical knowledge-base publication accompanies this dossier under `projects/phase-rag-cli/design-2026-11-13/`. Source documents remain the reviewable repository artifacts; KB notes carry matching content and provenance. Verification results and publication identifiers are in [delivery evidence](06-delivery-evidence.md).

## Evolution log

- 2026-11-13: initial dossier after user requested durable documentation instead of chat summaries.
