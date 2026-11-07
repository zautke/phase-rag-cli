#!/usr/bin/env python3
# p05_index.py
from pathlib import Path
from typing import Annotated

import typer
from qdrant_client import models

from hybrid_engine import (
    DEFAULT_DENSE_BACKEND,
    DEFAULT_DENSE_MODEL,
    DEFAULT_QDRANT_PATH,
    DEFAULT_SPARSE_MODEL,
    DENSE_BACKENDS,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    deterministic_point_uuid,
    embed_dense_batch,
    embed_sparse_batch,
    ensure_hybrid_collection,
    get_dense_embedder,
    get_qdrant_client,
    resolve_backend,
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
        "[--dense-backend / -b NAME] [--dense-model / -m NAME] [--sparse-model / -s NAME] "
        "[--recreate / -r | --append / -a] [--quiet / -q]\n"
        "Computes dense and sparse embeddings with the named plugin backends and upserts to Qdrant."
    )


@app.command(epilog=Usage())
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
            envvar="QDRANT_PATH",
            help="Local persistent Qdrant path if no URL",
        ),
    ] = DEFAULT_QDRANT_PATH,
    dense_backend: Annotated[
        str,
        typer.Option(
            "--dense-backend",
            "-b",
            envvar="RAG_DENSE_BACKEND",
            help=f"Dense embedder plugin ({'|'.join(sorted(DENSE_BACKENDS))})",
        ),
    ] = DEFAULT_DENSE_BACKEND,
    dense_model: Annotated[
        str,
        typer.Option("--dense-model", "-m", envvar="RAG_DENSE_MODEL", help="Dense embedding model"),
    ] = DEFAULT_DENSE_MODEL,
    sparse_model: Annotated[
        str,
        typer.Option("--sparse-model", "-s", envvar="RAG_SPARSE_MODEL", help="Sparse (SPLADE) model"),
    ] = DEFAULT_SPARSE_MODEL,
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
    try:
        resolve_backend(DENSE_BACKENDS, dense_backend, "dense")
    except ValueError as e:
        raise typer.BadParameter(str(e)) from None
    upstream: Phase04ChunkedOutput = cli_engine.load_upstream(in_file)

    # 1. Build contextualized text strings for batch neural encoding
    contextualized_texts: list[str] = [
        f"[Doc: {chk.doc_id} | Section: {' > '.join(chk.header_hierarchy)}] {chk.text}"
        for chk in upstream.chunks
    ]

    # 2. Compute dense and sparse (lexical expansion) vectors with the named plugins
    dense_vectors = embed_dense_batch(contextualized_texts, dense_backend, dense_model)
    sparse_tuples = embed_sparse_batch(contextualized_texts, sparse_model)

    # 3. Initialize Qdrant Hybrid Collection (vector size from the loaded dense model) & build PointStructs
    _, dense_dim = get_dense_embedder(dense_backend, dense_model)
    client = get_qdrant_client(qdrant_url, qdrant_path)
    ensure_hybrid_collection(client, collection, dense_dim, recreate=recreate)

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
        dense_backend=dense_backend,
        dense_model=dense_model,
        sparse_model=sparse_model,
        indexed_records=indexed_records,
    )
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
