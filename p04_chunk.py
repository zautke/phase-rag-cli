#!/usr/bin/env python3
# p04_chunk.py
from pathlib import Path
from typing import Annotated

import typer

from rag_contracts import (
    DocumentChunk,
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
        "[--max-words / -m INT] [--overlap / -v INT] [--quiet / -q]\n"
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
        typer.Option("--max-words", "-m", help="Max words per child chunk"),
    ] = 60,
    overlap: Annotated[
        int,
        typer.Option("--overlap", "-v", help="Sliding window word overlap"),
    ] = 12,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress stderr Rich panel"),
    ] = False,
) -> None:
    upstream: Phase03ParsedOutput = cli_engine.load_upstream(in_file)
    chunks: list[DocumentChunk] = []

    for sec in upstream.sections:
        words = sec.body.split()
        step = max(1, max_words - overlap)
        for idx, start in enumerate(range(0, max(1, len(words)), step)):
            slice_words = words[start : start + max_words]
            if not slice_words:
                continue
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{sec.section_id}_chk_{idx}",
                    parent_section_id=sec.section_id,
                    doc_id=sec.doc_id,
                    text=" ".join(slice_words),
                    token_count=len(slice_words),
                    header_hierarchy=sec.header_path,
                    parent_markdown=f"### {' > '.join(sec.header_path)}\n{sec.body}",
                )
            )

    output = Phase04ChunkedOutput(run_id=upstream.run_id, chunks=chunks)
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
