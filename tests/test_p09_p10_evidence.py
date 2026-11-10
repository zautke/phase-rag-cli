"""D-E3: p09 keeps math/table/code evidence blocks verbatim; p10 faithfulness is a claim-support ratio.

Pure functions only: no model is loaded.
"""
from __future__ import annotations

import re

import p08_rerank
import p09_generate
import p10_evaluate
import rag_contracts as rc

PARENT = """### Doc > What happens when you introduce tags?
Consider three notes:
| Note | Tags |
|---|---|
| A | `#database` |
| B | `#database`, `#performance` |
Define a note-tag incidence matrix \\(X\\), where \\(X_{it}=1\\) when note i has tag t.
\\[
X=
\\begin{bmatrix}
1&0\\\\
1&1
\\end{bmatrix}
\\]
This is the adjacency information for a **bipartite graph**, with two disjoint classes of vertices.
$$ S = X X^\\top $$
```python
S = X @ X.T
```
Unrelated closing remark about wiki-links.
"""
QUERY = "What is the adjacency matrix of the tag bipartite graph?"


def _items(parent: str = PARENT) -> list[rc.RerankedContextItem]:
    return [
        rc.RerankedContextItem(chunk_id="c1", doc_id="d", cross_encoder_score=0.99, expanded_parent_context=parent),
        rc.RerankedContextItem(
            chunk_id="c2", doc_id="d", cross_encoder_score=0.5, expanded_parent_context="Other.\n| x | y |\n|---|---|"
        ),
    ]


def _answer(items: list[rc.RerankedContextItem]) -> tuple[str, list[str]]:
    return p09_generate.extract_grounded_answer(QUERY, items, 0.65, 0.99, "GROUNDED")


def test_split_evidence_blocks_finds_every_block_kind_verbatim() -> None:
    prose, blocks = p09_generate.split_evidence_blocks(PARENT)
    assert blocks[0] == "| Note | Tags |\n|---|---|\n| A | `#database` |\n| B | `#database`, `#performance` |"
    assert blocks[1].startswith("\\[\nX=\n\\begin{bmatrix}") and blocks[1].endswith("\\]")
    assert blocks[2] == "$$ S = X X^\\top $$"
    assert blocks[3] == "```python\nS = X @ X.T\n```"
    assert len(blocks) == 4
    assert "Consider three notes:" in prose and not any(line.startswith(("|", "\\", "$$", "`")) for line in prose)


def test_p09_answer_keeps_latex_table_and_code_blocks_of_top_context() -> None:
    ans, _ = _answer(_items())
    blocks = p09_generate.split_evidence_blocks(PARENT)[1]
    for block in blocks:
        assert f"{block}\n[d:c1]" in ans  # verbatim, followed by its citation
    assert "| x | y |" not in ans  # blocks come from the top-ranked context only


def test_p09_unclosed_fence_runs_to_end_and_dollar_block_spans_lines() -> None:
    _, blocks = p09_generate.split_evidence_blocks("intro\n```\ncode\nmore")
    assert blocks == ["```\ncode\nmore"]
    _, blocks = p09_generate.split_evidence_blocks("$$\na=b\n$$\nafter")
    assert blocks == ["$$\na=b\n$$"]


def test_p09_without_blocks_is_unchanged() -> None:
    ans, _ = _answer(_items("Hybrid retrieval combines dense and sparse vectors for the tag graph."))
    assert "\n" not in ans


def test_p10_faithfulness_is_one_for_a_real_p09_answer_with_blocks() -> None:
    items = _items()
    ans, cites = _answer(items)
    xml = p08_rerank.assemble_xml_context(items, reorder_litm=True)
    assert p10_evaluate.compute_faithfulness(ans, cites, xml) == 1.0


def test_p10_faithfulness_drops_for_an_unsupported_sentence() -> None:
    items = _items()
    ans, cites = _answer(items)
    xml = p08_rerank.assemble_xml_context(items, reorder_litm=True)
    claims = len(re.split("|".join(map(re.escape, cites)), ans)) - 1
    bad = ans + " The moon is made of cheese. " + cites[0]
    score = p10_evaluate.compute_faithfulness(bad, cites, xml)
    assert score == round(claims / (claims + 1), 4) < 1.0


def test_p10_faithfulness_zero_for_no_context_and_ignores_rewrite_lead_in() -> None:
    msg, cites = p09_generate.extract_grounded_answer("q", [], 0.8, 0.0, "REWRITE_REQUIRED")
    assert p10_evaluate.compute_faithfulness(msg, cites, "<retrieved_context>\n</retrieved_context>") == 0.0
    items = _items()
    ans, cites = p09_generate.extract_grounded_answer(QUERY, items, 0.999, 0.99, "REWRITE_REQUIRED")
    xml = p08_rerank.assemble_xml_context(items, reorder_litm=False)
    assert p10_evaluate.compute_faithfulness(ans, cites, xml) == 1.0


def test_p10_faithfulness_is_whitespace_insensitive_but_case_sensitive() -> None:
    xml = "<retrieved_context>\n    Alpha   beta\n    gamma.\n</retrieved_context>"
    assert p10_evaluate.compute_faithfulness("Verified grounded answer: Alpha beta gamma. [d:c]", ["[d:c]"], xml) == 1.0
    assert p10_evaluate.compute_faithfulness("Verified grounded answer: alpha beta gamma. [d:c]", ["[d:c]"], xml) == 0.0
