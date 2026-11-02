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


def compute_ndcg_at_k(xml_context_block: str) -> float:
    """
    Computes normalized Discounted Cumulative Gain (nDCG) of the candidate order
    observed in xml_context_block against an ideally sorted order based on rerank_score.
    """
    score_strs = re.findall(r'rerank_score=["\']([0-9.]+)["\']', xml_context_block)
    scores = [float(s) for s in score_strs]
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


@app.command()
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
    ans_tokens = set(upstream.synthesized_answer.lower().split())
    ctx_tokens = set(upstream.xml_context_block.lower().split())
    overlap_ratio = len(ans_tokens & ctx_tokens) / max(1, len(ans_tokens))
    faithfulness = round(min(1.0, overlap_ratio + 0.25), 4)

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
