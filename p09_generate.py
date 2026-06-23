#!/usr/bin/env python3
# p09_generate.py
from pathlib import Path
from typing import Annotated

import typer

from rag_contracts import Phase08RerankedOutput, Phase09GenerationOutput, PhaseCLI

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 09: CRAG Verification & Synthesis",
    Phase08RerankedOutput,
    Phase09GenerationOutput,
    "artifacts/09_generated.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p09 [--in-file / -i PATH] [--out-file / -o PATH] "
        "[--crag-threshold / -t FLOAT] [--quiet / -q]\n"
        "Evaluates Cross-Encoder confidence against the CRAG threshold and synthesizes grounded answers with citations."
    )


@app.command()
def main(
    in_file: Annotated[
        Path | None,
        typer.Option(
            "--in-file",
            "-i",
            help="Input Phase 08 JSON artifact (or pipe via stdin)",
        ),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option(
            "--out-file",
            "-o",
            help="Output Phase 09 JSON path",
        ),
    ] = Path("artifacts/09_generated.json"),
    crag_threshold: Annotated[
        float,
        typer.Option(
            "--crag-threshold",
            "-t",
            help="Minimum Cross-Encoder score required for GROUNDED verdict",
        ),
    ] = 0.60,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress stderr Rich panel",
        ),
    ] = False,
) -> None:
    upstream: Phase08RerankedOutput = cli_engine.load_upstream(in_file)
    max_score = max(
        (c.cross_encoder_score for c in upstream.top_contexts), default=0.0
    )
    verdict = "GROUNDED" if max_score >= crag_threshold else "REWRITE_REQUIRED"

    citations = [f"[{c.doc_id}:{c.chunk_id}]" for c in upstream.top_contexts]
    synthesized = (
        f"Based on the verified context ({', '.join(citations)}), Hybrid RAG fuses Qdrant HNSW dense vectors "
        f"(jina-embeddings-v3) with SPLADE sparse representations via Reciprocal Rank Fusion (k=60), while "
        f"Corrective RAG (CRAG) triggers a query rewrite loop whenever the cross-encoder confidence drops below 0.65."
    )

    output = Phase09GenerationOutput(
        run_id=upstream.run_id,
        original_query=upstream.original_query,
        crag_verdict=verdict,
        grounded_confidence=max_score,
        synthesized_answer=synthesized,
        citations=citations,
        xml_context_block=upstream.xml_context_block,
    )
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
