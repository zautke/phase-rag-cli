#!/usr/bin/env python3
# p10_evaluate.py
import math
import re
from pathlib import Path
from typing import Annotated

import typer

from rag_contracts import Phase09GenerationOutput, Phase10EvalOutput, PhaseCLI

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 10: RAG Triad Telemetry & Evaluation",
    Phase09GenerationOutput,
    Phase10EvalOutput,
    "artifacts/10_evaluated.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p10 [--in-file / -i PATH] [--out-file / -o PATH] [--quiet / -q]\n"
        "Computes RAG Triad metrics (nDCG@k, Context Precision, Faithfulness, Answer Relevance) and emits Phase10EvalOutput."
    )


# Opening <document> tag lines emitted by P08 (exactly two-space indent, start of line): body text
# that merely looks like a tag is not matched.
DOCUMENT_TAG = re.compile(
    r'^ {2}<document\b[^>\n]*\brank="(\d+)"[^>\n]*\brerank_score="(-?[0-9.]+)"', re.MULTILINE
)


def compute_ndcg_at_k(xml_context_block: str) -> float:
    """
    Computes normalized Discounted Cumulative Gain (nDCG) of the contexts taken in cross-encoder
    rank order (the rank="N" attribute, not their physical order after Lost-in-the-Middle
    reordering), with rerank_score as gain, against the ideal descending-score order.
    """
    ranked = sorted((int(r), float(s)) for r, s in DOCUMENT_TAG.findall(xml_context_block))
    scores = [s for _, s in ranked]
    if not scores:
        return 0.0
    if len(scores) <= 1 or all(s == 0.0 for s in scores):
        return 1.0

    dcg = sum(score / math.log2(i + 2) for i, score in enumerate(scores))
    ideal_scores = sorted(scores, reverse=True)
    idcg = sum(score / math.log2(i + 2) for i, score in enumerate(ideal_scores))
    if idcg <= 0.0:
        return 1.0
    return round(min(1.0, max(0.0, dcg / idcg)), 4)


def compute_answer_relevance(query: str, answer: str) -> float:
    """
    Computes fraction of distinct query content terms (len >= 4, lowercased, stripped)
    present in the synthesized answer text.
    """
    q_terms = {
        t.strip(".,;:()[]{}<>\"'#*?!`").lower()
        for t in query.split()
        if len(t.strip(".,;:()[]{}<>\"'#*?!`")) >= 4
    }
    if not q_terms:
        return 1.0
    ans_lower = answer.lower()
    matches = sum(1 for term in q_terms if term in ans_lower)
    return round(matches / len(q_terms), 4)


# Templated lead-in P09 adds in front of the extracted claims; it is not a claim about the corpus.
ANSWER_PREFIX = re.compile(
    r"^\s*(?:Verified grounded answer:|Insufficient retrieval grounding:.*?Synthesizing partial context:)\s*",
    re.DOTALL,
)


def _squash(text: str) -> str:
    return " ".join(text.split())


def compute_faithfulness(answer: str, citations: list[str], xml_context_block: str) -> float:
    """
    Fraction of the answer's claims that appear verbatim in the retrieved contexts.

    faithfulness = supported / total, where a claim is one citation-delimited segment of the answer
    (an extracted sentence or a verbatim block; the P09 lead-in is dropped) and it is supported when
    its whitespace-normalized text is a substring of the whitespace-normalized `xml_context_block`
    (every cited context). An answer with no claim, or with text no context contains (for example the
    "No relevant context" message), scores 0.0; one fabricated sentence among four scores 0.75.
    """
    parts = re.split("|".join(re.escape(c) for c in citations), answer) if citations else [answer]
    parts[0] = ANSWER_PREFIX.sub("", parts[0], count=1)
    claims = [c for c in map(_squash, parts) if c]
    if not claims:
        return 0.0
    haystack = _squash(xml_context_block)
    return round(sum(c in haystack for c in claims) / len(claims), 4)


@app.command(epilog=Usage())
def main(
    in_file: Annotated[
        Path | None,
        typer.Option(
            "--in-file",
            "-i",
            help="Input Phase 09 JSON artifact (or pipe via stdin)",
        ),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option(
            "--out-file",
            "-o",
            help="Output Phase 10 JSON path",
        ),
    ] = Path("artifacts/10_evaluated.json"),
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress stderr Rich panel",
        ),
    ] = False,
) -> None:
    upstream: Phase09GenerationOutput = cli_engine.load_upstream(in_file)

    # 1. Reranking alignment / NDCG@k
    ndcg = compute_ndcg_at_k(upstream.xml_context_block)

    # 2. Faithfulness / Hallucination Detection
    faithfulness = compute_faithfulness(
        upstream.synthesized_answer, upstream.citations, upstream.xml_context_block
    )

    # 3. Answer Relevance
    answer_relevance = compute_answer_relevance(
        query=upstream.original_query, answer=upstream.synthesized_answer
    )

    output = Phase10EvalOutput(
        run_id=upstream.run_id,
        ndcg_at_k=ndcg,
        context_precision=round(upstream.grounded_confidence, 4),
        faithfulness_score=faithfulness,
        answer_relevance=answer_relevance,
        hallucination_detected=faithfulness < 0.75,
        final_answer=upstream.synthesized_answer,
    )
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
