# CURRENT TASK STATE

## Status as of 2026-11-10 (handoff) — branch `feat/minimal-pluggability` @ a134d95 — READ `HANDOFF_NEXT_SESSION.md` FIRST

- HEAD `a134d95` (pushed): D-E1 batched encoding + D-E3 answer evidence/faithfulness, recovered from a usage-cap-killed fix agent; 136 non-live tests pass, ruff clean (RUN #131). **Live-unverified** — PRE-VERIFY 2 is the next gate.
- Demo attempt 1 (RUN #125) failed on demo-script bugs (fixed + reviewed); PRE-VERIFY 1 (RUN #126–#130) failed at p05 `MemoryError 7.80 GiB` = D-E1. The user has NOT yet seen a clean run; nothing is signed off.
- New non-negotiables (kb protocol + memory): input-scaling review check in every reviewer brief; gates on the real corpus with N + peak RSS; pre-verify the exact demo script non-interactively before any console demo; errors/unexpected short-circuit the demo.
- Open defect D-E2 (p04 parent_markdown ×12.9 bloat) scheduled as Task 8 after the demo signoff.
- The sections below describe the state at 2026-11-07 15:46 and remain accurate for everything before `62b0dc7`.

## Status as of 2026-11-07 15:46 MST — branch `feat/minimal-pluggability` @ 62b0dc7 (release 0.2.0 fix wave, live gate in progress)

- **Worktree / branch:** `C:\Users\me\dev\phase-rag-cli-wt-feat`, branch `feat/minimal-pluggability`, HEAD `62b0dc7` (`fix(ci): set executable bit on shebang scripts (ruff EXE001)`), on top of `50c6467` (test corpus + continuity restored). Base of the plan: `198f343`. The main checkout `C:\Users\me\dev\phase-rag-cli` belongs to concurrent Codex CLI sessions: do not touch it.
- **PRs:** #4 (`feat/minimal-pluggability` -> `development`) OPEN. #5 (`fix/battery-hardening`) shows MERGED on GitHub; its content was fast-forwarded into this branch at `198f343`, so it is folded. #3 (`docs/plugin-evolution-audit-plan`) OPEN, pending close (its docs were evicted to the kb; it is superseded).
- **Release target:** 0.2.0 into `development` (MINOR+1, three numbers), then 1.0.0 into `main` (MAJOR+1, three numbers). No fourth number, no suffix.

### DONE
- **Plan Tasks 1-6** (SDD ledger `.superpowers/sdd/release-1.0.0/progress.md`, every task review-clean):
  - T1 `cdfa6dc`, `e3041af`: `rag-p04b` deleted, `--strategy` registry kept, D10 `--overlap` bounds.
  - T2 `ab9c101`: dense/sparse/rerank backends are named plugins (default dense `sentence_transformers`, `fastembed` selectable), D1, D5, D8.
  - T3 `49d0f34`, `f2e0fe7`: `model_fetch` hardening D4, D14, D17 (aria2c only, no fallback).
  - T4 `c61659c`..`bd896da`: D6, D7, D9, D11, D12, D13, D16 (one fix round).
  - T5 `09342ca`..`5a6e3b0`: one `verify_pipeline.py` core + `.ps1`/`.sh` wrappers, `live` pytest marker (one fix round).
  - T6 `db6b7d2`..`9f23a93`: merge `origin/main`, evict non-product docs, `CHANGELOG.md` 0.2.0, plugin-seam docs, CI (`setup-uv@v10.3.3`) (two fix rounds).
- **Live gate (Task 7), all via live-qa agents, evidence under `C:\Users\me\dev\phase-rag-cli-run-evidence\RUN-<n>\`:**
  - Wave A @414d66e, RUN #56-#59: p01-p04 PASS, negatives 2/2; found D-A1 (stdout bytes != artifact, CRLF).
  - D-A1 fixed `4057648` (RUN #60-#62, 113 passed, review approved).
  - Wave B @4057648, RUN #63-#71: all PASS (p01-p04 byte-identical re-run; p05 ST 101.5 s; p05 fastembed first live PASS 161.2 s, 2.29 GB jina ONNX via aria2c; p06; p07 ST 32.9 s; p07 fastembed 13.4 s). Negatives 3/3. M05 738 ms HIGH band. RAM low-water 2.8 MB during ONNX load.
  - Wave C @4057648, RUN #72-#74: p08 ST 26.3 s + fastembed 67.3 s (1131 MB aria2c); p09 REWRITE_REQUIRED 0.6277; p10 nDCG 1.0. Negative 1/1.
  - Wave D @4057648: p00 default PASS RUN #75 (109.9 s, converged attempt 2); p00 stress PARTIAL RUN #76 (0.92 converges at attempt 3 = 0.9613, 0.99 stays REWRITE_REQUIRED x3); `pytest -m ""` PASS RUN #77 (115 passed, 236 s); `verify_pipeline.ps1` FAIL RUN #78 (Stage 3 D-D1 only); `verify_pipeline.sh` under WSL Ubuntu-24.04 FAIL RUN #79 (same, 1331 s, CPU torch venv 1.3 GB).
- **Final fix wave** (all landed, `6c08e23`..`bf6c445`): D-D1 stress threshold 0.99 + rewrite-proven assertion; D-B1 `get_embedding_dimension`; D-C1 p09 skips headings/unpunctuated bullets; `RAG_RERANK_BACKEND`/`RAG_RERANK_MODEL` env keys on p08; byte-identical pipeline-copy tests; p00 payload byte assertion; script-path p01.
- `50c6467`: real corpus `docs/__test_data__/Obsidian, Basic Memory ERO, and GraphRAG - Verbatim Session Transcript - 2026-10-13.md` added; `docs/continuity/` restored (SessionStart hook reads it). `62b0dc7`: executable bit on shebang scripts for ruff EXE001 (local, pushed with this sync commit).

### IN FLIGHT (agents may still be running: check with ListAgents before assuming)
- Final-fix-wave review (reviewer on the `6c08e23..bf6c445` diff).
- Re-runs of the battery after the D-D1 fix: `verify_pipeline.ps1` on adagio and `verify_pipeline.sh` under WSL (replace FAIL #78/#79).
- Real-corpus run (`live-realdoc`, sonnet/high) on the Obsidian transcript through all phases ("bet it fails in phase 0").
- kb recording by `kb-recorder` (sonnet) of the run ledger blocks and test-metrics.
- CHANGELOG `Verification:` line still reads `<filled after Task 7>`: fill with the run numbers once the re-runs pass.

### NEXT (in order)
1. Per-phase demo signoff by the user: `READY TO DEMO` was sent for p01-p07 and p08-p10; p00 pending. Signoff is appended to each phase's ledger block (`Signoff: user, <timestamp>`).
2. Whole-branch review on opus (all of `198f343..HEAD`).
3. Close PR #3 (superseded by the kb eviction).
4. Copilot/Codex bot reviews on PR #4: check each finding against the repo rules before touching code; decline context-free ones with a one-line reply naming the rule.
5. Merge PR #4: 0.2.0 -> `development` (CHANGELOG entry already in the branch; `package`/pyproject version three numbers).
6. Open `release/1.0.0` -> `main` by PR (MAJOR+1, MINOR/PATCH 0, no CHANGELOG entry on promotion), merge, tag `v1.0.0` (keep the repo tag convention), fast-forward `development` to `main`.
7. Cleanup: remove worktree `phase-rag-cli-wt-feat` and the merged feature branches (local + remote); set branch protection on `main` and `development`.

### Resume commands (PowerShell tool only; bash is banned on adagio)
- `Set-Location C:\Users\me\dev\phase-rag-cli-wt-feat; git status -sb; git log --oneline 198f343..HEAD`
- SDD ledger (authoritative: tasks, Rulings, wave results): `Get-Content .superpowers\sdd\release-1.0.0\progress.md`; plan: `.superpowers\sdd\release-1.0.0\plan.md`.
- Run ledger (kb file): `C:\Users\me\master-kb\projects\phase-rag-cli\phase-rag-cli Run Ledger (append-only).md` (read the tail for the next RUN number; last known #79 plus fix-wave and real-doc runs).
- Demo a phase (visible pwsh window on the right half): `C:\Users\me\dev\phase-rag-cli-run-evidence\demo\demo_phase.ps1 -p pNN` (p01..p10, p00).
- Tests: `uv run pytest -q` (non-live, seconds); `uv run pytest -q -m ""` (all, ~4 min, needs RAM). Battery: `.\verify_pipeline.ps1`; Linux proof: `wsl -d Ubuntu-24.04 --exec bash -lc "cd /mnt/c/Users/me/dev/phase-rag-cli-wt-feat && UV_PROJECT_ENVIRONMENT=/home/luke/.venvs/phase-rag-cli ./verify_pipeline.sh"`.
