#!/usr/bin/env python3
# tests/test_p06_p08_p09_p10_p00.py
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import p00_crag_orchestrator
import p06_query
import p08_rerank
import p09_generate
import p10_evaluate
import rag_contracts as rc


def test_ast_no_bare_print_in_task3_modules() -> None:
    """Ensure zero bare print() calls exist in p06, p08, p09, p10, and p00."""
    root = Path(__file__).resolve().parent.parent
    for fname in (
        "p06_query.py",
        "p08_rerank.py",
        "p09_generate.py",
        "p10_evaluate.py",
        "p00_crag_orchestrator.py",
    ):
        fpath = root / fname
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=fname)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                pytest.fail(f"Bare print() found in {fname}:{node.lineno}")


def test_usage_and_contracts_task3_modules() -> None:
    """Verify Usage() and PhaseCLI contracts across p06, p08, p09, p10, and p00."""
    for mod in (
        p06_query,
        p08_rerank,
        p09_generate,
        p10_evaluate,
        p00_crag_orchestrator,
    ):
        assert hasattr(mod, "Usage")
        usage_text = mod.Usage()
        assert isinstance(usage_text, str) and "Usage:" in usage_text

    assert p06_query.cli_engine.input_model is rc.Phase05IndexedOutput
    assert p06_query.cli_engine.output_model is rc.Phase06QueryPlanOutput

    assert p08_rerank.cli_engine.input_model is rc.Phase07RetrievedOutput
    assert p08_rerank.cli_engine.output_model is rc.Phase08RerankedOutput

    assert p09_generate.cli_engine.input_model is rc.Phase08RerankedOutput
    assert p09_generate.cli_engine.output_model is rc.Phase09GenerationOutput

    assert p10_evaluate.cli_engine.input_model is rc.Phase09GenerationOutput
    assert p10_evaluate.cli_engine.output_model is rc.Phase10EvalOutput

    assert p00_crag_orchestrator.cli_engine.input_model is rc.Phase05IndexedOutput
    assert p00_crag_orchestrator.cli_engine.output_model is rc.PhaseCRAGLoopOutput


def test_lost_in_the_middle_and_query_rewriter_helpers() -> None:
    """Verify apply_lost_in_the_middle_ordering and synthesize_rewritten_query."""
    items = [
        rc.RerankedContextItem(
            chunk_id=f"c{i}",
            doc_id="doc1",
            cross_encoder_score=round(0.9 - i * 0.1, 4),
            expanded_parent_context=f"Parent section {i} about Qdrant HNSW SPLADE RRF fusion.",
        )
        for i in range(5)
    ]
    reordered = p08_rerank.apply_lost_in_the_middle_ordering(items)
    # idx 0, 2, 4 on left -> c0, c2, c4; idx 1, 3 reversed on right -> c3, c1
    assert [it.chunk_id for it in reordered] == ["c0", "c2", "c4", "c3", "c1"]

    # 2 or fewer items unchanged
    assert p08_rerank.apply_lost_in_the_middle_ordering(items[:2]) == items[:2]

    p08_sample = rc.Phase08RerankedOutput(
        run_id="20261031T120000Z",
        original_query="How are things combined?",
        xml_context_block="<retrieved_context></retrieved_context>",
        top_contexts=items[:2],
    )
    seen: set[str] = set()
    q1, reason1 = p00_crag_orchestrator.synthesize_rewritten_query(
        initial_query="How are things combined?",
        current_query="How are things combined?",
        attempt=1,
        p08_out=p08_sample,
        seen_terms=seen,
    )
    assert "specifically addressing:" in q1
    assert "Attempt 1 confidence" in reason1
    assert len(seen) > 0

    q2, reason2 = p00_crag_orchestrator.synthesize_rewritten_query(
        initial_query="How are things combined?",
        current_query=q1,
        attempt=2,
        p08_out=p08_sample,
        seen_terms=seen,
    )
    assert "Technical architecture specification" in q2
    assert "Attempt 2 remained below threshold" in reason2


def test_ndcg_and_answer_relevance_unit() -> None:
    """Unit test new computed nDCG and answer relevance metrics in p10."""
    xml_ideal = (
        '<retrieved_context>\n'
        '  <document id="d1" chunk_id="c1" rerank_score="0.9">\n    ctx\n  </document>\n'
        '  <document id="d2" chunk_id="c2" rerank_score="0.5">\n    ctx\n  </document>\n'
        '</retrieved_context>'
    )
    assert p10_evaluate.compute_ndcg_at_k(xml_ideal) == 1.0

    xml_inverted = (
        '<retrieved_context>\n'
        '  <document id="d1" chunk_id="c1" rerank_score="0.2">\n    ctx\n  </document>\n'
        '  <document id="d2" chunk_id="c2" rerank_score="0.8">\n    ctx\n  </document>\n'
        '</retrieved_context>'
    )
    ndcg_inv = p10_evaluate.compute_ndcg_at_k(xml_inverted)
    assert 0.0 < ndcg_inv < 1.0

    assert p10_evaluate.compute_ndcg_at_k("<retrieved_context></retrieved_context>") == 0.0

    q = "How does hybrid retrieval combine dense and sparse?"
    ans_good = "Hybrid retrieval uses dense vectors and sparse indices to combine candidate sets."
    relevance_good = p10_evaluate.compute_answer_relevance(q, ans_good)
    assert relevance_good > 0.5

    ans_poor = "Nothing related here."
    relevance_poor = p10_evaluate.compute_answer_relevance(q, ans_poor)
    assert relevance_poor == 0.0


def test_p09_extractive_grounding_unit() -> None:
    """Unit test p09 extractive grounding under GROUNDED, REWRITE_REQUIRED, and empty contexts."""
    items = [
        rc.RerankedContextItem(
            chunk_id="chk_0",
            doc_id="doc_0",
            cross_encoder_score=0.88,
            expanded_parent_context="### Section 1\nHybrid RAG fuses dense embeddings and SPLADE sparse vectors. Reciprocal rank fusion merges them cleanly.",
        )
    ]
    ans_grounded, citations = p09_generate.extract_grounded_answer(
        query="How does Hybrid RAG fuse dense and sparse vectors?",
        top_contexts=items,
        crag_threshold=0.70,
        max_score=0.88,
        verdict="GROUNDED",
    )
    assert "Verified grounded answer:" in ans_grounded
    assert "[doc_0:chk_0]" in ans_grounded
    assert citations == ["[doc_0:chk_0]"]

    ans_rewrite, _ = p09_generate.extract_grounded_answer(
        query="How does Hybrid RAG fuse dense and sparse vectors?",
        top_contexts=items,
        crag_threshold=0.95,
        max_score=0.88,
        verdict="REWRITE_REQUIRED",
    )
    assert "Insufficient retrieval grounding: maximum confidence score is 0.8800" in ans_rewrite
    assert "below the required CRAG threshold of 0.9500" in ans_rewrite

    ans_empty, cit_empty = p09_generate.extract_grounded_answer(
        query="test query",
        top_contexts=[],
        crag_threshold=0.80,
        max_score=0.0,
        verdict="REWRITE_REQUIRED",
    )
    assert "No relevant context retrieved" in ans_empty
    assert cit_empty == []


def test_end_to_end_p06_p08_p09_p10_and_p00_loop(tmp_path: Path) -> None:
    """
    Test p06_query.py, p08_rerank.py (with fastembed backend), p09_generate.py,
    p10_evaluate.py, and p00_crag_orchestrator.py end-to-end.
    """
    root = Path(__file__).resolve().parent.parent
    qdrant_dir = tmp_path / "qdrant"
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    f04 = artifacts_dir / "04_chunked.json"
    f05 = artifacts_dir / "05_indexed.json"
    f06 = artifacts_dir / "06_query_plan.json"
    f07 = artifacts_dir / "07_retrieved.json"
    f08 = artifacts_dir / "08_reranked.json"
    f09 = artifacts_dir / "09_generated.json"
    f10 = artifacts_dir / "10_evaluated.json"
    f00 = artifacts_dir / "00_crag_loop_summary.json"

    # Build Phase 04 input fixture
    p04_payload = rc.Phase04ChunkedOutput(
        run_id="20261031T130000Z",
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
                chunk_id="doc_arch_01_sec_00_chk_1",
                parent_section_id="doc_arch_01_sec_00",
                doc_id="doc_arch_01",
                text="Duplicate child chunk sharing the same parent section for deduplication testing.",
                token_count=11,
                header_hierarchy=["Hybrid RAG Architecture"],
                parent_markdown=(
                    "### Hybrid RAG Architecture\nCombine Qdrant HNSW dense vectors "
                    "(jina-embeddings-v3) with SPLADE sparse vectors using Reciprocal Rank Fusion (k=60)."
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

    # 1. Index via p05_index.py
    subprocess.run(
        [
            sys.executable,
            str(root / "p05_index.py"),
            "-i",
            str(f04),
            "-o",
            str(f05),
            "-c",
            "test_task3_collection",
            "-p",
            str(qdrant_dir),
            "-q",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert f05.exists()

    # 2. Run p06_query.py
    proc06 = subprocess.run(
        [
            sys.executable,
            str(root / "p06_query.py"),
            "-i",
            str(f05),
            "-o",
            str(f06),
            "-q",
            "How does Hybrid RAG fuse dense and sparse vectors and when does CRAG rewrite?",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    out06 = rc.Phase06QueryPlanOutput.model_validate_json(proc06.stdout)
    assert len(out06.sub_queries) >= 2
    assert "Hybrid RAG" in out06.hyde_passage
    assert out06.metadata_filters["collection"] == "test_task3_collection"

    # 3. Run p07_retrieve.py
    subprocess.run(
        [
            sys.executable,
            str(root / "p07_retrieve.py"),
            "-i",
            str(f06),
            "-o",
            str(f07),
            "-p",
            str(qdrant_dir),
            "-q",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert f07.exists()

    # 4. Run p08_rerank.py with fastembed backend
    proc08 = subprocess.run(
        [
            sys.executable,
            str(root / "p08_rerank.py"),
            "-i",
            str(f07),
            "-o",
            str(f08),
            "-b",
            "fastembed",
            "-m",
            "jinaai/jina-reranker-v2-base-multilingual",
            "-n",
            "4",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    out08 = rc.Phase08RerankedOutput.model_validate_json(proc08.stdout)
    assert out08.xml_context_block.startswith("<retrieved_context>")
    assert out08.xml_context_block.endswith("</retrieved_context>")
    # Because dedupe_parents=True by default, the 2 chunks sharing doc_arch_01's parent section deduplicate to 1
    assert len(out08.top_contexts) == 2
    assert (
        out08.top_contexts[0].cross_encoder_score
        >= out08.top_contexts[1].cross_encoder_score
    )

    # 5. Run p09_generate.py (test GROUNDED verdict)
    proc09 = subprocess.run(
        [
            sys.executable,
            str(root / "p09_generate.py"),
            "-i",
            str(f08),
            "-o",
            str(f09),
            "-t",
            "0.10",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    out09 = rc.Phase09GenerationOutput.model_validate_json(proc09.stdout)
    assert out09.crag_verdict == "GROUNDED"
    assert len(out09.citations) == 2
    assert "Hybrid RAG" in out09.synthesized_answer
    assert "Verified grounded answer:" in out09.synthesized_answer

    # 6. Run p10_evaluate.py
    proc10 = subprocess.run(
        [
            sys.executable,
            str(root / "p10_evaluate.py"),
            "-i",
            str(f09),
            "-o",
            str(f10),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    out10 = rc.Phase10EvalOutput.model_validate_json(proc10.stdout)
    assert 0.0 <= out10.ndcg_at_k <= 1.0
    assert 0.0 <= out10.faithfulness_score <= 1.0
    assert 0.0 <= out10.answer_relevance <= 1.0
    assert out10.final_answer == out09.synthesized_answer

    # 7. Run p00_crag_orchestrator.py with high threshold (0.9999) to exercise multi-attempt rewrite loop
    # Test running from a non-repo CWD (tmp_path) and piping empty stdin (non-TTY)
    external_dir = tmp_path / "somewhere_else"
    external_dir.mkdir()

    proc00 = subprocess.run(
        [
            sys.executable,
            str(root / "p00_crag_orchestrator.py"),
            "-i",
            str(f05),
            "-o",
            str(f00),
            "-q",
            "How are things combined and retried?",
            "-p",
            str(qdrant_dir),
            "-b",
            "fastembed",
            "-m",
            "jinaai/jina-reranker-v2-base-multilingual",
            "-t",
            "0.9999",
            "-r",
            "2",
            "-c",
        ],
        cwd=str(external_dir),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    out00 = rc.PhaseCRAGLoopOutput.model_validate_json(proc00.stdout)
    assert out00.total_attempts == 2
    assert len(out00.attempts_history) == 2
    assert out00.attempts_history[0].crag_verdict == "REWRITE_REQUIRED"
    assert out00.final_query != out00.initial_query

    # Verify attempt artifacts exist under out_file.parent
    assert (artifacts_dir / "crag_attempt_1" / "06_query_plan.json").exists()
    assert (artifacts_dir / "crag_attempt_1" / "07_retrieved.json").exists()
    assert (artifacts_dir / "crag_attempt_1" / "08_reranked.json").exists()
    assert (artifacts_dir / "crag_attempt_1" / "09_generated.json").exists()
    assert (artifacts_dir / "crag_attempt_2" / "06_query_plan.json").exists()
    assert (artifacts_dir / "crag_attempt_2" / "07_retrieved.json").exists()
    assert (artifacts_dir / "crag_attempt_2" / "08_reranked.json").exists()
    assert (artifacts_dir / "crag_attempt_2" / "09_generated.json").exists()
    assert (artifacts_dir / "09_generated.json").exists()
    assert (artifacts_dir / "10_evaluated.json").exists()
    assert f00.exists()


def test_resolve_rerank_model_wires_fastembed_default() -> None:
    from hybrid_engine import (
        DEFAULT_FASTEMBED_RERANK_MODEL,
        DEFAULT_RERANK_MODEL,
        resolve_rerank_model,
    )

    assert resolve_rerank_model(DEFAULT_RERANK_MODEL, "fastembed") == DEFAULT_FASTEMBED_RERANK_MODEL
    assert resolve_rerank_model(DEFAULT_RERANK_MODEL, "transformers") == DEFAULT_RERANK_MODEL
    assert resolve_rerank_model("custom/model", "fastembed") == "custom/model"


def test_p00_forwards_p07_p08_knobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    p05 = rc.Phase05IndexedOutput(
        run_id="r", qdrant_collection="c", indexed_records=[],
        dense_backend="sentence_transformers", dense_model="d", sparse_model="s",
    )
    f05 = tmp_path / "05.json"
    f05.write_text(p05.model_dump_json(), encoding="utf-8")
    plan = rc.Phase06QueryPlanOutput(
        run_id="r",
        original_query="q",
        route="hybrid_rag",
        sub_queries=["q"],
        hyde_passage="h",
        metadata_filters={},
        qdrant_collection="c",
        dense_backend="sentence_transformers",
        dense_model="d",
        sparse_model="s",
    )
    p07 = rc.Phase07RetrievedOutput(run_id="r", query_plan=plan, candidates=[])
    calls: dict[str, list[str]] = {}

    class Stop(Exception):
        pass

    def fake(script: str, input_json: str, args: list[str], quiet_child: bool) -> str:
        calls[script] = args
        if script == "p06_query.py":
            return plan.model_dump_json()
        if script == "p07_retrieve.py":
            return p07.model_dump_json()
        raise Stop

    monkeypatch.setattr(p00_crag_orchestrator, "invoke_cli_phase", fake)
    res = CliRunner().invoke(
        p00_crag_orchestrator.app,
        ["-i", str(f05), "-o", str(tmp_path / "00.json"), "-l", "7", "-k", "33", "-K", "4",
         "-n", "2", "-B", "8", "-s"],
    )
    assert isinstance(res.exception, Stop)
    a07, a08 = calls["p07_retrieve.py"], calls["p08_rerank.py"]
    assert a07[a07.index("--prefetch-limit") + 1] == "7"
    assert a07[a07.index("--rrf-k") + 1] == "33"
    assert a07[a07.index("--top-k") + 1] == "4"
    assert a08[a08.index("--top-n") + 1] == "2"
    assert a08[a08.index("--batch-size") + 1] == "8"
