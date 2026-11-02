# run_readme_pipeline.ps1
# Runs the full 10-phase pipeline on README.md with Rich console output displayed

$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8NoBom
[Console]::InputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$artDir = "artifacts/readme_run"
if (Test-Path $artDir) { Remove-Item -Recurse -Force $artDir }
if (Test-Path "qdrant_readme") { Remove-Item -Recurse -Force "qdrant_readme" }
New-Item -ItemType Directory -Path $artDir -Force | Out-Null

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host " EXECUTING 10-PHASE HYBRID RAG PIPELINE ON README.md" -ForegroundColor White
Write-Host "================================================================================" -ForegroundColor Cyan

# Phase 01: Load
Write-Host "`n>>> [PHASE 01: DOCUMENT LOADING]" -ForegroundColor Green
$p = Start-Process "uv" -ArgumentList "run rag-p01 -s README.md -o $artDir/01_loaded.json" -NoNewWindow -PassThru -RedirectStandardOutput "$artDir/stdout_01.json"
$p.WaitForExit()
if ($p.ExitCode -ne 0) { exit $p.ExitCode }

# Phase 02: Markdown Normalization
Write-Host "`n>>> [PHASE 02: MARKDOWN NORMALIZATION]" -ForegroundColor Green
$p = Start-Process "uv" -ArgumentList "run rag-p02 -i $artDir/01_loaded.json -o $artDir/02_markdown.json" -NoNewWindow -PassThru -RedirectStandardOutput "$artDir/stdout_02.json"
$p.WaitForExit()
if ($p.ExitCode -ne 0) { exit $p.ExitCode }

# Phase 03: AST Parsing
Write-Host "`n>>> [PHASE 03: STRUCTURAL AST PARSING]" -ForegroundColor Green
$p = Start-Process "uv" -ArgumentList "run rag-p03 -i $artDir/02_markdown.json -o $artDir/03_parsed.json" -NoNewWindow -PassThru -RedirectStandardOutput "$artDir/stdout_03.json"
$p.WaitForExit()
if ($p.ExitCode -ne 0) { exit $p.ExitCode }

# Phase 04: Semantic Chunking
Write-Host "`n>>> [PHASE 04: SEMANTIC SLIDING-WINDOW CHUNKING]" -ForegroundColor Green
$p = Start-Process "uv" -ArgumentList "run rag-p04 -i $artDir/03_parsed.json -o $artDir/04_chunked.json --max-words 75 --overlap 15" -NoNewWindow -PassThru -RedirectStandardOutput "$artDir/stdout_04.json"
$p.WaitForExit()
if ($p.ExitCode -ne 0) { exit $p.ExitCode }

# Phase 05: Hybrid Indexing (Dense + Sparse -> Qdrant)
Write-Host "`n>>> [PHASE 05: HYBRID QDRANT INDEXING (JINA-V3 + SPLADE)]" -ForegroundColor Green
$p = Start-Process "uv" -ArgumentList "run rag-p05 -i $artDir/04_chunked.json -o $artDir/05_indexed.json --collection readme_corpus --qdrant-path ./qdrant_readme" -NoNewWindow -PassThru -RedirectStandardOutput "$artDir/stdout_05.json"
$p.WaitForExit()
if ($p.ExitCode -ne 0) { exit $p.ExitCode }

# Phase 06: Query Decomposition & HyDE Plan
Write-Host "`n>>> [PHASE 06: QUERY ORCHESTRATION & HYDE]" -ForegroundColor Green
$query = "How does Phase 08 Cross-Encoder reranking implement Lost-in-the-Middle context assembly and what eval metrics are computed in Phase 10?"
$p = Start-Process "uv" -ArgumentList "run rag-p06 -i $artDir/05_indexed.json -o $artDir/06_query_plan.json --query `"$query`"" -NoNewWindow -PassThru -RedirectStandardOutput "$artDir/stdout_06.json"
$p.WaitForExit()
if ($p.ExitCode -ne 0) { exit $p.ExitCode }

# Phase 07: Hybrid Prefetch + RRF Retrieval
Write-Host "`n>>> [PHASE 07: HYBRID PREFETCH + RRF RETRIEVAL]" -ForegroundColor Green
$p = Start-Process "uv" -ArgumentList "run rag-p07 -i $artDir/06_query_plan.json -o $artDir/07_retrieved.json --qdrant-path ./qdrant_readme --top-k 6 --rrf-k 60" -NoNewWindow -PassThru -RedirectStandardOutput "$artDir/stdout_07.json"
$p.WaitForExit()
if ($p.ExitCode -ne 0) { exit $p.ExitCode }

# Phase 08: Cross-Encoder Reranking & Lost-in-the-Middle Context
Write-Host "`n>>> [PHASE 08: CROSS-ENCODER RERANKING & LOST-IN-THE-MIDDLE ASSEMBLY]" -ForegroundColor Green
$p = Start-Process "uv" -ArgumentList "run rag-p08 -i $artDir/07_retrieved.json -o $artDir/08_reranked.json --backend fastembed --model jinaai/jina-reranker-v2-base-multilingual --top-n 4" -NoNewWindow -PassThru -RedirectStandardOutput "$artDir/stdout_08.json"
$p.WaitForExit()
if ($p.ExitCode -ne 0) { exit $p.ExitCode }

# Phase 09: CRAG Verification & Generation
Write-Host "`n>>> [PHASE 09: CRAG GROUNDED GENERATION]" -ForegroundColor Green
$p = Start-Process "uv" -ArgumentList "run rag-p09 -i $artDir/08_reranked.json -o $artDir/09_generated.json --crag-threshold 0.50" -NoNewWindow -PassThru -RedirectStandardOutput "$artDir/stdout_09.json"
$p.WaitForExit()
if ($p.ExitCode -ne 0) { exit $p.ExitCode }

# Phase 10: Evaluation
Write-Host "`n>>> [PHASE 10: RAG TRIAD & NDCG EVALUATION]" -ForegroundColor Green
$p = Start-Process "uv" -ArgumentList "run rag-p10 -i $artDir/09_generated.json -o $artDir/10_evaluated.json" -NoNewWindow -PassThru -RedirectStandardOutput "$artDir/stdout_10.json"
$p.WaitForExit()
if ($p.ExitCode -ne 0) { exit $p.ExitCode }

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host " PIPELINE RUN COMPLETE - FINAL GENERATION & EVALUATION PAYLOADS" -ForegroundColor White
Write-Host "================================================================================" -ForegroundColor Cyan

$printerScript = @'
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
p09 = json.loads(Path("artifacts/readme_run/09_generated.json").read_text(encoding="utf-8"))
p10 = json.loads(Path("artifacts/readme_run/10_evaluated.json").read_text(encoding="utf-8"))

body = (
    f"[bold cyan]Query:[/bold cyan] {p09['original_query']}\n\n"
    f"[bold green]CRAG Verdict:[/bold green] {p09['crag_verdict']} (Confidence: {p09['grounded_confidence']:.4f})\n\n"
    f"[bold yellow]Generated Answer:[/bold yellow]\n{p09['synthesized_answer']}\n\n"
    f"[bold magenta]Citations Used:[/bold magenta] {', '.join(p09['citations'])}"
)
console.print(Panel(body, title="Phase 09 Grounded Generation", border_style="cyan"))

t = Table(title="Phase 10 Evaluation Metrics", border_style="magenta")
t.add_column("Metric", style="cyan")
t.add_column("Value", style="bold green")
t.add_column("Description", style="white")
t.add_row("nDCG@k", f"{p10['ndcg_at_k']:.4f}", "Normalized Discounted Cumulative Gain of Context Ranking")
t.add_row("Context Precision", f"{p10['context_precision']:.4f}", "Ratio of high-relevance chunks in retrieved context")
t.add_row("Faithfulness Score", f"{p10['faithfulness_score']:.4f}", "Token grounding ratio against retrieved passages")
t.add_row("Answer Relevance", f"{p10['answer_relevance']:.4f}", "Query intent term overlap in generated answer")
console.print(t)
'@

$printerScript | uv run python -

