#!/usr/bin/env python3
# p01_load.py
from pathlib import Path
from typing import Annotated

import typer

from rag_contracts import Phase01LoadedOutput, PhaseCLI, RawDocument

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 01: Document Loading",
    None,
    Phase01LoadedOutput,
    "artifacts/01_loaded.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p01 [--source-dir / -s PATH] [--out-file / -o PATH] [--quiet / -q]\n"
        "Loads raw documents from a directory or emits the built-in sample corpus."
    )


@app.command()
def main(
    source_dir: Annotated[
        Path | None,
        typer.Option("--source-dir", "-s", help="Directory of raw docs"),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option("--out-file", "-o", help="Output JSON artifact path"),
    ] = Path("artifacts/01_loaded.json"),
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress stderr Rich panel"),
    ] = False,
) -> None:
    docs = []
    if source_dir and source_dir.exists():
        for p in sorted(source_dir.glob("*.*")):
            docs.append(
                RawDocument(
                    doc_id=p.stem,
                    source_uri=str(p.resolve()),
                    mime_type="text/markdown" if p.suffix == ".md" else "text/plain",
                    raw_content=p.read_text(encoding="utf-8", errors="ignore"),
                )
            )
    else:
        # Built-in sample corpus for immediate zero-config testing
        docs = [
            RawDocument(
                doc_id="doc_arch_01",
                source_uri="s3://rag-corpus/hybrid_search_spec.html",
                mime_type="text/html",
                raw_content=(
                    "<html><body><h1>Hybrid RAG Architecture</h1>"
                    "<p>Combine Qdrant HNSW dense vectors (jina-embeddings-v3) with SPLADE sparse vectors "
                    "using Reciprocal Rank Fusion (k=60).</p>"
                    "<h2>Late Chunking</h2>"
                    "<p>Apply long-context token pooling before segmentation to preserve cross-paragraph anaphora.</p>"
                    "</body></html>"
                ),
            ),
            RawDocument(
                doc_id="doc_sec_02",
                source_uri="s3://rag-corpus/crag_verification.md",
                mime_type="text/markdown",
                raw_content=(
                    "# Corrective RAG (CRAG)\n"
                    "If the cross-encoder score falls below 0.65, trigger a query rewrite loop "
                    "before invoking the generator LLM."
                ),
            ),
        ]

    output = Phase01LoadedOutput(documents=docs)
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
