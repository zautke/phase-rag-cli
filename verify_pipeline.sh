#!/usr/bin/env bash
# verify_pipeline.sh
# Complete Post-Implementation Review, Per-Phase Live Terminal Exercise, and Through-Test Battery
set -euo pipefail

BOLD="\033[1m"
CYAN="\033[1;36m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
RESET="\033[0m"

echo -e "${CYAN}================================================================================${RESET}"
echo -e "${BOLD} STAGE 0: UV ENVIRONMENT SYNC & POST-IMPLEMENTATION STATIC REVIEW${RESET}"
echo -e "${CYAN}================================================================================${RESET}"

uv sync --all-extras --quiet

uv run python3 - <<'PYEOF'
import ast
import sys
from pathlib import Path
import rag_contracts as rc

scripts = [
    "rag_contracts.py", "hybrid_engine.py", "p00_crag_orchestrator.py",
    "p01_load.py", "p02_markdown.py", "p03_parse.py", "p04_chunk.py",
    "p05_index.py", "p06_query.py", "p07_retrieve.py", "p08_rerank.py",
    "p09_generate.py", "p10_evaluate.py", "chunkers.py", "p04b_graph.py"
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
import p01_load, p02_markdown, p03_parse, p04_chunk, p04b_graph, p05_index
import p06_query, p07_retrieve, p08_rerank, p09_generate, p10_evaluate

chain = [
    p01_load.cli_engine, p02_markdown.cli_engine, p03_parse.cli_engine,
    p04_chunk.cli_engine, p04b_graph.cli_engine, p05_index.cli_engine, p06_query.cli_engine,
    p07_retrieve.cli_engine, p08_rerank.cli_engine, p09_generate.cli_engine,
    p10_evaluate.cli_engine
]

assert chain[0].input_model is None, "Phase 01 input_model must be None"
for i in range(len(chain) - 1):
    out_m = chain[i].output_model
    in_m = chain[i + 1].input_model
    assert out_m is in_m, f"Type mismatch between {chain[i].phase_title} ({out_m}) and {chain[i+1].phase_title} ({in_m})"

print("[STATIC REVIEW PASSED] 0 stdout print leaks | 10/10 Pydantic phase contracts strictly aligned.", file=sys.stderr)
PYEOF

# Clean previous test artifacts
rm -rf artifacts qdrant_storage
mkdir -p artifacts

echo -e "\n${CYAN}================================================================================${RESET}"
echo -e "${BOLD} STAGE 1: LIVE IN-TERMINAL STEP-BY-STEP EXERCISE (PHASES 01 -> 10 ISOLATED)${RESET}"
echo -e "${CYAN}================================================================================${RESET}"

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

disk_json = Path(sys.argv[1]).read_text(encoding="utf-8")
stdout_json = Path(sys.argv[2]).read_text(encoding="utf-8")
schema_cls = getattr(rc, sys.argv[3])

# Validate both persisted disk artifact and streamed stdout payload against strict Pydantic contract
disk_obj = schema_cls.model_validate_json(disk_json)
stdout_obj = schema_cls.model_validate_json(stdout_json)
assert disk_obj.model_dump() == stdout_obj.model_dump(), "Disk JSON and stdout stream diverged!"
print(f"  ✓ Verified {sys.argv[3]} (run_id={disk_obj.run_id}) | Disk == Stdout Stream", file=sys.stderr)
PYEOF
}

# Phase 01: Loading
echo -e "${YELLOW}-> Exercising Phase 01 (rag-p01)...${RESET}"
uv run rag-p01 --out-file artifacts/01_loaded.json > artifacts/stdout_01.json
validate_triplex_artifact "01" "artifacts/01_loaded.json" "Phase01LoadedOutput" "artifacts/stdout_01.json"

# Phase 02: Pre-process to Markdown
echo -e "${YELLOW}-> Exercising Phase 02 (rag-p02)...${RESET}"
uv run rag-p02 --in-file artifacts/01_loaded.json --out-file artifacts/02_markdown.json > artifacts/stdout_02.json
validate_triplex_artifact "02" "artifacts/02_markdown.json" "Phase02MarkdownOutput" "artifacts/stdout_02.json"

# Phase 03: Structural AST Parsing
echo -e "${YELLOW}-> Exercising Phase 03 (rag-p03)...${RESET}"
uv run rag-p03 --in-file artifacts/02_markdown.json --out-file artifacts/03_parsed.json > artifacts/stdout_03.json
validate_triplex_artifact "03" "artifacts/03_parsed.json" "Phase03ParsedOutput" "artifacts/stdout_03.json"

# Phase 04: Semantic Chunking
echo -e "${YELLOW}-> Exercising Phase 04 (rag-p04)...${RESET}"
uv run rag-p04 --in-file artifacts/03_parsed.json --out-file artifacts/04_chunked.json --max-words 50 --overlap 10 > artifacts/stdout_04.json
validate_triplex_artifact "04" "artifacts/04_chunked.json" "Phase04ChunkedOutput" "artifacts/stdout_04.json"

# Phase 04 (recursive strategy): separate artifact so the canonical 04_chunked.json stays untouched
echo -e "${YELLOW}-> Exercising Phase 04 --strategy recursive...${RESET}"
uv run rag-p04 --in-file artifacts/03_parsed.json --out-file artifacts/04_chunked_recursive.json --strategy recursive > artifacts/stdout_04_recursive.json 2> artifacts/stderr_04_recursive.txt
validate_triplex_artifact "04-recursive" "artifacts/04_chunked_recursive.json" "Phase04ChunkedOutput" "artifacts/stdout_04_recursive.json"

# Phase 04b: pass-through graph stage (stdout == its Phase 04 input)
echo -e "${YELLOW}-> Exercising Phase 04b (rag-p04b: entity graph side-artifact)...${RESET}"
uv run rag-p04b --in-file artifacts/04_chunked.json --out-file artifacts/04b_passthrough.json --graph-file artifacts/04b_graph.json > artifacts/stdout_04b.json 2> artifacts/stderr_04b.txt
validate_triplex_artifact "04b" "artifacts/04b_passthrough.json" "Phase04ChunkedOutput" "artifacts/stdout_04b.json"
validate_triplex_artifact "04b-graph" "artifacts/04b_graph.json" "GraphArtifact" "artifacts/04b_graph.json"

# Phase 04 negative: unknown strategy must exit 2 with the known names on stderr and empty stdout
echo -e "${YELLOW}-> Negative test: rag-p04 --strategy nope (PASS = exit 2 + 'Known:')...${RESET}"
neg_code=0
uv run rag-p04 --strategy nope --in-file artifacts/03_parsed.json --out-file artifacts/_neg.json > artifacts/stdout_neg.json 2> artifacts/stderr_neg.txt || neg_code=$?
if [[ "$neg_code" -ne 2 ]] || ! grep -q "Known:" artifacts/stderr_neg.txt || [[ -s artifacts/stdout_neg.json ]]; then
    echo -e "${RED}[FAIL] Negative strategy test: exit=${neg_code}${RESET}" >&2
    exit 1
fi
echo -e "  ${GREEN}[OK] Negative strategy test: exit 2, stderr lists known strategies, stdout empty${RESET}"

# Phase 05: Live Jina-v3 + SPLADE Hybrid Qdrant Indexing
echo -e "${YELLOW}-> Exercising Phase 05 (rag-p05: Jina-v3 + SPLADE + Qdrant Upsert)...${RESET}"
uv run rag-p05 --in-file artifacts/04_chunked.json --out-file artifacts/05_indexed.json --collection "test_hybrid_qdrant" --qdrant-path "./qdrant_storage" > artifacts/stdout_05.json
validate_triplex_artifact "05" "artifacts/05_indexed.json" "Phase05IndexedOutput" "artifacts/stdout_05.json"

# Phase 06: Query Orchestration
echo -e "${YELLOW}-> Exercising Phase 06 (rag-p06)...${RESET}"
uv run rag-p06 --in-file artifacts/05_indexed.json --out-file artifacts/06_query_plan.json --query "How does Hybrid RAG fuse dense and sparse vectors and when does CRAG rewrite?" > artifacts/stdout_06.json
validate_triplex_artifact "06" "artifacts/06_query_plan.json" "Phase06QueryPlanOutput" "artifacts/stdout_06.json"

# Phase 07: Live Qdrant Hybrid Prefetch + RRF Retrieval
echo -e "${YELLOW}-> Exercising Phase 07 (rag-p07: Qdrant Multi-Prefetch + RRF)...${RESET}"
uv run rag-p07 --in-file artifacts/06_query_plan.json --out-file artifacts/07_retrieved.json --qdrant-path "./qdrant_storage" --rrf-k 60 --top-k 6 > artifacts/stdout_07.json
validate_triplex_artifact "07" "artifacts/07_retrieved.json" "Phase07RetrievedOutput" "artifacts/stdout_07.json"

# Phase 08: Live Cross-Encoder Reranking & XML Context Assembly
echo -e "${YELLOW}-> Exercising Phase 08 (rag-p08: Live Cross-Encoder + XML Context)...${RESET}"
uv run rag-p08 --in-file artifacts/07_retrieved.json --out-file artifacts/08_reranked.json --backend fastembed --model "jinaai/jina-reranker-v2-base-multilingual" --top-n 4 > artifacts/stdout_08.json
validate_triplex_artifact "08" "artifacts/08_reranked.json" "Phase08RerankedOutput" "artifacts/stdout_08.json"

# Phase 09: CRAG Verification & Grounded Generation
echo -e "${YELLOW}-> Exercising Phase 09 (rag-p09)...${RESET}"
uv run rag-p09 --in-file artifacts/08_reranked.json --out-file artifacts/09_generated.json --crag-threshold 0.55 > artifacts/stdout_09.json
validate_triplex_artifact "09" "artifacts/09_generated.json" "Phase09GenerationOutput" "artifacts/stdout_09.json"

# Phase 10: RAG Triad Evaluation
echo -e "${YELLOW}-> Exercising Phase 10 (rag-p10)...${RESET}"
uv run rag-p10 --in-file artifacts/09_generated.json --out-file artifacts/10_evaluated.json > artifacts/stdout_10.json
validate_triplex_artifact "10" "artifacts/10_evaluated.json" "Phase10EvalOutput" "artifacts/stdout_10.json"

echo -e "\n${CYAN}================================================================================${RESET}"
echo -e "${BOLD} STAGE 2: FULL 10-PHASE ZERO-COPY UNIX PIPE THROUGH-TEST BATTERY${RESET}"
echo -e "${CYAN}================================================================================${RESET}"

uv run rag-p01 \
  | uv run rag-p02 \
  | uv run rag-p03 \
  | uv run rag-p04 --max-words 50 --overlap 10 \
  | uv run rag-p05 --collection "pipe_hybrid_qdrant" --qdrant-path "./qdrant_storage" \
  | uv run rag-p06 --query "How does Qdrant fuse Jina-v3 dense and SPLADE sparse vectors?" \
  | uv run rag-p07 --qdrant-path "./qdrant_storage" --rrf-k 60 --top-k 5 \
  | uv run rag-p08 --backend fastembed --model "jinaai/jina-reranker-v2-base-multilingual" --top-n 3 \
  | uv run rag-p09 --crag-threshold 0.50 \
  | uv run rag-p10 > artifacts/pipe_final_stdout.json

validate_triplex_artifact "PIPE_E2E" "artifacts/10_evaluated.json" "Phase10EvalOutput" "artifacts/pipe_final_stdout.json"

echo -e "\n${CYAN}================================================================================${RESET}"
echo -e "${BOLD} STAGE 3: AUTONOMOUS CRAG LOOPBACK & QUERY-REWRITE CONVERGENCE BATTERY${RESET}"
echo -e "${CYAN}================================================================================${RESET}"

# Force a high threshold (0.99) or vague query to exercise the multi-attempt CRAG rewrite loop
uv run rag-p00 \
  --in-file artifacts/05_indexed.json \
  --out-file artifacts/00_crag_loop_summary.json \
  --query "How are things combined and retried?" \
  --qdrant-path "./qdrant_storage" \
  --rerank-backend fastembed \
  --rerank-model "jinaai/jina-reranker-v2-base-multilingual" \
  --crag-threshold 0.92 \
  --max-retries 2 \
  --quiet-children > artifacts/stdout_00_loop.json

validate_triplex_artifact "00_CRAG_LOOP" "artifacts/00_crag_loop_summary.json" "PhaseCRAGLoopOutput" "artifacts/stdout_00_loop.json"

echo -e "\n${GREEN}================================================================================${RESET}"
echo -e "${GREEN} ALL STATIC REVIEWS, 10 ISOLATED PHASE TESTS, UNIX PIPE, & CRAG LOOP PASSED!${RESET}"
echo -e "${GREEN}================================================================================${RESET}"
