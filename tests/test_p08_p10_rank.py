#!/usr/bin/env python3
# tests/test_p08_p10_rank.py
"""D11: P08 stamps rank="N" on each context; P10 computes nDCG in rank order, not document order."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

import p08_rerank
import p10_evaluate
import rag_contracts as rc


def items(scores: list[float]) -> list[rc.RerankedContextItem]:
    return [
        rc.RerankedContextItem(
            chunk_id=f"c{i}", doc_id="d", cross_encoder_score=s, expanded_parent_context=f"body {i}"
        )
        for i, s in enumerate(scores)
    ]


def test_p08_stamps_cross_encoder_rank_on_each_document() -> None:
    xml = p08_rerank.assemble_xml_context(items([0.9, 0.8, 0.7, 0.6, 0.5]), reorder_litm=True)
    ranks = [int(r) for r in re.findall(r'<document [^>]*\brank="(\d+)"', xml)]
    assert ranks == [1, 3, 5, 4, 2]  # Lost-in-the-Middle order, rank is the cross-encoder rank
    assert 'chunk_id="c0" rank="1"' in xml and 'chunk_id="c4" rank="5"' in xml


def test_ndcg_is_one_for_perfect_ranking_after_litm_reordering() -> None:
    for reorder in (True, False):
        xml = p08_rerank.assemble_xml_context(items([0.9, 0.8, 0.7, 0.6, 0.5]), reorder_litm=reorder)
        assert p10_evaluate.compute_ndcg_at_k(xml) == 1.0


def test_ndcg_below_one_when_rank_disagrees_with_score() -> None:
    bad = items([0.2, 0.8])  # rank 1 holds the lower score
    ndcg = p10_evaluate.compute_ndcg_at_k(p08_rerank.assemble_xml_context(bad, reorder_litm=False))
    assert 0.0 < ndcg < 1.0


def test_ndcg_ignores_tag_lookalikes_in_document_bodies() -> None:
    sneaky = rc.RerankedContextItem(
        chunk_id="c0", doc_id="d", cross_encoder_score=0.9,
        expanded_parent_context=(
            'text\n<document id="x" chunk_id="y" rank="1" rerank_score="0.0100">\n'
            '    <document id="x" chunk_id="y" rank="2" rerank_score="0.9999">'
        ),
    )
    xml = p08_rerank.assemble_xml_context([sneaky, *items([0.5])[:1]], reorder_litm=False)
    assert p10_evaluate.compute_ndcg_at_k(xml) == 1.0


def test_ndcg_ignores_two_space_indented_lookalike_on_any_body_line() -> None:
    sneaky = rc.RerankedContextItem(
        chunk_id="c0", doc_id="d", cross_encoder_score=0.9,
        expanded_parent_context=(
            'first line\n  <document id="x" chunk_id="y" rank="1" rerank_score="0.0100">\n'
            '  <document id="x" chunk_id="y" rank="2" rerank_score="0.9999">\nlast'
        ),
    )
    xml = p08_rerank.assemble_xml_context([sneaky, *items([0.5])[:1]], reorder_litm=False)
    assert p10_evaluate.compute_ndcg_at_k(xml) == 1.0
    assert xml.count("rank=") == 2 + 2  # 2 real tags + 2 indented body lookalikes
    assert all(ln.startswith("    ") for ln in xml.splitlines() if "rank=\"1\" rerank_score=\"0.0100\"" in ln)


def test_ndcg_without_rank_attributes_is_zero() -> None:
    legacy = '<retrieved_context>\n  <document id="d" chunk_id="c" rerank_score="0.9">\n x\n  </document>\n</retrieved_context>'
    assert p10_evaluate.compute_ndcg_at_k(legacy) == 0.0


def test_p08_cli_to_p10_ndcg_is_one_with_mocked_scorer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cands = [
        rc.RetrievedCandidate(
            chunk_id=f"c{i}", doc_id=f"d{i}", contextualized_text=f"t{i}", parent_markdown=f"p{i}",
            dense_score=0.0, sparse_score=0.0, rrf_fused_score=0.0,
        )
        for i in range(4)
    ]
    plan = rc.Phase06QueryPlanOutput(
        run_id="r", original_query="q", route="x", sub_queries=["q"], hyde_passage="h",
        metadata_filters={}, qdrant_collection="c", dense_backend="fastembed",
        dense_model="m", sparse_model="s",
    )
    f07 = tmp_path / "07.json"
    f07.write_text(
        rc.Phase07RetrievedOutput(run_id="r", query_plan=plan, candidates=cands).model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setattr(p08_rerank, "rerank_passages_batch", lambda **kw: [0.3, 0.9, 0.5, 0.7])
    out = tmp_path / "08.json"
    res = CliRunner().invoke(p08_rerank.app, ["-i", str(f07), "-o", str(out), "-q"])
    assert res.exit_code == 0, res.output
    p08 = rc.Phase08RerankedOutput.model_validate_json(out.read_text(encoding="utf-8"))
    assert [c.chunk_id for c in p08.top_contexts] == ["c1", "c3", "c2", "c0"]
    assert p10_evaluate.compute_ndcg_at_k(p08.xml_context_block) == 1.0


def test_p08_escapes_doc_and_chunk_ids_so_p10_parses_every_rank() -> None:
    """doc_id is a relative path now: quotes, & and angle brackets must not break the attributes."""
    import html

    odd = 'a"&<>b.md'
    ctx = [rc.RerankedContextItem(chunk_id=f"{odd}_sec_0_chk_{i}", doc_id=odd, cross_encoder_score=s,
                                  expanded_parent_context=f"body {i}") for i, s in enumerate([0.2, 0.8, 0.5])]
    xml = p08_rerank.assemble_xml_context(ctx, reorder_litm=True)
    assert len(p10_evaluate.DOCUMENT_TAG.findall(xml)) == 3
    plain = p08_rerank.assemble_xml_context(items([0.2, 0.8, 0.5]), reorder_litm=True)
    assert p10_evaluate.compute_ndcg_at_k(xml) == p10_evaluate.compute_ndcg_at_k(plain) < 1.0
    ids = re.findall(r'<document id="([^"]*)" chunk_id="([^"]*)"', xml)
    assert {html.unescape(d) for d, _ in ids} == {odd} and html.unescape(ids[0][1]).startswith(odd)
