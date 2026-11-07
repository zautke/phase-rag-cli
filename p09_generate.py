#!/usr/bin/env python3
# p09_generate.py
import re
from pathlib import Path
from typing import Annotated

import typer

from rag_contracts import (
    DEFAULT_CRAG_THRESHOLD,
    CragVerdict,
    Phase08RerankedOutput,
    Phase09GenerationOutput,
    PhaseCLI,
    RerankedContextItem,
)

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 09: CRAG Verification & Synthesis",
    Phase08RerankedOutput,
    Phase09GenerationOutput,
    "artifacts/09_generated.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p09 [--in-file / -i PATH] [--out-file / -o PATH] "
        "[--crag-threshold / -t FLOAT] [--quiet / -q]\n"
        "Evaluates Cross-Encoder confidence against the CRAG threshold and synthesizes grounded answers with citations."
    )


def extract_grounded_answer(
    query: str,
    top_contexts: list[RerankedContextItem],
    crag_threshold: float,
    max_score: float,
    verdict: CragVerdict,
) -> tuple[str, list[str]]:
    citations = [f"[{c.doc_id}:{c.chunk_id}]" for c in top_contexts]
    if not top_contexts:
        ans = (
            f"No relevant context retrieved. Verification score is 0.0000 "
            f"(threshold: {crag_threshold:.4f}); rewrite required."
        )
        return ans, []

    q_terms = {
        t.strip(".,;:()[]{}<>\"'#*?!`").lower()
        for t in query.split()
        if len(t.strip(".,;:()[]{}<>\"'#*?!`")) >= 4
    }

    candidate_sentences: list[tuple[int, float, str, str]] = []

    for item in top_contexts:
        citation = f"[{item.doc_id}:{item.chunk_id}]"
        lines = [
            line.strip()
            for line in item.expanded_parent_context.replace("\r", "").split("\n")
            if line.strip()
        ]
        for line in lines:
            clean_line = line.lstrip("#").strip()
            if not clean_line:
                continue
            parts = [
                p.strip()
                for p in re.split(r"(?<=[.!?])\s+", clean_line)
                if len(p.strip()) > 10
            ]
            for s in parts if parts else [clean_line]:
                s_terms = {w.strip(".,;:()[]{}<>\"'#*?!`").lower() for w in s.split()}
                overlap = len(q_terms & s_terms)
                candidate_sentences.append(
                    (overlap, item.cross_encoder_score, s, citation)
                )

    candidate_sentences.sort(key=lambda x: (x[0], x[1]), reverse=True)

    selected_sentences: list[str] = []
    seen_text: set[str] = set()
    for _, _, s, cit in candidate_sentences:
        norm = s.lower()
        if norm not in seen_text:
            seen_text.add(norm)
            selected_sentences.append(f"{s} {cit}")
        if len(selected_sentences) >= 3:
            break

    body = (
        " ".join(selected_sentences)
        if selected_sentences
        else (
            top_contexts[0].expanded_parent_context.strip()
            + f" [{top_contexts[0].doc_id}:{top_contexts[0].chunk_id}]"
        )
    )

    if verdict == "REWRITE_REQUIRED":
        prefix = (
            f"Insufficient retrieval grounding: maximum confidence score is {max_score:.4f}, "
            f"which is below the required CRAG threshold of {crag_threshold:.4f}. "
            f"Synthesizing partial context: "
        )
        synthesized = prefix + body
    else:
        synthesized = f"Verified grounded answer: {body}"

    return synthesized, citations


@app.command(epilog=Usage())
def main(
    in_file: Annotated[
        Path | None,
        typer.Option(
            "--in-file",
            "-i",
            help="Input Phase 08 JSON artifact (or pipe via stdin)",
        ),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option(
            "--out-file",
            "-o",
            help="Output Phase 09 JSON path",
        ),
    ] = Path("artifacts/09_generated.json"),
    crag_threshold: Annotated[
        float,
        typer.Option(
            "--crag-threshold",
            "-t",
            envvar="RAG_CRAG_THRESHOLD",
            help="Minimum Cross-Encoder score required for GROUNDED verdict",
        ),
    ] = DEFAULT_CRAG_THRESHOLD,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress stderr Rich panel",
        ),
    ] = False,
) -> None:
    upstream: Phase08RerankedOutput = cli_engine.load_upstream(in_file)
    max_score = max(
        (c.cross_encoder_score for c in upstream.top_contexts), default=0.0
    )
    verdict: CragVerdict = "GROUNDED" if max_score >= crag_threshold else "REWRITE_REQUIRED"

    synthesized, citations = extract_grounded_answer(
        query=upstream.original_query,
        top_contexts=upstream.top_contexts,
        crag_threshold=crag_threshold,
        max_score=max_score,
        verdict=verdict,
    )

    output = Phase09GenerationOutput(
        run_id=upstream.run_id,
        original_query=upstream.original_query,
        crag_verdict=verdict,
        grounded_confidence=max_score,
        synthesized_answer=synthesized,
        citations=citations,
        xml_context_block=upstream.xml_context_block,
    )
    cli_engine.emit(output, out_file, quiet)


if __name__ == "__main__":
    app()
