#!/usr/bin/env python3
# p06_query.py
from pathlib import Path
from typing import Annotated

import typer

from rag_contracts import Phase05IndexedOutput, Phase06QueryPlanOutput, PhaseCLI

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 06: Pre-Retrieval Query Orchestration",
    Phase05IndexedOutput,
    Phase06QueryPlanOutput,
    "artifacts/06_query_plan.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p06 [--query / -q TEXT] [--in-file / -i PATH] "
        "[--out-file / -o PATH] [--quiet / -s]\n"
        "Decomposes multi-clause queries and synthesizes a HyDE passage for hybrid retrieval."
    )


@app.command()
def main(
    query: Annotated[
        str,
        typer.Option(
            "--query",
            "-q",
            help="User natural language query",
        ),
    ] = "How does Hybrid RAG fuse dense and sparse vectors and when does CRAG rewrite?",
    in_file: Annotated[
        Path | None,
        typer.Option(
            "--in-file",
            "-i",
            help="Input Phase 05 JSON artifact (or pipe via stdin)",
        ),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option(
            "--out-file",
            "-o",
            help="Output Phase 06 JSON path",
        ),
    ] = Path("artifacts/06_query_plan.json"),
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-s",
            help="Suppress stderr Rich panel",
        ),
    ] = False,
) -> None:
    upstream: Phase05IndexedOutput = cli_engine.load_upstream(in_file)

    # Multi-query decomposition + HyDE generation
    sub_queries = [
        q.strip() for q in query.replace(" and ", " | ").split("|") if q.strip()
    ]
    hyde_passage = (
        f"Technical specification answering '{query}': Hybrid RAG combines Qdrant HNSW dense embeddings "
        f"with SPLADE sparse vectors via Reciprocal Rank Fusion (RRF) and verifies relevance via CRAG."
    )

    output = Phase06QueryPlanOutput(
        run_id=upstream.run_id,
        original_query=query,
        route="hybrid_rag_multi_query",
        sub_queries=sub_queries,
        hyde_passage=hyde_passage,
        metadata_filters={"collection": upstream.qdrant_collection},
        qdrant_collection=upstream.qdrant_collection,
    )
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
