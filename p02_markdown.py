#!/usr/bin/env python3
# p02_markdown.py
import re
from pathlib import Path
from typing import Annotated

import typer

from rag_contracts import (
    MarkdownDocument,
    Phase01LoadedOutput,
    Phase02MarkdownOutput,
    PhaseCLI,
)

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 02: Pre-Process to Markdown",
    Phase01LoadedOutput,
    Phase02MarkdownOutput,
    "artifacts/02_markdown.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p02 [--in-file / -i PATH] [--out-file / -o PATH] [--quiet / -q]\n"
        "Normalizes HTML and raw document content into clean Markdown."
    )


def html_to_clean_markdown(raw: str) -> str:
    flags = re.IGNORECASE | re.DOTALL
    text = re.sub(r"<h1>(.*?)</h1>", r"# \1\n\n", raw, flags=flags)
    text = re.sub(r"<h2>(.*?)</h2>", r"## \1\n\n", text, flags=flags)
    text = re.sub(r"<p>(.*?)</p>", r"\1\n\n", text, flags=flags)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


@app.command(epilog=Usage())
def main(
    in_file: Annotated[
        Path | None,
        typer.Option("--in-file", "-i", help="Input Phase 01 JSON artifact (or pipe via stdin)"),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option("--out-file", "-o", help="Output Phase 02 JSON path"),
    ] = Path("artifacts/02_markdown.json"),
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress stderr Rich panel"),
    ] = False,
) -> None:
    upstream: Phase01LoadedOutput = cli_engine.load_upstream(in_file)
    md_docs = []
    for doc in upstream.documents:
        clean_md = (
            html_to_clean_markdown(doc.raw_content)
            if "html" in doc.mime_type
            else doc.raw_content.strip()
        )
        md_docs.append(
            MarkdownDocument(
                doc_id=doc.doc_id,
                source_uri=doc.source_uri,
                clean_markdown=clean_md,
                frontmatter={"original_mime": doc.mime_type, "char_len": len(clean_md)},
            )
        )

    output = Phase02MarkdownOutput(run_id=upstream.run_id, documents=md_docs)
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
