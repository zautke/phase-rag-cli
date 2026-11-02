#!/usr/bin/env python3
# p05_index.py
from pathlib import Path
from typing import Annotated

import typer
from qdrant_client import models

from hybrid_engine import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    deterministic_point_uuid,
    embed_dense_batch,
    embed_sparse_batch,
    ensure_hybrid_collection,
    get_qdrant_client,
)
from rag_contracts import (
    EnrichedIndexedChunk,
    Phase04ChunkedOutput,
    Phase05IndexedOutput,
    PhaseCLI,
)

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 05: Live Jina-v3 + SPLADE Hybrid Qdrant Indexing",
    Phase04ChunkedOutput,
    Phase05IndexedOutput,
    "artifacts/05_indexed.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p05 [--in-file / -i PATH] [--out-file / -o PATH] "
        "[--collection / -c NAME] [--qdrant-url / -u URL] [--qdrant-path / -p PATH] "
        "[--recreate / -r | --append / -a] [--quiet / -q]\n"
        "Computes live Jina-v3 dense and SPLADE++ sparse embeddings and upserts to Qdrant."
    )


@app.command()
def main(
    in_file: Annotated[
        Path | None,
        typer.Option("--in-file", "-i", help="Input Phase 04 JSON artifact (or pipe via stdin)"),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option("--out-file", "-o", help="Output Phase 05 JSON path"),
    ] = Path("artifacts/05_indexed.json"),
    collection: Annotated[
        str,
        typer.Option("--collection", "-c", help="Qdrant collection name"),
    ] = "sota_hybrid_rag_v1",
    qdrant_url: Annotated[
        str | None,
        typer.Option(
            "--qdrant-url",
            "-u",
            envvar="QDRANT_URL",
            help="e.g. http://localhost:6333",
        ),
    ] = None,
    qdrant_path: Annotated[
        str,
        typer.Option(
            "--qdrant-path",
            "-p",
            help="Local persistent Qdrant path if no URL",
        ),
    ] = "./qdrant_storage",
    recreate: Annotated[
        bool,
        typer.Option(
            "--recreate/--append",
            "-r/-a",
            help="Recreate Qdrant collection on run",
        ),
    ] = True,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress stderr Rich panel"),
    ] = False,
) -> None:
    upstream: Phase04ChunkedOutput = cli_engine.load_upstream(in_file)

    # 1. Build contextualized text strings for batch neural encoding
    contextualized_texts: list[str] = [
        f"[Doc: {chk.doc_id} | Section: {' > '.join(chk.header_hierarchy)}] {chk.text}"
        for chk in upstream.chunks
    ]

    # 2. Compute live Jina-v3 (1024-d dense) and SPLADE++ (sparse lexical expansion) vectors
    dense_vectors = embed_dense_batch(contextualized_texts)
    sparse_tuples = embed_sparse_batch(contextualized_texts)

    # 3. Initialize Qdrant Hybrid Collection & build PointStructs
    client = get_qdrant_client(qdrant_url, qdrant_path)
    ensure_hybrid_collection(client, collection, recreate=recreate)

    indexed_records: list[EnrichedIndexedChunk] = []
    points: list[models.PointStruct] = []

    for chk, ctx_text, d_vec, (s_idx, s_val) in zip(
        upstream.chunks, contextualized_texts, dense_vectors, sparse_tuples, strict=True
    ):
        record = EnrichedIndexedChunk(
            chunk_id=chk.chunk_id,
            doc_id=chk.doc_id,
            contextualized_text=ctx_text,
            dense_vector=d_vec,
            sparse_indices=s_idx,
            sparse_values=s_val,
            parent_markdown=chk.parent_markdown,
            header_hierarchy=chk.header_hierarchy,
        )
        indexed_records.append(record)

        points.append(
            models.PointStruct(
                id=deterministic_point_uuid(chk.chunk_id),
                vector={
                    DENSE_VECTOR_NAME: d_vec,
                    SPARSE_VECTOR_NAME: models.SparseVector(indices=s_idx, values=s_val),
                },
                payload={
                    "chunk_id": chk.chunk_id,
                    "doc_id": chk.doc_id,
                    "contextualized_text": ctx_text,
                    "parent_markdown": chk.parent_markdown,
                    "header_hierarchy": chk.header_hierarchy,
                },
            )
        )

    if points:
        client.upsert(collection_name=collection, points=points, wait=True)

    client.close()

    output = Phase05IndexedOutput(
        run_id=upstream.run_id,
        qdrant_collection=collection,
        indexed_records=indexed_records,
    )
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
