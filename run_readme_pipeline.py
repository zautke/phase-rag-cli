# run_readme_pipeline.py
import json
import shutil
import subprocess
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console(stderr=True)

art_dir = Path("artifacts/readme_run")
if art_dir.exists():
    shutil.rmtree(art_dir)
art_dir.mkdir(parents=True, exist_ok=True)

qdrant_dir = Path("qdrant_readme")
if qdrant_dir.exists():
    shutil.rmtree(qdrant_dir)

query = "How does Phase 08 Cross-Encoder reranking implement Lost-in-the-Middle context assembly and what eval metrics are computed in Phase 10?"

phases = [
    ("Phase 01: Document Loading", [
        sys.executable, "p01_load.py",
        "-s", "README.md",
        "-o", str(art_dir / "01_loaded.json")
    ]),
    ("Phase 02: Markdown Normalization", [
        sys.executable, "p02_markdown.py",
        "-i", str(art_dir / "01_loaded.json"),
        "-o", str(art_dir / "02_markdown.json")
    ]),
    ("Phase 03: Structural AST Parsing", [
        sys.executable, "p03_parse.py",
        "-i", str(art_dir / "02_markdown.json"),
        "-o", str(art_dir / "03_parsed.json")
    ]),
    ("Phase 04: Semantic Sliding-Window Chunking", [
        sys.executable, "p04_chunk.py",
        "-i", str(art_dir / "03_parsed.json"),
        "-o", str(art_dir / "04_chunked.json"),
        "--max-words", "80",
        "--overlap", "15"
    ]),
    ("Phase 05: Hybrid Qdrant Indexing (Jina-v3 + SPLADE)", [
        sys.executable, "p05_index.py",
        "-i", str(art_dir / "04_chunked.json"),
        "-o", str(art_dir / "05_indexed.json"),
        "--collection", "readme_corpus",
        "--qdrant-path", str(qdrant_dir)
    ]),
    ("Phase 06: Query Decomposition & HyDE Plan", [
        sys.executable, "p06_query.py",
        "-i", str(art_dir / "05_indexed.json"),
        "-o", str(art_dir / "06_query_plan.json"),
        "--query", query
    ]),
    ("Phase 07: Hybrid Prefetch + RRF Retrieval", [
        sys.executable, "p07_retrieve.py",
        "-i", str(art_dir / "06_query_plan.json"),
        "-o", str(art_dir / "07_retrieved.json"),
        "--qdrant-path", str(qdrant_dir),
        "--top-k", "6",
        "--rrf-k", "60"
    ]),
    ("Phase 08: Cross-Encoder Reranking & Lost-in-the-Middle XML", [
        sys.executable, "p08_rerank.py",
        "-i", str(art_dir / "07_retrieved.json"),
        "-o", str(art_dir / "08_reranked.json"),
        "--backend", "fastembed",
        "--model", "jinaai/jina-reranker-v2-base-multilingual",
        "--top-n", "4"
    ]),
    ("Phase 09: CRAG Grounded Generation", [
        sys.executable, "p09_generate.py",
        "-i", str(art_dir / "08_reranked.json"),
        "-o", str(art_dir / "09_generated.json"),
        "--crag-threshold", "0.50"
    ]),
    ("Phase 10: RAG Triad & nDCG Evaluation", [
        sys.executable, "p10_evaluate.py",
        "-i", str(art_dir / "09_generated.json"),
        "-o", str(art_dir / "10_evaluated.json")
    ]),
]

console.print(Panel(
    f"[bold white]Target Document:[/bold white] README.md ({Path('README.md').stat().st_size} bytes)\n"
    f"[bold cyan]Query:[/bold cyan] {query}\n"
    f"[bold green]Total Phases:[/bold green] 10 sequential isolated stages\n"
    f"[bold yellow]I/O Architecture:[/bold yellow] stderr Rich Telemetry Panels | Disk Artifacts in {art_dir}",
    title="[bold cyan]10-Phase SOTA Hybrid RAG Pipeline Execution[/bold cyan]",
    border_style="cyan"
))

for idx, (title, cmd) in enumerate(phases, start=1):
    console.print(f"\n[bold magenta]>>> EXECUTING PHASE {idx:02d}: {title}[/bold magenta]")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8-sig")
    stdout, stderr = proc.communicate()
    
    # Write captured raw JSON stdout to artifact
    stdout_file = art_dir / f"stdout_{idx:02d}.json"
    stdout_file.write_text(stdout, encoding="utf-8")
    
    # Display stderr Rich console output directly
    if stderr:
        sys.stderr.write(stderr)
        sys.stderr.flush()
        
    if proc.returncode != 0:
        console.print(f"[bold red][FAIL] Phase {idx:02d} exited with return code {proc.returncode}[/bold red]")
        sys.exit(proc.returncode)

console.print("\n" + "=" * 80)
console.print("[bold green]ALL 10 PHASES COMPLETED SUCCESSFULLY ON README.md![/bold green]")
console.print("=" * 80 + "\n")

# Display final generation and evaluation
p09 = json.loads((art_dir / "09_generated.json").read_text(encoding="utf-8-sig"))
p10 = json.loads((art_dir / "10_evaluated.json").read_text(encoding="utf-8-sig"))

body = (
    f"[bold cyan]User Query:[/bold cyan] {p09['original_query']}\n\n"
    f"[bold green]CRAG Verdict:[/bold green] [bold underline]{p09['crag_verdict']}[/bold underline] "
    f"(Confidence: {p09['grounded_confidence']:.4f})\n\n"
    f"[bold yellow]Generated Grounded Response:[/bold yellow]\n{p09['synthesized_answer']}\n\n"
    f"[bold magenta]Citations Used:[/bold magenta] {', '.join(p09['citations']) if p09.get('citations') else 'None'}"
)
console.print(Panel(body, title="[bold cyan]Phase 09: Final Grounded Generation[/bold cyan]", border_style="cyan"))

t = Table(title="Phase 10: RAG Triad & Metric Evaluation", border_style="magenta", header_style="bold cyan")
t.add_column("Metric", style="cyan")
t.add_column("Value", style="bold green", justify="right")
t.add_column("Interpretation", style="white")

t.add_row("nDCG@k", f"{p10['ndcg_at_k']:.4f}", "Normalized Discounted Cumulative Gain of Context Ranking")
t.add_row("Context Precision", f"{p10['context_precision']:.4f}", "Ratio of retrieved candidate chunks exceeding relevance threshold (0.30)")
t.add_row("Faithfulness Score", f"{p10['faithfulness_score']:.4f}", "Lexical token grounding ratio of generated claims against retrieved context")
t.add_row("Answer Relevance", f"{p10['answer_relevance']:.4f}", "Intent lexical coverage of query keywords in generated answer")
console.print(t)
