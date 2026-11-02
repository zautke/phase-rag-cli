import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

p09_data = json.loads(Path("artifacts/readme_run/09_generated.json").read_text(encoding="utf-8-sig"))
p10_data = json.loads(Path("artifacts/readme_run/10_evaluated.json").read_text(encoding="utf-8-sig"))

query = p09_data.get("original_query", "")
verdict = p09_data.get("crag_verdict", "")
conf = p09_data.get("grounded_confidence", 0.0)
thresh = p09_data.get("threshold", 0.0)
answer = p09_data.get("synthesized_answer", "")
citations = p09_data.get("citations", [])

body = (
    f"[bold cyan]User Query:[/bold cyan] {query}\n\n"
    f"[bold green]CRAG Decision Gate:[/bold green] [bold underline]{verdict}[/bold underline] "
    f"(Cross-Encoder Confidence: {conf:.4f} >= Threshold: {thresh:.2f})\n\n"
    f"[bold yellow]Synthesized Grounded Answer:[/bold yellow]\n{answer}\n\n"
    f"[bold magenta]Citations Bound:[/bold magenta] {', '.join(citations) if citations else 'None'}"
)
console.print(Panel(body, title="[bold cyan]Phase 09 Grounded Generation Payload[/bold cyan]", border_style="cyan"))

t = Table(title="Phase 10: RAG Triad & Metric Evaluation", border_style="magenta", header_style="bold cyan")
t.add_column("Evaluation Metric", style="cyan")
t.add_column("Score", style="bold green", justify="right")
t.add_column("Benchmark Interpretation", style="white")

t.add_row("nDCG@k", f"{p10_data['ndcg_at_k']:.4f}", "Normalized Discounted Cumulative Gain of Context Ranking")
t.add_row("Context Precision", f"{p10_data['context_precision']:.4f}", "Ratio of candidate chunks exceeding relevance threshold (0.30)")
t.add_row("Faithfulness Score", f"{p10_data['faithfulness_score']:.4f}", "Lexical token grounding ratio against retrieved passages")
t.add_row("Answer Relevance", f"{p10_data['answer_relevance']:.4f}", "Query intent keyword coverage in generated response")
console.print(t)
