#!/usr/bin/env python3
# p00_crag_orchestrator.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from rag_contracts import (
    CRAGAttemptRecord,
    Phase05IndexedOutput,
    Phase06QueryPlanOutput,
    Phase07RetrievedOutput,
    Phase08RerankedOutput,
    Phase09GenerationOutput,
    Phase10EvalOutput,
    PhaseCLI,
    PhaseCRAGLoopOutput,
    err_console,
)

app = typer.Typer(add_completion=False)
cli_engine = PhaseCLI(
    "Phase 00: Autonomous CRAG Loopback Orchestrator (P06 -> P09 Cycle + P10)",
    Phase05IndexedOutput,
    PhaseCRAGLoopOutput,
    "artifacts/00_crag_loop_summary.json",
)


def Usage() -> str:
    return (
        "Usage: rag-p00 [--query / -q TEXT] [--in-file / -i PATH] [--out-file / -o PATH] "
        "[--qdrant-url / -u URL] [--qdrant-path / -p PATH] [--rerank-backend / -b BACKEND] "
        "[--rerank-model / -m MODEL] [--crag-threshold / -t FLOAT] [--max-retries / -r INT] "
        "[--quiet-children / -c] [--quiet / -s]\n"
        "Orchestrates autonomous CRAG query-rewrite loops across Phases 06 -> 09 and final evaluation in Phase 10."
    )


def invoke_cli_phase(
    script: str, input_json: str, args: list[str], quiet_child: bool
) -> str:
    """
    Spawns an isolated CLI phase subprocess, pipes validated JSON to its stdin,
    allows child stderr telemetry to pass straight to the terminal, and captures stdout JSON.
    """
    cmd = [sys.executable, script, *args]
    if quiet_child:
        cmd.append("--quiet")

    proc = subprocess.run(
        cmd,
        input=input_json,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    # Forward child's Rich stderr panels directly to our stderr console
    if proc.stderr:
        sys.stderr.write(proc.stderr)
        sys.stderr.flush()

    if proc.returncode != 0:
        raise RuntimeError(
            f"Subprocess {script} failed (exit {proc.returncode}):\n{proc.stderr}"
        )
    return proc.stdout.strip()


def synthesize_rewritten_query(
    initial_query: str,
    current_query: str,
    attempt: int,
    p08_out: Phase08RerankedOutput,
    seen_terms: set[str],
) -> tuple[str, str]:
    """
    Diagnoses why the cross-encoder confidence fell below the CRAG threshold and
    synthesizes an expanded, disambiguated query for the next P06 -> P09 iteration.
    """
    # Extract high-signal domain terms from the partial retrieved context that weren't in the query
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "what",
        "when",
        "where",
        "how",
        "does",
        "into",
        "before",
        "after",
        "below",
        "above",
        "document",
        "retrieved_context",
    }
    context_tokens: list[str] = []
    for item in p08_out.top_contexts:
        for raw_tok in item.expanded_parent_context.replace("\n", " ").split():
            clean = raw_tok.strip(".,;:()[]{}<>\"'#*").lower()
            if (
                len(clean) >= 4
                and clean not in stop_words
                and clean not in seen_terms
                and clean not in current_query.lower()
            ):
                context_tokens.append(clean)
                seen_terms.add(clean)

    # Pick top diagnostic anchor terms discovered in the corpus
    anchor_terms = context_tokens[:4]
    if attempt == 1:
        expansion = (
            " ".join(anchor_terms)
            if anchor_terms
            else "Qdrant HNSW dense SPLADE sparse Reciprocal Rank Fusion CRAG"
        )
        rewritten = f"{initial_query} (specifically addressing: {expansion})"
        top_score = (
            p08_out.top_contexts[0].cross_encoder_score
            if p08_out.top_contexts
            else 0.0
        )
        reason = (
            f"Attempt 1 confidence ({top_score:.4f}) < threshold; "
            f"injected corpus-grounded lexical anchors [{', '.join(anchor_terms) or 'domain defaults'}]."
        )
    else:
        expansion = (
            " ".join(anchor_terms)
            if anchor_terms
            else "cross-encoder score threshold query rewrite loop late chunking"
        )
        rewritten = (
            f"Technical architecture specification for {initial_query} including {expansion}"
        )
        reason = (
            f"Attempt {attempt} remained below threshold; reformulated into explicit "
            f"technical specification query with expanded terms [{', '.join(anchor_terms) or 'fallback expansion'}]."
        )

    return rewritten, reason


@app.command()
def main(
    query: Annotated[
        str,
        typer.Option(
            "--query",
            "-q",
            help="Initial user query (intentionally vague by default to demonstrate CRAG rewrite loop)",
        ),
    ] = "How are vectors combined and when does it retry?",
    in_file: Annotated[
        Path | None,
        typer.Option(
            "--in-file",
            "-i",
            help="Phase 05 Indexed output JSON (or pipe Phase 05 into stdin)",
        ),
    ] = Path("artifacts/05_indexed.json"),
    out_file: Annotated[
        Path,
        typer.Option(
            "--out-file",
            "-o",
            help="Output Phase 00 JSON summary path",
        ),
    ] = Path("artifacts/00_crag_loop_summary.json"),
    qdrant_url: Annotated[
        str | None,
        typer.Option(
            "--qdrant-url",
            "-u",
            envvar="QDRANT_URL",
            help="Remote Qdrant URL",
        ),
    ] = None,
    qdrant_path: Annotated[
        str,
        typer.Option(
            "--qdrant-path",
            "-p",
            help="Local persistent Qdrant path",
        ),
    ] = "./qdrant_storage",
    rerank_backend: Annotated[
        str,
        typer.Option(
            "--rerank-backend",
            "-b",
            help="Cross-Encoder backend ('transformers' or 'fastembed')",
        ),
    ] = "transformers",
    rerank_model: Annotated[
        str,
        typer.Option(
            "--rerank-model",
            "-m",
            help="Cross-Encoder model name",
        ),
    ] = "BAAI/bge-reranker-v2-m3",
    crag_threshold: Annotated[
        float,
        typer.Option(
            "--crag-threshold",
            "-t",
            help="Minimum Cross-Encoder score required for GROUNDED verdict",
        ),
    ] = 0.65,
    max_retries: Annotated[
        int,
        typer.Option(
            "--max-retries",
            "-r",
            help="Maximum CRAG loopback attempts before forcing synthesis",
        ),
    ] = 3,
    quiet_children: Annotated[
        bool,
        typer.Option(
            "--quiet-children",
            "-c",
            help="Suppress individual phase panels and only show CRAG loop table",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-s",
            help="Suppress stderr Rich output",
        ),
    ] = False,
) -> None:
    # 1. Validate upstream Phase 05 contract (either from --in-file or stdin pipe)
    p05_indexed: Phase05IndexedOutput = cli_engine.load_upstream(
        in_file if (in_file and in_file.exists() and sys.stdin.isatty()) else None
    )
    p05_json = p05_indexed.model_dump_json()

    current_query = query
    attempts_history: list[CRAGAttemptRecord] = []
    seen_expansion_terms: set[str] = set()

    p09_out: Phase09GenerationOutput | None = None
    converged = False

    for attempt in range(1, max_retries + 1):
        attempt_dir = Path(f"artifacts/crag_attempt_{attempt}")
        attempt_dir.mkdir(parents=True, exist_ok=True)

        if not quiet:
            err_console.rule(
                f'[bold magenta]CRAG Loop Iteration {attempt}/{max_retries}[/bold magenta] | Query: [yellow]"{current_query}"[/yellow]'
            )

        # --- Phase 06: Query Orchestration ---
        p06_raw = invoke_cli_phase(
            "p06_query.py",
            input_json=p05_json,
            args=[
                "--query",
                current_query,
                "--out-file",
                str(attempt_dir / "06_query_plan.json"),
            ],
            quiet_child=quiet_children,
        )
        p06_out = Phase06QueryPlanOutput.model_validate_json(p06_raw)

        # --- Phase 07: Live Qdrant Hybrid Retrieval ---
        p07_args = [
            "--qdrant-path",
            qdrant_path,
            "--out-file",
            str(attempt_dir / "07_retrieved.json"),
        ]
        if qdrant_url:
            p07_args.extend(["--qdrant-url", qdrant_url])

        p07_raw = invoke_cli_phase(
            "p07_retrieve.py",
            input_json=p06_out.model_dump_json(),
            args=p07_args,
            quiet_child=quiet_children,
        )
        p07_out = Phase07RetrievedOutput.model_validate_json(p07_raw)

        # --- Phase 08: Live Cross-Encoder Reranking ---
        p08_raw = invoke_cli_phase(
            "p08_rerank.py",
            input_json=p07_out.model_dump_json(),
            args=[
                "--backend",
                rerank_backend,
                "--model",
                rerank_model,
                "--out-file",
                str(attempt_dir / "08_reranked.json"),
            ],
            quiet_child=quiet_children,
        )
        p08_out = Phase08RerankedOutput.model_validate_json(p08_raw)

        # --- Phase 09: CRAG Verification & Synthesis ---
        p09_raw = invoke_cli_phase(
            "p09_generate.py",
            input_json=p08_out.model_dump_json(),
            args=[
                "--crag-threshold",
                str(crag_threshold),
                "--out-file",
                str(attempt_dir / "09_generated.json"),
            ],
            quiet_child=quiet_children,
        )
        p09_out = Phase09GenerationOutput.model_validate_json(p09_raw)

        # Check CRAG Verdict
        if p09_out.crag_verdict == "GROUNDED":
            attempts_history.append(
                CRAGAttemptRecord(
                    attempt=attempt,
                    query_used=current_query,
                    crag_verdict=p09_out.crag_verdict,
                    grounded_confidence=p09_out.grounded_confidence,
                    top_chunk_ids=[c.chunk_id for c in p08_out.top_contexts],
                    rewrite_reason="Passed CRAG threshold; no rewrite needed.",
                )
            )
            converged = True
            break

        # Verdict == REWRITE_REQUIRED
        if attempt < max_retries:
            next_query, reason = synthesize_rewritten_query(
                initial_query=query,
                current_query=current_query,
                attempt=attempt,
                p08_out=p08_out,
                seen_terms=seen_expansion_terms,
            )
            attempts_history.append(
                CRAGAttemptRecord(
                    attempt=attempt,
                    query_used=current_query,
                    crag_verdict=p09_out.crag_verdict,
                    grounded_confidence=p09_out.grounded_confidence,
                    top_chunk_ids=[c.chunk_id for c in p08_out.top_contexts],
                    rewrite_reason=reason,
                )
            )
            if not quiet:
                err_console.print(
                    f"[bold red]⚠ CRAG Verdict: REWRITE_REQUIRED[/bold red] "
                    f"(score={p09_out.grounded_confidence:.4f} < {crag_threshold:.4f})\n"
                    f"[bold yellow]↻ Rewriting Query ->[/bold yellow] {next_query}"
                )
            current_query = next_query
        else:
            attempts_history.append(
                CRAGAttemptRecord(
                    attempt=attempt,
                    query_used=current_query,
                    crag_verdict=p09_out.crag_verdict,
                    grounded_confidence=p09_out.grounded_confidence,
                    top_chunk_ids=[c.chunk_id for c in p08_out.top_contexts],
                    rewrite_reason="Max retries exhausted; proceeding with best available context.",
                )
            )

    assert p09_out is not None

    # Copy winning attempt's Phase 09 artifact to canonical path
    canonical_p09 = Path("artifacts/09_generated.json")
    canonical_p09.parent.mkdir(parents=True, exist_ok=True)
    canonical_p09.write_text(
        p09_out.model_dump_json(indent=2), encoding="utf-8"
    )

    # --- Phase 10: Final RAG Triad Evaluation ---
    p10_raw = invoke_cli_phase(
        "p10_evaluate.py",
        input_json=p09_out.model_dump_json(),
        args=["--out-file", "artifacts/10_evaluated.json"],
        quiet_child=quiet_children,
    )
    p10_out = Phase10EvalOutput.model_validate_json(p10_raw)

    # Render summary table of the CRAG Trajectory to stderr
    if not quiet:
        table = Table(
            title="CRAG Autonomous Query-Rewrite Trajectory", border_style="green"
        )
        table.add_column("Attempt", justify="center", style="cyan")
        table.add_column("Query Used", style="white")
        table.add_column("CE Score", justify="right", style="magenta")
        table.add_column("Verdict", justify="center")
        table.add_column("Action / Diagnostic", style="dim")

        for rec in attempts_history:
            badge = (
                "[bold green]GROUNDED[/bold green]"
                if rec.crag_verdict == "GROUNDED"
                else "[bold red]REWRITE_REQUIRED[/bold red]"
            )
            table.add_row(
                str(rec.attempt),
                rec.query_used,
                f"{rec.grounded_confidence:.4f}",
                badge,
                rec.rewrite_reason or "",
            )
        err_console.print(table)

    loop_output = PhaseCRAGLoopOutput(
        run_id=p05_indexed.run_id,
        initial_query=query,
        final_query=current_query,
        total_attempts=len(attempts_history),
        converged=converged,
        attempts_history=attempts_history,
        final_generation=p09_out,
        final_evaluation=p10_out,
    )
    cli_engine.emit(loop_output, out_file, quiet)


if __name__ == "__main__":
    app()
