# PLANS

## Active — Release 0.2.0 (development) then 1.0.0 (main): minimal pluggability + audit fix wave

### Goals
10-phase UNIX-piped Hybrid RAG CLI suite + P00 CRAG controller, Tri-Plex I/O (`stdout` JSON, `stderr` Rich, `disk` artifact), strict Pydantic contracts, with every backend a named plugin and every defect D1-D17 of the 2026-11-07 audit fixed and live-proven. Spec: `AGENTS.md`; plan: `.superpowers/sdd/release-1.0.0/plan.md`; ledger: `.superpowers/sdd/release-1.0.0/progress.md`; kb audit: `projects/phase-rag-cli/audits/audit-2026-11-07-lead-synthesis-simplify-streamline-fix`.

### Plan tasks (base 198f343, branch `feat/minimal-pluggability`, PR #4)
| # | Task | Status |
|---|---|---|
| 1 | Delete `rag-p04b`; D10 overlap bounds | DONE `cdfa6dc`, `e3041af` |
| 2 | Dense/sparse/rerank backends as plugins; D1, D5, D8 | DONE `ab9c101` |
| 3 | `model_fetch` hardening D4, D14, D17 | DONE `49d0f34`, `f2e0fe7` |
| 4 | Orchestrator/phase defects D6, D7, D9, D11, D12, D13, D16 | DONE `bd896da` (1 fix round) |
| 5 | One battery core + ps1/sh wrappers; D3, D15; `live` marker | DONE `5a6e3b0` (1 fix round) |
| 6 | Docs, CHANGELOG, trunk sync, CI | DONE `9f23a93` (2 fix rounds) |
| 7 | Live gate: per-phase live exercise, fix teams, demo signoff | IN PROGRESS: Waves A-D run, D-A1/D-B1/D-C1/D-D1 fixed, battery re-runs + real-corpus run + user signoff pending |

Task 7 findings fixed: D-A1 `4057648` (byte-identical stdout/artifact), D-D1 `6c08e23` (stress 0.99), D-B1 `5678070`, D-C1 `55bf1db`, rerank env keys `e3a73c7`, test hardening `bf6c445`. Code freeze rule: product code frozen except fixes the live gate proves necessary; doc/CI-only commits do not require phase re-runs.

### Release runbook (steps remaining)
1. Battery re-runs green: `verify_pipeline.ps1` (adagio) and `verify_pipeline.sh` (WSL Ubuntu-24.04); real-corpus run through all phases; ledger blocks written (kb-recorder).
2. User signoff per phase via `demo_phase.ps1 -p pNN`; nobody is done until the user has seen it run.
3. Fill CHANGELOG `Verification:` line with RUN numbers; commit; push.
4. Whole-branch opus review of `198f343..HEAD`; fix anything found in the same run.
5. Close PR #3 with a note (docs evicted to kb).
6. Bot reviews (Copilot/Codex) on PR #4: verify against repo rules, fix only genuine defects, decline the rest with a one-line reply.
7. Merge PR #4 into `development` (0.2.0, MINOR+1).
8. `release/1.0.0` -> `main` by PR (MAJOR+1; three numbers; no CHANGELOG entry on promotion); merge; tag `v1.0.0`; fast-forward `development` to `main`.
9. Cleanup: remove worktree + merged branches; branch protection on `main`/`development`; stop every process and window opened by agents.

### Non-Goals
- External Qdrant daemon for baseline operation (embedded mode stays default).
- Unstructured stdout logging; loosening `extra="forbid"`.
- A second sparse backend until one exists (`--sparse-model` only; YAGNI).

### Future (after 1.0.0)
Docker Compose for standalone Qdrant; PyPI packaging (`uv build`, `uv tool install`); optional FastAPI/Gradio wrapper.
