# TASKS

## Completed
- [x] Wave 1-7 (2026-10-31 .. 2026-11-02): contracts, P01-P10 + P00, tests, batteries, PR #1/#2 merged to `main`, architecture map (since evicted to the kb).
- [x] Release plan Task 1: delete `rag-p04b`, keep `--strategy`, D10 overlap bounds (`cdfa6dc`, `e3041af`).
- [x] Task 2: dense/sparse/rerank backends as named plugins; D1, D5, D8 (`ab9c101`).
- [x] Task 3: `model_fetch` D4, D14, D17; aria2c only (`49d0f34`, `f2e0fe7`).
- [x] Task 4: D6, D7, D9, D11, D12, D13, D16 (`bd896da`).
- [x] Task 5: `verify_pipeline.py` + ps1/sh wrappers; D3, D15; `live` marker (`5a6e3b0`).
- [x] Task 6: merge `origin/main`, evict docs, CHANGELOG 0.2.0, plugin-seam docs, CI (`9f23a93`).
- [x] Live gate Wave A RUN #56-#59 (found D-A1); D-A1 fixed `4057648` RUN #60-#62.
- [x] Wave B RUN #63-#71 (p01-p07 incl. fastembed dense live); Wave C RUN #72-#74 (p08-p10); Wave D RUN #75-#79 (p00, pytest, batteries).
- [x] Final fix wave `6c08e23`..`bf6c445` (D-D1, D-B1, D-C1, rerank env keys, test hardening).
- [x] Real corpus added; `docs/continuity/` restored (`50c6467`); EXE001 fix (`62b0dc7`).

## In flight
- [ ] Final-fix-wave review.
- [ ] `verify_pipeline.ps1` re-run on adagio after D-D1 (replaces FAIL RUN #78).
- [ ] `verify_pipeline.sh` re-run under WSL Ubuntu-24.04 (replaces FAIL RUN #79).
- [ ] Real-corpus run (`docs/__test_data__/Obsidian...Transcript...md`) through p01..p10 + p00.
- [ ] kb-recorder: run ledger blocks + test-metrics entries for all runs, failed ones included.
- [ ] Fill CHANGELOG `Verification:` line with RUN numbers.

## Next
- [ ] Per-phase demo signoff by the user (`demo_phase.ps1 -p pNN`), appended to each ledger block (p01-p10 offered; p00 pending).
- [ ] Whole-branch review on opus (`198f343..HEAD`); fix findings in the same run.
- [ ] Close PR #3 (superseded).
- [ ] Copilot/Codex bot reviews on PR #4 addressed or declined with rule citation.
- [ ] Merge PR #4: 0.2.0 -> `development`.
- [ ] `release/1.0.0` -> `main` PR, merge, tag `v1.0.0`, fast-forward `development`.
- [ ] Remove worktree `phase-rag-cli-wt-feat` and merged branches (local + remote).
- [ ] Branch protection on `main` and `development`.
- [ ] Stop everything agents started (servers, browsers, demo windows); record leftovers in the hand-off.

## Backlog (after 1.0.0)
- [ ] `docker-compose.yml` for standalone Qdrant.
- [ ] `uv build` wheel + `uv tool install` check; PyPI packaging.
