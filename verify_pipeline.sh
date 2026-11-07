#!/usr/bin/env bash
# verify_pipeline.sh
# Complete Post-Implementation Review, Per-Phase Live Terminal Exercise, and Through-Test Battery.
# Twin of verify_pipeline.ps1 (same stages, phases, flags and assertions).
set -euo pipefail

BOLD="\033[1m"
CYAN="\033[1;36m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
RESET="\033[0m"

Usage() {
    cat <<'EOF'
Usage: ./verify_pipeline.sh [-q | --quiet] [-s | --skip-sync] [-h | --help]

Runs the comprehensive 4-stage verification battery:
  Stage 0: UV environment sync & AST static review (print audit + contract continuity + client.close())
  Stage 1: Live in-terminal step-by-step isolated phase tests (p01 through p10)
  Stage 2: Full 10-phase continuous pipe through-test battery (every stage exit checked)
  Stage 3: CRAG loopback: 0.92 stress run (schema) + default-threshold convergence assertion (p00)

  -q, --quiet       Do not echo each phase's captured stderr (shown anyway on failure)
  -s, --skip-sync   Skip 'uv sync --all-extras'
  -h, --help        Show this help and exit
EOF
}

QUIET=0
SKIP_SYNC=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -q|--quiet) QUIET=1 ;;
        -s|--skip-sync) SKIP_SYNC=1 ;;
        -h|--help) Usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; Usage >&2; exit 2 ;;
    esac
    shift
done

# Persist the whole battery transcript so evidence survives the session (twin of the .ps1 transcript).
mkdir -p artifacts
VERIFY_LOG="artifacts/verify_sh_$(date -u +%Y%m%dT%H%M%S).log"
exec > >(tee -a "$VERIFY_LOG") 2>&1
echo -e "-> Transcript: ${VERIFY_LOG}"

echo -e "${CYAN}================================================================================${RESET}"
echo -e "${BOLD} STAGE 0: UV ENVIRONMENT SYNC & POST-IMPLEMENTATION STATIC REVIEW${RESET}"
echo -e "${CYAN}================================================================================${RESET}"

if [[ "$SKIP_SYNC" -eq 0 ]]; then
    echo -e "${YELLOW}-> Synchronizing uv environment...${RESET}"
    uv sync --all-extras --quiet
fi

echo -e "${YELLOW}-> Running static AST and contract continuity review...${RESET}"
uv run python3 - <<'PYEOF'
import ast
import sys
from pathlib import Path
import rag_contracts as rc

scripts = [
    "rag_contracts.py", "hybrid_engine.py", "p00_crag_orchestrator.py",
    "p01_load.py", "p02_markdown.py", "p03_parse.py", "p04_chunk.py",
    "p05_index.py", "p06_query.py", "p07_retrieve.py", "p08_rerank.py",
    "p09_generate.py", "p10_evaluate.py", "chunkers.py"
]

# 1. AST & Bare print() stdout pollution check
for s in scripts:
    path = Path(s)
    assert path.exists(), f"Missing file: {s}"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=s)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            sys.exit(f"[AUDIT FAIL] Bare print() detected in {s}:{node.lineno} (corrupts stdout JSON pipe)")

# 2. Verify Type-Chain Continuity across Phases 01 -> 10
import p01_load, p02_markdown, p03_parse, p04_chunk, p05_index
import p06_query, p07_retrieve, p08_rerank, p09_generate, p10_evaluate

chain = [
    p01_load.cli_engine, p02_markdown.cli_engine, p03_parse.cli_engine,
    p04_chunk.cli_engine, p05_index.cli_engine, p06_query.cli_engine,
    p07_retrieve.cli_engine, p08_rerank.cli_engine, p09_generate.cli_engine,
    p10_evaluate.cli_engine
]

assert chain[0].input_model is None, "Phase 01 input_model must be None"
for i in range(len(chain) - 1):
    out_m = chain[i].output_model
    in_m = chain[i + 1].input_model
    assert out_m is in_m, f"Type mismatch between {chain[i].phase_title} ({out_m}) and {chain[i+1].phase_title} ({in_m})"

# 3. Check client.close() in p05 and p07
for s in ("p05_index.py", "p07_retrieve.py"):
    code = Path(s).read_text(encoding="utf-8")
    assert "client.close()" in code, f"Missing client.close() in {s}"

print("[STATIC REVIEW PASSED] 0 stdout print leaks | 10/10 Pydantic phase contracts strictly aligned.", file=sys.stderr)
PYEOF

# Clean previous test artifacts
rm -rf artifacts qdrant_storage
mkdir -p artifacts

echo -e "\n${CYAN}================================================================================${RESET}"
echo -e "${BOLD} STAGE 1: LIVE IN-TERMINAL STEP-BY-STEP EXERCISE (PHASES 01 -> 10 ISOLATED)${RESET}"
echo -e "${CYAN}================================================================================${RESET}"

# run_phase <label> <expected_exit> <stdout_file> <stderr_file> <command...>
# Captures stdout/stderr, echoes stderr unless --quiet, and fails with the stderr tail on an unexpected exit code.
run_phase() {
    local label="$1" expect="$2" out="$3" err="$4"
    shift 4
    local code=0
    "$@" < /dev/null > "$out" 2> "$err" || code=$?
    if [[ "$QUIET" -eq 0 ]]; then cat "$err" >&2; fi
    if [[ "$code" -ne "$expect" ]]; then
        echo -e "${RED}[FAIL] ${label}: exit=${code} (expected ${expect}). stderr tail:${RESET}" >&2
        tail -n 10 "$err" >&2
        exit 1
    fi
}

validate_triplex_artifact() {
    local phase_num="$1"
    local file_path="$2"
    local schema_name="$3"
    local stdout_capture="$4"

    if [[ ! -s "$file_path" ]]; then
        echo -e "${RED}[FAIL] Phase ${phase_num}: Persisted file ${file_path} is missing or empty!${RESET}" >&2
        exit 1
    fi

    uv run python3 - "$file_path" "$stdout_capture" "$schema_name" <<'PYEOF'
import sys
from pathlib import Path
import rag_contracts as rc

# utf-8-sig strips a leading U+FEFF, matching verify_pipeline.ps1
disk_json = Path(sys.argv[1]).read_text(encoding="utf-8-sig")
stdout_json = Path(sys.argv[2]).read_text(encoding="utf-8-sig")
schema_cls = getattr(rc, sys.argv[3])

# Validate both persisted disk artifact and streamed stdout payload against strict Pydantic contract
disk_obj = schema_cls.model_validate_json(disk_json)
stdout_obj = schema_cls.model_validate_json(stdout_json)
assert disk_obj.model_dump() == stdout_obj.model_dump(), "Disk JSON and stdout stream diverged!"
print(f"  [OK] Verified {sys.argv[3]} (run_id={disk_obj.run_id}) | Disk == Stdout Stream", file=sys.stderr)
PYEOF
}

# Phase 01: Loading
echo -e "${YELLOW}-> Exercising Phase 01 (rag-p01)...${RESET}"
run_phase "rag-p01" 0 artifacts/stdout_01.json artifacts/stderr_01.txt uv run rag-p01 --out-file artifacts/01_loaded.json
validate_triplex_artifact "01" "artifacts/01_loaded.json" "Phase01LoadedOutput" "artifacts/stdout_01.json"

# Phase 02: Pre-process to Markdown
echo -e "${YELLOW}-> Exercising Phase 02 (rag-p02)...${RESET}"
run_phase "rag-p02" 0 artifacts/stdout_02.json artifacts/stderr_02.txt uv run rag-p02 --in-file artifacts/01_loaded.json --out-file artifacts/02_markdown.json
validate_triplex_artifact "02" "artifacts/02_markdown.json" "Phase02MarkdownOutput" "artifacts/stdout_02.json"

# Phase 03: Structural AST Parsing
echo -e "${YELLOW}-> Exercising Phase 03 (rag-p03)...${RESET}"
run_phase "rag-p03" 0 artifacts/stdout_03.json artifacts/stderr_03.txt uv run rag-p03 --in-file artifacts/02_markdown.json --out-file artifacts/03_parsed.json
validate_triplex_artifact "03" "artifacts/03_parsed.json" "Phase03ParsedOutput" "artifacts/stdout_03.json"

# Phase 04: Semantic Chunking
echo -e "${YELLOW}-> Exercising Phase 04 (rag-p04)...${RESET}"
run_phase "rag-p04" 0 artifacts/stdout_04.json artifacts/stderr_04.txt uv run rag-p04 --in-file artifacts/03_parsed.json --out-file artifacts/04_chunked.json --max-words 50 --overlap 10
validate_triplex_artifact "04" "artifacts/04_chunked.json" "Phase04ChunkedOutput" "artifacts/stdout_04.json"

# Phase 04 (recursive strategy): separate artifact so the canonical 04_chunked.json stays untouched
echo -e "${YELLOW}-> Exercising Phase 04 --strategy recursive...${RESET}"
run_phase "rag-p04 --strategy recursive" 0 artifacts/stdout_04_recursive.json artifacts/stderr_04_recursive.txt uv run rag-p04 --in-file artifacts/03_parsed.json --out-file artifacts/04_chunked_recursive.json --strategy recursive
validate_triplex_artifact "04-recursive" "artifacts/04_chunked_recursive.json" "Phase04ChunkedOutput" "artifacts/stdout_04_recursive.json"

# Phase 04 negative: unknown strategy must exit 2 with the known names on stderr and empty stdout
echo -e "${YELLOW}-> Negative test: rag-p04 --strategy nope (PASS = exit 2 + 'Known:')...${RESET}"
run_phase "NEG rag-p04 --strategy nope" 2 artifacts/stdout_neg.json artifacts/stderr_neg.txt uv run rag-p04 --strategy nope --in-file artifacts/03_parsed.json --out-file artifacts/_neg.json
if ! grep -q "Known:" artifacts/stderr_neg.txt || [[ -s artifacts/stdout_neg.json ]]; then
    echo -e "${RED}[FAIL] Negative strategy test: 'Known:' missing from stderr or stdout not empty${RESET}" >&2
    exit 1
fi
echo -e "  ${GREEN}[OK] Negative strategy test: exit 2, stderr lists known strategies, stdout empty${RESET}"

# Phase 05: Live Jina-v3 + SPLADE Hybrid Qdrant Indexing
echo -e "${YELLOW}-> Exercising Phase 05 (rag-p05: Jina-v3 + SPLADE + Qdrant Upsert)...${RESET}"
run_phase "rag-p05" 0 artifacts/stdout_05.json artifacts/stderr_05.txt uv run rag-p05 --in-file artifacts/04_chunked.json --out-file artifacts/05_indexed.json --collection "test_hybrid_qdrant" --qdrant-path "./qdrant_storage"
validate_triplex_artifact "05" "artifacts/05_indexed.json" "Phase05IndexedOutput" "artifacts/stdout_05.json"

# Phase 06: Query Orchestration
echo -e "${YELLOW}-> Exercising Phase 06 (rag-p06)...${RESET}"
run_phase "rag-p06" 0 artifacts/stdout_06.json artifacts/stderr_06.txt uv run rag-p06 --in-file artifacts/05_indexed.json --out-file artifacts/06_query_plan.json --query "How does Hybrid RAG fuse dense and sparse vectors and when does CRAG rewrite?"
validate_triplex_artifact "06" "artifacts/06_query_plan.json" "Phase06QueryPlanOutput" "artifacts/stdout_06.json"

# Phase 07: Live Qdrant Hybrid Prefetch + RRF Retrieval
echo -e "${YELLOW}-> Exercising Phase 07 (rag-p07: Qdrant Multi-Prefetch + RRF)...${RESET}"
run_phase "rag-p07" 0 artifacts/stdout_07.json artifacts/stderr_07.txt uv run rag-p07 --in-file artifacts/06_query_plan.json --out-file artifacts/07_retrieved.json --qdrant-path "./qdrant_storage" --rrf-k 60 --top-k 6
validate_triplex_artifact "07" "artifacts/07_retrieved.json" "Phase07RetrievedOutput" "artifacts/stdout_07.json"

# Phase 08: Live Cross-Encoder Reranking & XML Context Assembly
echo -e "${YELLOW}-> Exercising Phase 08 (rag-p08: Live Cross-Encoder + XML Context)...${RESET}"
run_phase "rag-p08" 0 artifacts/stdout_08.json artifacts/stderr_08.txt uv run rag-p08 --in-file artifacts/07_retrieved.json --out-file artifacts/08_reranked.json --backend fastembed --model "jinaai/jina-reranker-v2-base-multilingual" --top-n 4
validate_triplex_artifact "08" "artifacts/08_reranked.json" "Phase08RerankedOutput" "artifacts/stdout_08.json"

# Phase 09: CRAG Verification & Grounded Generation
echo -e "${YELLOW}-> Exercising Phase 09 (rag-p09)...${RESET}"
run_phase "rag-p09" 0 artifacts/stdout_09.json artifacts/stderr_09.txt uv run rag-p09 --in-file artifacts/08_reranked.json --out-file artifacts/09_generated.json --crag-threshold 0.55
validate_triplex_artifact "09" "artifacts/09_generated.json" "Phase09GenerationOutput" "artifacts/stdout_09.json"

# Phase 10: RAG Triad Evaluation
echo -e "${YELLOW}-> Exercising Phase 10 (rag-p10)...${RESET}"
run_phase "rag-p10" 0 artifacts/stdout_10.json artifacts/stderr_10.txt uv run rag-p10 --in-file artifacts/09_generated.json --out-file artifacts/10_evaluated.json
validate_triplex_artifact "10" "artifacts/10_evaluated.json" "Phase10EvalOutput" "artifacts/stdout_10.json"

echo -e "\n${CYAN}================================================================================${RESET}"
echo -e "${BOLD} STAGE 2: FULL 10-PHASE ZERO-COPY UNIX PIPE THROUGH-TEST BATTERY${RESET}"
echo -e "${CYAN}================================================================================${RESET}"

# Every stage's stderr goes to its own file; every stage's exit code is checked via PIPESTATUS.
set +e
uv run rag-p01 2> artifacts/stderr_pipe_01.txt < /dev/null \
  | uv run rag-p02 2> artifacts/stderr_pipe_02.txt \
  | uv run rag-p03 2> artifacts/stderr_pipe_03.txt \
  | uv run rag-p04 --max-words 50 --overlap 10 2> artifacts/stderr_pipe_04.txt \
  | uv run rag-p05 --collection "pipe_hybrid_qdrant" --qdrant-path "./qdrant_storage" 2> artifacts/stderr_pipe_05.txt \
  | uv run rag-p06 --query "How does Qdrant fuse Jina-v3 dense and SPLADE sparse vectors?" 2> artifacts/stderr_pipe_06.txt \
  | uv run rag-p07 --qdrant-path "./qdrant_storage" --rrf-k 60 --top-k 5 2> artifacts/stderr_pipe_07.txt \
  | uv run rag-p08 --backend fastembed --model "jinaai/jina-reranker-v2-base-multilingual" --top-n 3 2> artifacts/stderr_pipe_08.txt \
  | uv run rag-p09 --crag-threshold 0.50 2> artifacts/stderr_pipe_09.txt \
  | uv run rag-p10 2> artifacts/stderr_pipe_10.txt > artifacts/pipe_final_stdout.json
pipe_codes=("${PIPESTATUS[@]}")
set -e

pipe_failed=0
for i in "${!pipe_codes[@]}"; do
    stage=$(printf "%02d" $((i + 1)))
    if [[ "$QUIET" -eq 0 ]]; then cat "artifacts/stderr_pipe_${stage}.txt" >&2; fi
    if [[ "${pipe_codes[$i]}" -ne 0 ]]; then
        echo -e "${RED}[FAIL] Pipe stage rag-p${stage}: exit=${pipe_codes[$i]}. stderr tail:${RESET}" >&2
        tail -n 10 "artifacts/stderr_pipe_${stage}.txt" >&2
        pipe_failed=1
    fi
done
if [[ "$pipe_failed" -ne 0 ]]; then exit 1; fi
echo -e "  ${GREEN}[OK] All 10 pipe stages exited 0 (${pipe_codes[*]})${RESET}"

validate_triplex_artifact "PIPE_E2E" "artifacts/10_evaluated.json" "Phase10EvalOutput" "artifacts/pipe_final_stdout.json"

echo -e "\n${CYAN}================================================================================${RESET}"
echo -e "${BOLD} STAGE 3: AUTONOMOUS CRAG LOOPBACK & QUERY-REWRITE CONVERGENCE BATTERY${RESET}"
echo -e "${CYAN}================================================================================${RESET}"

# 3a. Stress: high threshold (0.92) + vague query exercises the multi-attempt rewrite loop (schema-only assertion)
echo -e "${YELLOW}-> Exercising rag-p00 stress run (--crag-threshold 0.92, schema only)...${RESET}"
run_phase "rag-p00 stress" 0 artifacts/stdout_00_loop.json artifacts/stderr_00_loop.txt uv run rag-p00 \
  --in-file artifacts/05_indexed.json \
  --out-file artifacts/00_crag_loop_summary.json \
  --query "How are things combined and retried?" \
  --qdrant-path "./qdrant_storage" \
  --rerank-backend fastembed \
  --rerank-model "jinaai/jina-reranker-v2-base-multilingual" \
  --crag-threshold 0.92 \
  --max-retries 2 \
  --quiet-children
validate_triplex_artifact "00_CRAG_LOOP" "artifacts/00_crag_loop_summary.json" "PhaseCRAGLoopOutput" "artifacts/stdout_00_loop.json"

# 3b. Convergence: all rag-p00 defaults (query, sentence_transformers bge-reranker-v2-m3, -t 0.65, -r 2) must end GROUNDED
#     with converged == true. -i is explicit only so p00 never falls back to reading stdin.
echo -e "${YELLOW}-> Exercising rag-p00 convergence run (defaults, must converge GROUNDED)...${RESET}"
run_phase "rag-p00 default" 0 artifacts/stdout_00_default.json artifacts/stderr_00_default.txt uv run rag-p00 -c -s \
  -i artifacts/05_indexed.json \
  -o artifacts/00_crag_default.json
validate_triplex_artifact "00_CRAG_DEFAULT" "artifacts/00_crag_default.json" "PhaseCRAGLoopOutput" "artifacts/stdout_00_default.json"
uv run python3 - artifacts/00_crag_default.json <<'PYEOF'
import sys
from pathlib import Path
import rag_contracts as rc

out = rc.PhaseCRAGLoopOutput.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
trail = " -> ".join(f"{a.grounded_confidence:.4f}" for a in out.attempts_history)
verdict = out.final_generation.crag_verdict
if not (out.converged and verdict == "GROUNDED"):
    sys.exit(f"[FAIL] CRAG default-threshold run did not converge: converged={out.converged} verdict={verdict} confidence {trail}")
print(f"  [OK] CRAG converged GROUNDED in {out.total_attempts} attempt(s) | confidence {trail}", file=sys.stderr)
PYEOF

echo -e "\n${GREEN}================================================================================${RESET}"
echo -e "${GREEN} ALL STATIC REVIEWS, 10 ISOLATED PHASE TESTS, UNIX PIPE, & CRAG LOOP PASSED!${RESET}"
echo -e "${GREEN}================================================================================${RESET}"
