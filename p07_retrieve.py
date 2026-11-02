#!/usr/bin/env python3
# p07_retrieve.py
from pathlib import Path
from typing import Annotated

import typer
from qdrant_client import models

from hybrid_engine import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    embed_dense_batch,
    embed_sparse_batch,
    get_qdrant_client,
)
from rag_contracts import (
    Phase06QueryPlanOutput,
    Phase07RetrievedOutput,
    PhaseCLI,
    RetrievedCandidate,
)

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 07: Live Qdrant Hybrid Prefetch + RRF Fusion",
    Phase06QueryPlanOutput,
    Phase07RetrievedOutput,
    "artifacts/07_retrieved.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p07 [--in-file / -i PATH] [--out-file / -o PATH] "
        "[--qdrant-url / -u URL] [--qdrant-path / -p PATH] [--prefetch-limit / -l INT] "
        "[--rrf-k / -k INT] [--dense-weight / -d FLOAT] [--sparse-weight / -s FLOAT] "
        "[--top-k / -t INT] [--quiet / -q]\n"
        "Executes live Qdrant Multi-Prefetch + Parameterized RRF hybrid retrieval."
    )


@app.command()
def main(
    in_file: Annotated[
        Path | None,
        typer.Option("--in-file", "-i", help="Input Phase 06 JSON artifact (or pipe via stdin)"),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option("--out-file", "-o", help="Output Phase 07 JSON path"),
    ] = Path("artifacts/07_retrieved.json"),
    qdrant_url: Annotated[
        str | None,
        typer.Option("--qdrant-url", "-u", envvar="QDRANT_URL", help="Remote Qdrant URL"),
    ] = None,
    qdrant_path: Annotated[
        str,
        typer.Option("--qdrant-path", "-p", help="Local persistent Qdrant path"),
    ] = "./qdrant_storage",
    prefetch_limit: Annotated[
        int,
        typer.Option("--prefetch-limit", "-l", help="Candidate pool per branch before RRF"),
    ] = 25,
    rrf_k: Annotated[
        int,
        typer.Option("--rrf-k", "-k", help="Qdrant Reciprocal Rank Fusion k constant"),
    ] = 60,
    dense_weight: Annotated[
        float,
        typer.Option("--dense-weight", "-d", help="RRF weight for Jina-v3 dense branch"),
    ] = 1.0,
    sparse_weight: Annotated[
        float,
        typer.Option("--sparse-weight", "-s", help="RRF weight for SPLADE sparse branch"),
    ] = 1.0,
    top_k: Annotated[
        int,
        typer.Option("--top-k", "-t", help="Final fused candidates returned"),
    ] = 10,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress stderr Rich panel"),
    ] = False,
) -> None:
    upstream: Phase06QueryPlanOutput = cli_engine.load_upstream(in_file)
    collection = upstream.index_snapshot.qdrant_collection

    # 1. Encode dense query (original query + HyDE expansion) and sparse query (original lexical query)
    q_dense_vec = embed_dense_batch([f"{upstream.original_query}\n{upstream.hyde_passage}"])[0]
    q_sparse_idx, q_sparse_val = embed_sparse_batch([upstream.original_query])[0]
    q_sparse_vec = models.SparseVector(indices=q_sparse_idx, values=q_sparse_val)

    client = get_qdrant_client(qdrant_url, qdrant_path)

    # 2. Fetch raw branch scores for telemetry inspection (dense cosine + sparse SPLADE dot product)
    dense_hits = client.query_points(
        collection_name=collection,
        query=q_dense_vec,
        using=DENSE_VECTOR_NAME,
        limit=prefetch_limit,
        with_payload=True,
    ).points
    sparse_hits = client.query_points(
        collection_name=collection,
        query=q_sparse_vec,
        using=SPARSE_VECTOR_NAME,
        limit=prefetch_limit,
        with_payload=True,
    ).points

    dense_score_map: dict[str, float] = {
        str(pt.payload["chunk_id"]): float(pt.score)
        for pt in dense_hits
        if pt.payload and "chunk_id" in pt.payload
    }
    sparse_score_map: dict[str, float] = {
        str(pt.payload["chunk_id"]): float(pt.score)
        for pt in sparse_hits
        if pt.payload and "chunk_id" in pt.payload
    }

    # 3. Execute Qdrant Universal Query API: Multi-Prefetch + Parameterized RRF Fusion
    fused_response = client.query_points(
        collection_name=collection,
        prefetch=[
            models.Prefetch(
                query=q_dense_vec,
                using=DENSE_VECTOR_NAME,
                limit=prefetch_limit,
            ),
            models.Prefetch(
                query=q_sparse_vec,
                using=SPARSE_VECTOR_NAME,
                limit=prefetch_limit,
            ),
        ],
        query=models.RrfQuery(
            rrf=models.Rrf(
                k=rrf_k,
                weights=[dense_weight, sparse_weight],
            )
        ),
        limit=top_k,
        with_payload=True,
    )

    client.close()

    candidates: list[RetrievedCandidate] = []
    for pt in fused_response.points:
        payload = pt.payload or {}
        cid = str(payload.get("chunk_id", pt.id))
        candidates.append(
            RetrievedCandidate(
                chunk_id=cid,
                doc_id=str(payload.get("doc_id", "unknown")),
                contextualized_text=str(payload.get("contextualized_text", "")),
                parent_markdown=str(payload.get("parent_markdown", "")),
                dense_score=round(dense_score_map.get(cid, 0.0), 4),
                sparse_score=round(sparse_score_map.get(cid, 0.0), 4),
                rrf_fused_score=round(float(pt.score), 6),
            )
        )

    output = Phase07RetrievedOutput(
        run_id=upstream.run_id,
        query_plan=upstream,
        candidates=candidates,
    )
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
