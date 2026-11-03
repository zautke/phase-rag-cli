#!/usr/bin/env pwsh
# verify_pipeline.ps1
# Complete Post-Implementation Review, Per-Phase Live Terminal Exercise, and Through-Test Battery for Windows (PowerShell)

[CmdletBinding()]
param(
    [Alias("q")][switch]$Quiet,
    [Alias("s")][switch]$SkipSync,
    [Alias("h")][switch]$Help
)

$ErrorActionPreference = "Stop"

function Usage {
    @"
Usage: ./verify_pipeline.ps1 [-Quiet / -q] [-SkipSync / -s] [-Help / -h]

Runs the comprehensive 4-stage verification battery:
  Stage 0: UV environment sync & AST static review (print audit + contract continuity)
  Stage 1: Live in-terminal step-by-step isolated phase tests (p01 through p10)
  Stage 2: Full 10-phase continuous pipe through-test battery
  Stage 3: Autonomous CRAG loopback query-rewrite convergence test (p00)
"@
}

if ($Help) {
    Usage
    exit 0
}

# Ensure UTF-8 (No BOM) output encoding across PowerShell streams
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8NoBom
[Console]::InputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host " STAGE 0: UV ENVIRONMENT SYNC & POST-IMPLEMENTATION STATIC REVIEW" -ForegroundColor White
Write-Host "================================================================================" -ForegroundColor Cyan

if (-not $SkipSync) {
    Write-Host "-> Synchronizing uv environment..." -ForegroundColor Yellow
    uv sync --all-extras --quiet
}

Write-Host "-> Running static AST and contract continuity review..." -ForegroundColor Yellow
$staticReviewCode = @"
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

# 3. Check client.close() in p05 and p07
for s in ("p05_index.py", "p07_retrieve.py"):
    code = Path(s).read_text(encoding="utf-8")
    assert "client.close()" in code, f"Missing client.close() in {s}"

print("[STATIC REVIEW PASSED] 0 stdout print leaks | 10/10 Pydantic phase contracts strictly aligned.", file=sys.stderr)
"@

$staticReviewCode | uv run python -

if ($LASTEXITCODE -ne 0) {
    Write-Error "Static review failed."
    exit 1
}

# Clean previous test artifacts
if (Test-Path artifacts) { Remove-Item -Recurse -Force artifacts }
if (Test-Path qdrant_storage) { Remove-Item -Recurse -Force qdrant_storage }
New-Item -ItemType Directory -Path artifacts -Force | Out-Null

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host " STAGE 1: LIVE IN-TERMINAL STEP-BY-STEP EXERCISE (PHASES 01 -> 10 ISOLATED)" -ForegroundColor White
Write-Host "================================================================================" -ForegroundColor Cyan

function Validate-TriplexArtifact {
    param(
        [string]$PhaseNum,
        [string]$FilePath,
        [string]$SchemaName,
        [string]$StdoutCapture
    )

    if (-not (Test-Path $FilePath) -or (Get-Item $FilePath).Length -eq 0) {
        Write-Host "[FAIL] Phase $PhaseNum`: Persisted file $FilePath is missing or empty!" -ForegroundColor Red
        exit 1
    }

    $verifyCode = @"
import sys
from pathlib import Path
import rag_contracts as rc

disk_json = Path(sys.argv[1]).read_text(encoding='utf-8-sig')
stdout_json = Path(sys.argv[2]).read_text(encoding='utf-8-sig')
schema_cls = getattr(rc, sys.argv[3])

disk_obj = schema_cls.model_validate_json(disk_json)
stdout_obj = schema_cls.model_validate_json(stdout_json)
assert disk_obj.model_dump() == stdout_obj.model_dump(), 'Disk JSON and stdout stream diverged!'
print(f'  [OK] Verified {sys.argv[3]} (run_id={disk_obj.run_id}) | Disk == Stdout Stream', file=sys.stderr)
"@

    $verifyCode | uv run python - $FilePath $StdoutCapture $SchemaName
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] Validation failed for Phase $PhaseNum" -ForegroundColor Red
        exit 1
    }
}

# Phase 01: Loading
Write-Host "-> Exercising Phase 01 (rag-p01)..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p01 --out-file artifacts/01_loaded.json" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_01.json"
$proc.WaitForExit()
Validate-TriplexArtifact "01" "artifacts/01_loaded.json" "Phase01LoadedOutput" "artifacts/stdout_01.json"

# Phase 02: Pre-process to Markdown
Write-Host "-> Exercising Phase 02 (rag-p02)..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p02 --in-file artifacts/01_loaded.json --out-file artifacts/02_markdown.json" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_02.json"
$proc.WaitForExit()
Validate-TriplexArtifact "02" "artifacts/02_markdown.json" "Phase02MarkdownOutput" "artifacts/stdout_02.json"

# Phase 03: Structural AST Parsing
Write-Host "-> Exercising Phase 03 (rag-p03)..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p03 --in-file artifacts/02_markdown.json --out-file artifacts/03_parsed.json" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_03.json"
$proc.WaitForExit()
Validate-TriplexArtifact "03" "artifacts/03_parsed.json" "Phase03ParsedOutput" "artifacts/stdout_03.json"

# Phase 04: Semantic Chunking
Write-Host "-> Exercising Phase 04 (rag-p04)..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p04 --in-file artifacts/03_parsed.json --out-file artifacts/04_chunked.json --max-words 50 --overlap 10" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_04.json"
$proc.WaitForExit()
Validate-TriplexArtifact "04" "artifacts/04_chunked.json" "Phase04ChunkedOutput" "artifacts/stdout_04.json"

# Phase 04 (recursive strategy): separate artifact so the canonical 04_chunked.json stays untouched
Write-Host "-> Exercising Phase 04 --strategy recursive..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p04 --in-file artifacts/03_parsed.json --out-file artifacts/04_chunked_recursive.json --strategy recursive" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_04_recursive.json" -RedirectStandardError "artifacts/stderr_04_recursive.txt"
$null = $proc.Handle
$proc.WaitForExit()
if ($proc.ExitCode -ne 0) { Write-Host "[FAIL] rag-p04 --strategy recursive exited $($proc.ExitCode)" -ForegroundColor Red; exit 1 }
Validate-TriplexArtifact "04-recursive" "artifacts/04_chunked_recursive.json" "Phase04ChunkedOutput" "artifacts/stdout_04_recursive.json"

# Phase 04b: pass-through graph stage (stdout == its Phase 04 input)
Write-Host "-> Exercising Phase 04b (rag-p04b: entity graph side-artifact)..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p04b --in-file artifacts/04_chunked.json --out-file artifacts/04b_passthrough.json --graph-file artifacts/04b_graph.json" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_04b.json" -RedirectStandardError "artifacts/stderr_04b.txt"
$null = $proc.Handle
$proc.WaitForExit()
if ($proc.ExitCode -ne 0) { Write-Host "[FAIL] rag-p04b exited $($proc.ExitCode)" -ForegroundColor Red; exit 1 }
Validate-TriplexArtifact "04b" "artifacts/04b_passthrough.json" "Phase04ChunkedOutput" "artifacts/stdout_04b.json"
Validate-TriplexArtifact "04b-graph" "artifacts/04b_graph.json" "GraphArtifact" "artifacts/04b_graph.json"

# Phase 04 negative: unknown strategy must exit 2 with the known names on stderr and empty stdout
Write-Host "-> Negative test: rag-p04 --strategy nope (PASS = exit 2 + 'Known:')..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p04 --strategy nope --in-file artifacts/03_parsed.json --out-file artifacts/_neg.json" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_neg.json" -RedirectStandardError "artifacts/stderr_neg.txt"
$null = $proc.Handle
$proc.WaitForExit()
$negErr = Get-Content "artifacts/stderr_neg.txt" -Raw
if ($proc.ExitCode -ne 2 -or $negErr -notmatch "Known:" -or (Get-Item "artifacts/stdout_neg.json").Length -ne 0) {
    Write-Host "[FAIL] Negative strategy test: exit=$($proc.ExitCode), 'Known:' present=$($negErr -match 'Known:')" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Negative strategy test: exit 2, stderr lists known strategies, stdout empty" -ForegroundColor Green

# Phase 05: Live Jina-v3 + SPLADE Hybrid Qdrant Indexing
Write-Host "-> Exercising Phase 05 (rag-p05: Jina-v3 + SPLADE + Qdrant Upsert)..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p05 --in-file artifacts/04_chunked.json --out-file artifacts/05_indexed.json --collection test_hybrid_qdrant --qdrant-path ./qdrant_storage" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_05.json"
$proc.WaitForExit()
Validate-TriplexArtifact "05" "artifacts/05_indexed.json" "Phase05IndexedOutput" "artifacts/stdout_05.json"

# Phase 06: Query Orchestration
Write-Host "-> Exercising Phase 06 (rag-p06)..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p06 --in-file artifacts/05_indexed.json --out-file artifacts/06_query_plan.json --query `"How does Hybrid RAG fuse dense and sparse vectors and when does CRAG rewrite?`"" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_06.json"
$proc.WaitForExit()
Validate-TriplexArtifact "06" "artifacts/06_query_plan.json" "Phase06QueryPlanOutput" "artifacts/stdout_06.json"

# Phase 07: Live Qdrant Hybrid Prefetch + RRF Retrieval
Write-Host "-> Exercising Phase 07 (rag-p07: Qdrant Multi-Prefetch + RRF)..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p07 --in-file artifacts/06_query_plan.json --out-file artifacts/07_retrieved.json --qdrant-path ./qdrant_storage --rrf-k 60 --top-k 6" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_07.json"
$proc.WaitForExit()
Validate-TriplexArtifact "07" "artifacts/07_retrieved.json" "Phase07RetrievedOutput" "artifacts/stdout_07.json"

# Phase 08: Live Cross-Encoder Reranking & XML Context Assembly
Write-Host "-> Exercising Phase 08 (rag-p08: Live Cross-Encoder + XML Context)..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p08 --in-file artifacts/07_retrieved.json --out-file artifacts/08_reranked.json --backend fastembed --model jinaai/jina-reranker-v2-base-multilingual --top-n 4" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_08.json"
$proc.WaitForExit()
Validate-TriplexArtifact "08" "artifacts/08_reranked.json" "Phase08RerankedOutput" "artifacts/stdout_08.json"

# Phase 09: CRAG Verification & Grounded Generation
Write-Host "-> Exercising Phase 09 (rag-p09)..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p09 --in-file artifacts/08_reranked.json --out-file artifacts/09_generated.json --crag-threshold 0.55" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_09.json"
$proc.WaitForExit()
Validate-TriplexArtifact "09" "artifacts/09_generated.json" "Phase09GenerationOutput" "artifacts/stdout_09.json"

# Phase 10: RAG Triad Evaluation
Write-Host "-> Exercising Phase 10 (rag-p10)..." -ForegroundColor Yellow
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p10 --in-file artifacts/09_generated.json --out-file artifacts/10_evaluated.json" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_10.json"
$proc.WaitForExit()
Validate-TriplexArtifact "10" "artifacts/10_evaluated.json" "Phase10EvalOutput" "artifacts/stdout_10.json"

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host " STAGE 2: FULL 10-PHASE ZERO-COPY PIPE THROUGH-TEST BATTERY" -ForegroundColor White
Write-Host "================================================================================" -ForegroundColor Cyan

# Execute full 10-phase pipe through python subprocess chain for byte-exact pipe fidelity on Windows
$pipeRunner = @"
import subprocess
import sys
from pathlib import Path

p01 = subprocess.Popen([sys.executable, "p01_load.py"], stdout=subprocess.PIPE)
p02 = subprocess.Popen([sys.executable, "p02_markdown.py"], stdin=p01.stdout, stdout=subprocess.PIPE)
p01.stdout.close()
p03 = subprocess.Popen([sys.executable, "p03_parse.py"], stdin=p02.stdout, stdout=subprocess.PIPE)
p02.stdout.close()
p04 = subprocess.Popen([sys.executable, "p04_chunk.py", "--max-words", "50", "--overlap", "10"], stdin=p03.stdout, stdout=subprocess.PIPE)
p03.stdout.close()
p05 = subprocess.Popen([sys.executable, "p05_index.py", "--collection", "pipe_hybrid_qdrant", "--qdrant-path", "./qdrant_storage"], stdin=p04.stdout, stdout=subprocess.PIPE)
p04.stdout.close()
p06 = subprocess.Popen([sys.executable, "p06_query.py", "--query", "How does Qdrant fuse Jina-v3 dense and SPLADE sparse vectors?"], stdin=p05.stdout, stdout=subprocess.PIPE)
p05.stdout.close()
p07 = subprocess.Popen([sys.executable, "p07_retrieve.py", "--qdrant-path", "./qdrant_storage", "--rrf-k", "60", "--top-k", "5"], stdin=p06.stdout, stdout=subprocess.PIPE)
p06.stdout.close()
p08 = subprocess.Popen([sys.executable, "p08_rerank.py", "--backend", "fastembed", "--model", "jinaai/jina-reranker-v2-base-multilingual", "--top-n", "3"], stdin=p07.stdout, stdout=subprocess.PIPE)
p07.stdout.close()
p09 = subprocess.Popen([sys.executable, "p09_generate.py", "--crag-threshold", "0.50"], stdin=p08.stdout, stdout=subprocess.PIPE)
p08.stdout.close()
p10 = subprocess.Popen([sys.executable, "p10_evaluate.py"], stdin=p09.stdout, stdout=subprocess.PIPE)
p09.stdout.close()

final_out, _ = p10.communicate()
Path("artifacts/pipe_final_stdout.json").write_bytes(final_out)
if p10.returncode != 0:
    sys.exit(p10.returncode)
"@

$pipeRunner | uv run python -
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] 10-Phase pipe execution failed" -ForegroundColor Red
    exit 1
}

Validate-TriplexArtifact "PIPE_E2E" "artifacts/10_evaluated.json" "Phase10EvalOutput" "artifacts/pipe_final_stdout.json"

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host " STAGE 3: AUTONOMOUS CRAG LOOPBACK & QUERY-REWRITE CONVERGENCE BATTERY" -ForegroundColor White
Write-Host "================================================================================" -ForegroundColor Cyan

# Force high threshold (0.92) to exercise multi-attempt CRAG rewrite loop
$proc = Start-Process -FilePath "uv" -ArgumentList "run rag-p00 --in-file artifacts/05_indexed.json --out-file artifacts/00_crag_loop_summary.json --query `"How are things combined and retried?`" --qdrant-path ./qdrant_storage --rerank-backend fastembed --rerank-model jinaai/jina-reranker-v2-base-multilingual --crag-threshold 0.92 --max-retries 2 --quiet-children" -NoNewWindow -PassThru -RedirectStandardOutput "artifacts/stdout_00_loop.json"
$proc.WaitForExit()

Validate-TriplexArtifact "00_CRAG_LOOP" "artifacts/00_crag_loop_summary.json" "PhaseCRAGLoopOutput" "artifacts/stdout_00_loop.json"

Write-Host "`n================================================================================" -ForegroundColor Green
Write-Host " ALL STATIC REVIEWS, 10 ISOLATED PHASE TESTS, UNIX PIPE, & CRAG LOOP PASSED!" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Green
