#!/usr/bin/env python3
# p04_chunk.py
from pathlib import Path
from typing import Annotated

import typer

from chunkers import resolve_chunker
from rag_contracts import (
    Phase03ParsedOutput,
    Phase04ChunkedOutput,
    PhaseCLI,
)

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 04: Semantic Chunking",
    Phase03ParsedOutput,
    Phase04ChunkedOutput,
    "artifacts/04_chunked.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p04 [--in-file / -i PATH] [--out-file / -o PATH] "
        "[--max-words / -m INT] [--overlap / -v INT] [--strategy / -s NAME] [--quiet / -q]\n"
        "Segments parsed sections into overlapping word chunks while preserving parent Markdown."
    )


@app.command()
def main(
    in_file: Annotated[
        Path | None,
        typer.Option("--in-file", "-i", help="Input Phase 03 JSON artifact (or pipe via stdin)"),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option("--out-file", "-o", help="Output Phase 04 JSON path"),
    ] = Path("artifacts/04_chunked.json"),
    max_words: Annotated[
        int,
        typer.Option("--max-words", "-m", min=1, help="Max words per child chunk"),
    ] = 60,
    overlap: Annotated[
        int,
        typer.Option("--overlap", "-v", help="Sliding window word overlap"),
    ] = 12,
    strategy: Annotated[
        str,
        typer.Option("--strategy", "-s", help="Chunker name (sliding_window|recursive)"),
    ] = "sliding_window",
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress stderr Rich panel"),
    ] = False,
) -> None:
    try:
        chunker = resolve_chunker(strategy)
    except KeyError as e:
        raise typer.BadParameter(e.args[0]) from None
    upstream: Phase03ParsedOutput = cli_engine.load_upstream(in_file)
    chunks = [c for sec in upstream.sections for c in chunker(sec, max_words, overlap)]
    output = Phase04ChunkedOutput(run_id=upstream.run_id, chunks=chunks, chunk_strategy=strategy)
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
