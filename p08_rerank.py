#!/usr/bin/env python3
# p08_rerank.py
from pathlib import Path
from typing import Annotated

import typer

from hybrid_engine import (
    DEFAULT_RERANK_MODEL,
    rerank_passages_batch,
    resolve_rerank_model,
)
from rag_contracts import (
    Phase07RetrievedOutput,
    Phase08RerankedOutput,
    PhaseCLI,
    RerankedContextItem,
    err_console,
)

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 08: Live Cross-Encoder Reranking & XML Context Assembly",
    Phase07RetrievedOutput,
    Phase08RerankedOutput,
    "artifacts/08_reranked.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p08 [--in-file / -i PATH] [--out-file / -o PATH] "
        "[--model / -m NAME] [--backend / -b BACKEND] [--batch-size / -s INT] "
        "[--dedupe-parents / -d | --keep-duplicate-parents / -k] "
        "[--reorder-litm / -r | --strict-rank-order / -l] [--top-n / -n INT] [--quiet / -q]\n"
        "Scores retrieved candidates via Cross-Encoder, deduplicates parent sections, and builds XML context."
    )


def apply_lost_in_the_middle_ordering(
    items: list[RerankedContextItem],
) -> list[RerankedContextItem]:
    """
    Places rank #1 at the start, rank #2 at the end, rank #3 second from start, etc.
    Mitigates U-shaped transformer attention decay across long XML context blocks.
    """
    if len(items) <= 2:
        return items
    left: list[RerankedContextItem] = []
    right: list[RerankedContextItem] = []
    for idx, item in enumerate(items):
        if idx % 2 == 0:
            left.append(item)
        else:
            right.append(item)
    return left + list(reversed(right))


@app.command()
def main(
    in_file: Annotated[
        Path | None,
        typer.Option(
            "--in-file",
            "-i",
            help="Input Phase 07 JSON artifact (or pipe via stdin)",
        ),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option(
            "--out-file",
            "-o",
            help="Output Phase 08 JSON path",
        ),
    ] = Path("artifacts/08_reranked.json"),
    model_name: Annotated[
        str,
        typer.Option(
            "--model",
            "-m",
            help="Cross-Encoder model (e.g., BAAI/bge-reranker-v2-m3, jinaai/jina-reranker-v3, or jinaai/jina-reranker-v2-base-multilingual; with -b fastembed the torch default maps to jinaai/jina-reranker-v2-base-multilingual)",
        ),
    ] = DEFAULT_RERANK_MODEL,
    backend: Annotated[
        str,
        typer.Option(
            "--backend",
            "-b",
            help="Execution runtime: 'transformers' (PyTorch/MPS/CUDA) or 'fastembed' (ONNX)",
        ),
    ] = "transformers",
    batch_size: Annotated[
        int,
        typer.Option(
            "--batch-size",
            "-s",
            help="Batch size for Cross-Encoder inference",
        ),
    ] = 16,
    dedupe_parents: Annotated[
        bool,
        typer.Option(
            "--dedupe-parents/--keep-duplicate-parents",
            "-d/-k",
            help="Deduplicate multiple child chunks that expand to the same parent Markdown section",
        ),
    ] = True,
    reorder_litm: Annotated[
        bool,
        typer.Option(
            "--reorder-litm/--strict-rank-order",
            "-r/-l",
            help="Apply Lost-in-the-Middle ordering to XML context block while keeping top_contexts sorted by score",
        ),
    ] = True,
    top_n: Annotated[
        int,
        typer.Option(
            "--top-n",
            "-n",
            help="Final reranked contexts passed to generation",
        ),
    ] = 5,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress stderr Rich panel",
        ),
    ] = False,
) -> None:
    upstream: Phase07RetrievedOutput = cli_engine.load_upstream(in_file)
    query = upstream.query_plan.original_query
    candidates = upstream.candidates

    if not candidates:
        empty_output = Phase08RerankedOutput(
            run_id=upstream.run_id,
            original_query=query,
            xml_context_block="<retrieved_context>\n</retrieved_context>",
            top_contexts=[],
        )
        cli_engine.emit(empty_output, out_file, quiet)
        return

    # 1. Batch score all (query, contextualized_text) candidate pairs through the live Cross-Encoder
    passages = [cand.contextualized_text for cand in candidates]
    rerank_backend = "fastembed" if backend.lower() == "fastembed" else "transformers"
    resolved_model = resolve_rerank_model(model_name, rerank_backend)
    if not quiet:
        err_console.print(f"[cyan]Reranker:[/cyan] {rerank_backend} / {resolved_model}")
    ce_scores = rerank_passages_batch(
        query=query,
        passages=passages,
        model_name=resolved_model,
        backend=rerank_backend,
        batch_size=batch_size,
    )

    # 2. Pair candidates with calibrated Cross-Encoder scores
    scored_items: list[RerankedContextItem] = [
        RerankedContextItem(
            chunk_id=cand.chunk_id,
            doc_id=cand.doc_id,
            cross_encoder_score=score,
            expanded_parent_context=cand.parent_markdown,
        )
        for cand, score in zip(candidates, ce_scores, strict=True)
    ]

    # Sort strictly descending by Cross-Encoder score
    scored_items.sort(key=lambda x: x.cross_encoder_score, reverse=True)

    # 3. Optional Parent-Section Deduplication (prevents duplicate parent sections in context)
    if dedupe_parents:
        deduped_by_parent: dict[str, RerankedContextItem] = {}
        for item in scored_items:
            parent_key = f"{item.doc_id}::{hash(item.expanded_parent_context)}"
            if parent_key not in deduped_by_parent:
                deduped_by_parent[parent_key] = item
        selected = list(deduped_by_parent.values())[:top_n]
    else:
        selected = scored_items[:top_n]

    # 4. Assemble XML Context Block (with optional Lost-in-the-Middle attention ordering)
    xml_ordered_items = (
        apply_lost_in_the_middle_ordering(selected) if reorder_litm else selected
    )

    xml_parts = ["<retrieved_context>"]
    for item in xml_ordered_items:
        xml_parts.append(
            f'  <document id="{item.doc_id}" chunk_id="{item.chunk_id}" rerank_score="{item.cross_encoder_score:.4f}">\n'
            f"    {item.expanded_parent_context}\n"
            f"  </document>"
        )
    xml_parts.append("</retrieved_context>")

    output = Phase08RerankedOutput(
        run_id=upstream.run_id,
        original_query=query,
        xml_context_block="\n".join(xml_parts),
        top_contexts=selected,
    )
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
