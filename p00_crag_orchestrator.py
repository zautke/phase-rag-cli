#!/usr/bin/env python3
# p00_crag_orchestrator.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from rag_contracts import (
    DEFAULT_CRAG_THRESHOLD,
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
        "[--rerank-model / -m MODEL] [--prefetch-limit / -l INT] [--rrf-k / -k INT] [--top-k / -K INT] "
        "[--top-n / -n INT] [--batch-size / -B INT] [--crag-threshold / -t FLOAT] [--max-retries / -r INT] "
        "[--quiet-children / -c] [--quiet / -s]\n"
        "Orchestrates autonomous CRAG query-rewrite loops across Phases 06 -> 09 and final evaluation in Phase 10.\n"
        "Input precedence: (1) explicit --in-file if provided; (2) stdin if piped; (3) default artifacts/05_indexed.json."
    )


def forward(**opts: object) -> list[str]:
    """`--kebab-name value` args for the options that are set; None is left to the child's own default/env."""
    return [x for k, v in opts.items() if v is not None for x in ("--" + k.replace("_", "-"), str(v))]


def invoke_cli_phase(
    script: str, input_json: str, args: list[str], quiet_child: bool
) -> str:
    """
    Spawns an isolated CLI phase subprocess, pipes validated JSON to its stdin,
    lets child stderr telemetry pass straight to the terminal, and captures stdout JSON.
    """
    script_dir = Path(__file__).resolve().parent
    target_script = (
        str(script_dir / script)
        if not Path(script).is_absolute()
        else script
    )

    cmd = [sys.executable, target_script, *args]
    if quiet_child:
        cmd.append("--quiet")

    # stderr is inherited: child Rich telemetry reaches the terminal live; only stdout JSON is captured
    proc = subprocess.run(
        cmd,
        input=input_json,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Subprocess {script} failed (exit {proc.returncode}); see its stderr above")
    return proc.stdout.strip()


def synthesize_rewritten_query(
    initial_query: str,
    current_query: str,
    attempt: int,
    p08_out: Phase08RerankedOutput,
    seen_terms: set[str],
) -> tuple[str, str] | None:
    """
    Diagnoses why the cross-encoder confidence fell below the CRAG threshold and
    synthesizes an expanded, disambiguated query for the next P06 -> P09 iteration.
    Returns None when the retrieved context has no new anchor terms (retrying cannot help).
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
    query_lower = current_query.lower()
    candidates = (
        raw_tok.strip(".,;:()[]{}<>\"'#*").lower()
        for item in p08_out.top_contexts
        for raw_tok in item.expanded_parent_context.replace("\n", " ").split()
    )
    anchor_terms = list(
        dict.fromkeys(
            c
            for c in candidates
            if len(c) >= 4 and c not in stop_words and c not in seen_terms and c not in query_lower
        )
    )[:4]
    if not anchor_terms:
        return None  # corpus offers nothing new: caller stops retrying
    seen_terms.update(anchor_terms)  # only the anchors actually used

    expansion = " ".join(anchor_terms)
    if attempt == 1:
        rewritten = f"{initial_query} (specifically addressing: {expansion})"
        top_score = (
            p08_out.top_contexts[0].cross_encoder_score
            if p08_out.top_contexts
            else 0.0
        )
        reason = (
            f"Attempt 1 confidence ({top_score:.4f}) < threshold; "
            f"injected corpus-grounded lexical anchors [{expansion.replace(' ', ', ')}]."
        )
    else:
        rewritten = (
            f"Technical architecture specification for {initial_query} including {expansion}"
        )
        reason = (
            f"Attempt {attempt} remained below threshold; reformulated into explicit "
            f"technical specification query with expanded terms [{expansion.replace(' ', ', ')}]."
        )

    return rewritten, reason


@app.command(epilog=Usage())
def main(
    ctx: typer.Context,
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
    ] = None,
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
        str | None,
        typer.Option(
            "--qdrant-path",
            "-p",
            help="Local persistent Qdrant path, forwarded to P07 only when given (else QDRANT_PATH / P07 default)",
        ),
    ] = None,
    rerank_backend: Annotated[
        str | None,
        typer.Option(
            "--rerank-backend",
            "-b",
            help="P08 reranker plugin (sentence_transformers|fastembed), forwarded only when given",
        ),
    ] = None,
    rerank_model: Annotated[
        str | None,
        typer.Option(
            "--rerank-model",
            "-m",
            help="P08 cross-encoder model, forwarded only when given",
        ),
    ] = None,
    prefetch_limit: Annotated[
        int | None,
        typer.Option("--prefetch-limit", "-l", help="P07 candidate pool per branch before RRF (forwarded only when given)"),
    ] = None,
    rrf_k: Annotated[
        int | None,
        typer.Option("--rrf-k", "-k", help="P07 Reciprocal Rank Fusion k constant (forwarded only when given)"),
    ] = None,
    top_k: Annotated[
        int | None,
        typer.Option("--top-k", "-K", help="P07 final fused candidates returned (forwarded only when given)"),
    ] = None,
    top_n: Annotated[
        int | None,
        typer.Option("--top-n", "-n", help="P08 final reranked contexts (forwarded only when given)"),
    ] = None,
    batch_size: Annotated[
        int | None,
        typer.Option("--batch-size", "-B", help="P08 cross-encoder batch size (forwarded only when given)"),
    ] = None,
    crag_threshold: Annotated[
        float,
        typer.Option(
            "--crag-threshold",
            "-t",
            envvar="RAG_CRAG_THRESHOLD",
            help="Minimum Cross-Encoder score required for GROUNDED verdict (P09 reads RAG_CRAG_THRESHOLD itself)",
        ),
    ] = DEFAULT_CRAG_THRESHOLD,
    max_retries: Annotated[
        int,
        typer.Option(
            "--max-retries",
            "-r",
            min=0,
            help="Retries after the first attempt (N retries = up to N+1 attempts) before forcing synthesis",
        ),
    ] = 2,
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
    # 1. Input precedence: explicit --in-file, then piped stdin, then artifacts/05_indexed.json fallback
    p05_indexed: Phase05IndexedOutput = cli_engine.load_upstream(
        in_file, Path("artifacts/05_indexed.json")
    )

    p05_json = p05_indexed.model_dump_json()

    current_query = query
    attempts_history: list[CRAGAttemptRecord] = []
    seen_expansion_terms: set[str] = set()

    p09_out: Phase09GenerationOutput | None = None
    converged = False

    artifacts_dir = out_file.resolve().parent

    def explicit(name: str) -> bool:
        # by enum name: typer >= 0.27 vendors its own click, so the enum class differs by version
        return getattr(ctx.get_parameter_source(name), "name", None) == "COMMANDLINE"

    # An option left to env/default is not forwarded: children resolve it from the same environment.
    max_attempts = max_retries + 1
    quiet_child = quiet_children or quiet
    for attempt in range(1, max_attempts + 1):
        attempt_dir = artifacts_dir / f"crag_attempt_{attempt}"
        attempt_dir.mkdir(parents=True, exist_ok=True)

        if not quiet:
            err_console.rule(
                f'[bold magenta]CRAG Loop Iteration {attempt}/{max_attempts}[/bold magenta] | Query: [yellow]"{escape(current_query)}"[/yellow]'
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
            quiet_child=quiet_child,
        )
        p06_out = Phase06QueryPlanOutput.model_validate_json(p06_raw)

        # --- Phase 07: Live Qdrant Hybrid Retrieval ---
        p07_args = forward(
            qdrant_path=qdrant_path,
            qdrant_url=qdrant_url if explicit("qdrant_url") else None,
            prefetch_limit=prefetch_limit,
            rrf_k=rrf_k,
            top_k=top_k,
            out_file=attempt_dir / "07_retrieved.json",
        )

        p07_raw = invoke_cli_phase(
            "p07_retrieve.py",
            input_json=p06_out.model_dump_json(),
            args=p07_args,
            quiet_child=quiet_child,
        )
        p07_out = Phase07RetrievedOutput.model_validate_json(p07_raw)

        # --- Phase 08: Live Cross-Encoder Reranking ---
        p08_raw = invoke_cli_phase(
            "p08_rerank.py",
            input_json=p07_out.model_dump_json(),
            args=forward(
                backend=rerank_backend,
                model=rerank_model,
                top_n=top_n,
                batch_size=batch_size,
                out_file=attempt_dir / "08_reranked.json",
            ),
            quiet_child=quiet_child,
        )
        p08_out = Phase08RerankedOutput.model_validate_json(p08_raw)

        # --- Phase 09: CRAG Verification & Synthesis ---
        p09_raw = invoke_cli_phase(
            "p09_generate.py",
            input_json=p08_out.model_dump_json(),
            args=forward(
                crag_threshold=crag_threshold if explicit("crag_threshold") else None,
                out_file=attempt_dir / "09_generated.json",
            ),
            quiet_child=quiet_child,
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
        rewrite = (
            synthesize_rewritten_query(
                initial_query=query,
                current_query=current_query,
                attempt=attempt,
                p08_out=p08_out,
                seen_terms=seen_expansion_terms,
            )
            if attempt < max_attempts
            else None
        )
        if attempt >= max_attempts:
            reason = "Max retries exhausted; proceeding with best available context."
        elif rewrite is None:
            reason = "No new corpus anchor terms to expand the query; stopping retries (not converged)."
        else:
            reason = rewrite[1]
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
        if rewrite is None:
            break
        current_query = rewrite[0]
        if not quiet:
            err_console.print(
                f"[bold red]⚠ CRAG Verdict: REWRITE_REQUIRED[/bold red] "
                f"(score={p09_out.grounded_confidence:.4f} < {crag_threshold:.4f})\n"
                f"[bold yellow]↻ Rewriting Query ->[/bold yellow] {escape(current_query)}"
            )

    if p09_out is None:
        raise RuntimeError("CRAG loop terminated without producing generation output.")

    # Copy winning attempt's Phase 09 artifact to canonical path under out_file's parent directory
    canonical_p09 = artifacts_dir / "09_generated.json"
    canonical_p09.parent.mkdir(parents=True, exist_ok=True)
    canonical_p09.write_text(
        p09_out.model_dump_json(indent=2), encoding="utf-8"
    )

    # --- Phase 10: Final RAG Triad Evaluation ---
    p10_raw = invoke_cli_phase(
        "p10_evaluate.py",
        input_json=p09_out.model_dump_json(),
        args=["--out-file", str(artifacts_dir / "10_evaluated.json")],
        quiet_child=quiet_child,
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
