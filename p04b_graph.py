#!/usr/bin/env python3
# p04b_graph.py
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from rag_contracts import (
    DocumentChunk,
    GraphArtifact,
    GraphEdge,
    GraphNode,
    Phase04ChunkedOutput,
    PhaseCLI,
    err_console,
)

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 04b: Entity Graph (pass-through)",
    Phase04ChunkedOutput,
    Phase04ChunkedOutput,
    "artifacts/04b_passthrough.json",
)

_ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9\-]+(?:\s+[A-Z][A-Za-z0-9\-]+)*\b")
_STOP = {"The", "A", "An", "This", "It", "In", "On", "For", "And", "But"}


def Usage() -> str:
    return (
        "Usage: rag-p04b [--in-file / -i PATH] [--out-file / -o PATH] [--graph-file / -g PATH] "
        "[--extractor / -e NAME] [--min-weight / -w INT] [--quiet / -q]\n"
        "Passes Phase 04 chunks through unchanged and writes an entity co-occurrence graph side-artifact."
    )


def extract_entities_heuristic(text: str) -> list[str]:
    # ponytail: heuristic NER; upgrade = --extractor ollama|spacy
    found = [m for m in _ENTITY_RE.findall(text) if m not in _STOP]
    return list(dict.fromkeys(found))


def build_graph(
    chunks: list[DocumentChunk], min_weight: int = 1
) -> tuple[list[GraphNode], list[GraphEdge]]:
    ent_chunks: dict[str, list[str]] = defaultdict(list)
    pair_chunks: dict[tuple[str, str], list[str]] = defaultdict(list)
    for c in chunks:
        ents = sorted(extract_entities_heuristic(c.text))
        for e in ents:
            ent_chunks[e].append(c.chunk_id)
        for pair in combinations(ents, 2):
            pair_chunks[pair].append(c.chunk_id)
    nodes = [GraphNode(entity=e, chunk_ids=ids) for e, ids in sorted(ent_chunks.items())]
    edges = [
        GraphEdge(source=s, target=t, weight=len(ids), chunk_ids=ids)
        for (s, t), ids in pair_chunks.items()
        if len(ids) >= min_weight
    ]
    edges.sort(key=lambda e: (-e.weight, e.source, e.target))
    return nodes, edges


@app.command()
def main(
    in_file: Annotated[
        Path | None,
        typer.Option("--in-file", "-i", help="Input Phase 04 JSON artifact (or pipe via stdin)"),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option("--out-file", "-o", help="Pass-through Phase 04 JSON path"),
    ] = Path("artifacts/04b_passthrough.json"),
    graph_file: Annotated[
        Path,
        typer.Option("--graph-file", "-g", help="Output graph side-artifact JSON path"),
    ] = Path("artifacts/04b_graph.json"),
    extractor: Annotated[
        str,
        typer.Option("--extractor", "-e", help="Entity extractor (heuristic)"),
    ] = "heuristic",
    min_weight: Annotated[
        int,
        typer.Option("--min-weight", "-w", help="Drop edges with fewer co-occurring chunks"),
    ] = 1,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress stderr Rich panels"),
    ] = False,
) -> None:
    if extractor != "heuristic":
        raise typer.BadParameter(f"Unknown extractor '{extractor}'. Known: heuristic")
    upstream: Phase04ChunkedOutput = cli_engine.load_upstream(in_file)
    nodes, edges = build_graph(upstream.chunks, min_weight)
    artifact = GraphArtifact(
        run_id=upstream.run_id, extractor=extractor, nodes=nodes, edges=edges
    )
    graph_file.parent.mkdir(parents=True, exist_ok=True)
    graph_file.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    if not quiet:
        top = ", ".join(n.entity for n in sorted(nodes, key=lambda n: -len(n.chunk_ids))[:5])
        err_console.print(
            Panel(
                f"nodes={len(nodes)} edges={len(edges)}\ntop entities: {top or '-'}",
                title=f"[bold cyan]Phase 04b graph[/bold cyan] -> [yellow]{graph_file}[/yellow]",
                border_style="cyan",
            )
        )
    cli_engine.emit(upstream, out_file, quiet)


if __name__ == "__main__":
    app()