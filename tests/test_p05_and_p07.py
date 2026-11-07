#!/usr/bin/env python3
# tests/test_p05_and_p07.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import hybrid_engine
import p05_index
import p07_retrieve
import rag_contracts as rc


def test_contract_chain_p05_and_p07() -> None:
    assert p05_index.cli_engine.input_model is rc.Phase04ChunkedOutput
    assert p05_index.cli_engine.output_model is rc.Phase05IndexedOutput
    assert p07_retrieve.cli_engine.input_model is rc.Phase06QueryPlanOutput
    assert p07_retrieve.cli_engine.output_model is rc.Phase07RetrievedOutput


def test_deterministic_point_uuid_and_sigmoid_calibration() -> None:
    u1 = hybrid_engine.deterministic_point_uuid("doc1_sec0_chk_0")
    u2 = hybrid_engine.deterministic_point_uuid("doc1_sec0_chk_0")
    u3 = hybrid_engine.deterministic_point_uuid("doc1_sec0_chk_1")
    assert u1 == u2
    assert u1 != u3
    assert len(u1) == 36

    assert abs(hybrid_engine._sigmoid(0.0) - 0.5) < 1e-6
    assert hybrid_engine._sigmoid(25.0) > 0.999
    assert hybrid_engine._sigmoid(-25.0) < 0.001


@pytest.mark.live
def test_live_p05_index_and_p07_retrieve_end_to_end(tmp_path: Path) -> None:
    """
    Test live p05_index.py and p07_retrieve.py against a temporary Qdrant storage directory.
    Verifies 1024-d Jina-v3 dense vectors, non-empty SPLADE sparse indices/values,
    Qdrant RrfQuery fusion scores, client.close() lock release, and Tri-Plex I/O contract.
    """
    root = Path(__file__).resolve().parent.parent
    qdrant_dir = tmp_path / "qdrant"
    f04 = tmp_path / "04_chunked.json"
    f05 = tmp_path / "05_indexed.json"
    f06 = tmp_path / "06_query_plan.json"
    f07 = tmp_path / "07_retrieved.json"

    # Build Phase 04 input fixture with 3 distinct technical chunks
    p04_payload = rc.Phase04ChunkedOutput(
        run_id="20261031T120000Z",
        chunks=[
            rc.DocumentChunk(
                chunk_id="doc_arch_01_sec_00_chk_0",
                parent_section_id="doc_arch_01_sec_00",
                doc_id="doc_arch_01",
                text=(
                    "Combine Qdrant HNSW dense vectors (jina-embeddings-v3) with SPLADE sparse "
                    "vectors using Reciprocal Rank Fusion (k=60)."
                ),
                token_count=17,
                header_hierarchy=["Hybrid RAG Architecture"],
                parent_markdown=(
                    "### Hybrid RAG Architecture\nCombine Qdrant HNSW dense vectors "
                    "(jina-embeddings-v3) with SPLADE sparse vectors using Reciprocal Rank Fusion (k=60)."
                ),
            ),
            rc.DocumentChunk(
                chunk_id="doc_arch_01_sec_01_chk_0",
                parent_section_id="doc_arch_01_sec_01",
                doc_id="doc_arch_01",
                text=(
                    "Apply long-context token pooling before segmentation to preserve "
                    "cross-paragraph anaphora."
                ),
                token_count=11,
                header_hierarchy=["Hybrid RAG Architecture", "Late Chunking"],
                parent_markdown=(
                    "### Hybrid RAG Architecture > Late Chunking\nApply long-context token "
                    "pooling before segmentation to preserve cross-paragraph anaphora."
                ),
            ),
            rc.DocumentChunk(
                chunk_id="doc_sec_02_sec_00_chk_0",
                parent_section_id="doc_sec_02_sec_00",
                doc_id="doc_sec_02",
                text=(
                    "If the cross-encoder score falls below 0.65, trigger a query rewrite loop "
                    "before invoking the generator LLM."
                ),
                token_count=18,
                header_hierarchy=["Corrective RAG (CRAG)"],
                parent_markdown=(
                    "### Corrective RAG (CRAG)\nIf the cross-encoder score falls below 0.65, "
                    "trigger a query rewrite loop before invoking the generator LLM."
                ),
            ),
        ],
    )
    f04.write_text(p04_payload.model_dump_json(indent=2), encoding="utf-8")

    # 1. Execute Phase 05 via CLI subprocess with short flags
    proc05 = subprocess.run(
        [
            sys.executable,
            str(root / "p05_index.py"),
            "-i",
            str(f04),
            "-o",
            str(f05),
            "-c",
            "test_hybrid_collection",
            "-p",
            str(qdrant_dir),
            "-r",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert f05.exists()
    assert "Phase 05: Live Jina-v3 + SPLADE Hybrid Qdrant Indexing" in proc05.stderr

    out05_stdout = rc.Phase05IndexedOutput.model_validate_json(proc05.stdout)
    out05_disk = rc.Phase05IndexedOutput.model_validate_json(f05.read_text(encoding="utf-8"))
    assert out05_stdout.model_dump() == out05_disk.model_dump()
    assert out05_disk.qdrant_collection == "test_hybrid_collection"
    assert len(out05_disk.indexed_records) == 3

    for rec in out05_disk.indexed_records:
        assert rec.contextualized_text.startswith(f"[Doc: {rec.doc_id} | Section: ")
        assert len(rec.dense_vector) == 1024
        assert all(isinstance(v, float) for v in rec.dense_vector)
        assert len(rec.sparse_indices) > 0
        assert len(rec.sparse_indices) == len(rec.sparse_values)
        assert all(isinstance(i, int) for i in rec.sparse_indices)
        assert all(isinstance(v, float) for v in rec.sparse_values)

    # 2. Construct Phase 06 Query Plan output carrying the Phase 05 qdrant_collection
    query_str = "How does Hybrid RAG fuse dense and sparse vectors using Reciprocal Rank Fusion?"
    p06_payload = rc.Phase06QueryPlanOutput(
        run_id=out05_disk.run_id,
        original_query=query_str,
        route="hybrid_rag",
        sub_queries=[
            f"{query_str} (semantic architecture & theory)",
            f"{query_str} (exact parameters, thresholds, & implementation)",
        ],
        hyde_passage=(
            f"Hypothetical Technical Excerpt for '{query_str}': A production RAG system "
            "combines Qdrant HNSW dense embeddings with SPLADE sparse lexical vectors fused via "
            "Reciprocal Rank Fusion (RRF k=60), followed by cross-encoder reranking and CRAG "
            "threshold verification."
        ),
        metadata_filters={"status": "production_verified"},
        qdrant_collection=out05_disk.qdrant_collection,
        dense_backend=out05_disk.dense_backend,
        dense_model=out05_disk.dense_model,
        sparse_model=out05_disk.sparse_model,
    )
    f06.write_text(p06_payload.model_dump_json(indent=2), encoding="utf-8")

    # 3. Execute Phase 07 via CLI subprocess with short flags
    proc07 = subprocess.run(
        [
            sys.executable,
            str(root / "p07_retrieve.py"),
            "-i",
            str(f06),
            "-o",
            str(f07),
            "-p",
            str(qdrant_dir),
            "-l",
            "10",
            "-k",
            "60",
            "-d",
            "1.0",
            "-s",
            "1.0",
            "-t",
            "3",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert f07.exists()
    assert "Phase 07: Live Qdrant Hybrid Prefetch + RRF Fusion" in proc07.stderr

    out07_stdout = rc.Phase07RetrievedOutput.model_validate_json(proc07.stdout)
    out07_disk = rc.Phase07RetrievedOutput.model_validate_json(f07.read_text(encoding="utf-8"))
    assert out07_stdout.model_dump() == out07_disk.model_dump()
    assert len(out07_disk.candidates) == 3

    # Top candidate must be the Hybrid RAG Architecture chunk
    top_cand = out07_disk.candidates[0]
    assert top_cand.chunk_id == "doc_arch_01_sec_00_chk_0"
    assert top_cand.dense_score > 0.0
    assert top_cand.sparse_score > 0.0
    assert top_cand.rrf_fused_score > 0.0

    # Verify RRF scores are sorted descending
    rrf_scores = [c.rrf_fused_score for c in out07_disk.candidates]
    assert rrf_scores == sorted(rrf_scores, reverse=True)
