#!/usr/bin/env python3
# p03_parse.py
import re
from pathlib import Path
from typing import Annotated

import typer

from rag_contracts import (
    ParsedSection,
    Phase02MarkdownOutput,
    Phase03ParsedOutput,
    PhaseCLI,
)

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 03: Structural Parsing",
    Phase02MarkdownOutput,
    Phase03ParsedOutput,
    "artifacts/03_parsed.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p03 [--in-file / -i PATH] [--out-file / -o PATH] [--quiet / -q]\n"
        "Splits clean Markdown into structural AST sections with hierarchical header paths."
    )


@app.command(epilog=Usage())
def main(
    in_file: Annotated[
        Path | None,
        typer.Option("--in-file", "-i", help="Input Phase 02 JSON artifact (or pipe via stdin)"),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option("--out-file", "-o", help="Output Phase 03 JSON path"),
    ] = Path("artifacts/03_parsed.json"),
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress stderr Rich panel"),
    ] = False,
) -> None:
    upstream: Phase02MarkdownOutput = cli_engine.load_upstream(in_file)
    sections: list[ParsedSection] = []

    for doc in upstream.documents:
        current_headers: list[str] = []
        buffer: list[str] = []
        sec_idx = 0

        for line in doc.clean_markdown.splitlines():
            header_match = re.match(r"^(#{1,6})\s+(.*)", line)
            if header_match:
                if buffer:
                    sections.append(
                        ParsedSection(
                            section_id=f"{doc.doc_id}_sec_{sec_idx}",
                            doc_id=doc.doc_id,
                            header_path=list(current_headers) or ["Root"],
                            body="\n".join(buffer).strip(),
                            metadata={"source_uri": doc.source_uri},
                        )
                    )
                    sec_idx += 1
                    buffer.clear()
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                current_headers = current_headers[: level - 1] + [title]
            else:
                if line.strip():
                    buffer.append(line)

        if buffer:
            sections.append(
                ParsedSection(
                    section_id=f"{doc.doc_id}_sec_{sec_idx}",
                    doc_id=doc.doc_id,
                    header_path=list(current_headers) or ["Root"],
                    body="\n".join(buffer).strip(),
                    metadata={"source_uri": doc.source_uri},
                )
            )

    output = Phase03ParsedOutput(run_id=upstream.run_id, sections=sections)
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
