#!/usr/bin/env python3
# rag_contracts.py
from __future__ import annotations

import contextlib
import io
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

import typer
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax


def ensure_utf8_streams() -> None:
    """Reconfigure sys.stdin, sys.stdout, and sys.stderr to use utf-8 on Windows and POSIX."""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if isinstance(stream, io.TextIOWrapper):
            with contextlib.suppress( OSError, ValueError):
                stream.reconfigure(encoding="utf-8")


# Console strictly targets stderr so stdout remains a pure JSON pipe
err_console = Console(stderr=True)


class BasePhasePayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    run_id: str = Field(
        default_factory=lambda: datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    )
    phase_name: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# --- INGESTION SCHEMAS (Phases 1 - 5) ---
class RawDocument(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    doc_id: str
    source_uri: str
    mime_type: str
    raw_content: str


class Phase01LoadedOutput(BasePhasePayload):
    phase_name: str = "01_loading"
    documents: list[RawDocument]


class MarkdownDocument(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    doc_id: str
    source_uri: str
    clean_markdown: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)


class Phase02MarkdownOutput(BasePhasePayload):
    phase_name: str = "02_preprocess_md"
    documents: list[MarkdownDocument]


class ParsedSection(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    section_id: str
    doc_id: str
    header_path: list[str]
    body: str
    metadata: dict[str, Any]


class Phase03ParsedOutput(BasePhasePayload):
    phase_name: str = "03_parsing"
    sections: list[ParsedSection]


class DocumentChunk(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    chunk_id: str
    parent_section_id: str
    doc_id: str
    text: str
    token_count: int
    header_hierarchy: list[str]
    parent_markdown: str


class Phase04ChunkedOutput(BasePhasePayload):
    phase_name: str = "04_chunking"
    chunks: list[DocumentChunk]


class EnrichedIndexedChunk(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    chunk_id: str
    doc_id: str
    contextualized_text: str
    dense_vector: list[float]          # e.g., jina-embeddings-v3 / MRL quantized
    sparse_indices: list[int]          # SPLADE / BM25 lexical indices
    sparse_values: list[float]
    parent_markdown: str
    header_hierarchy: list[str]


class Phase05IndexedOutput(BasePhasePayload):
    phase_name: str = "05_contextual_index"
    qdrant_collection: str
    indexed_records: list[EnrichedIndexedChunk]


# --- RETRIEVAL & GENERATION SCHEMAS (Phases 6 - 10) ---
class Phase06QueryPlanOutput(BasePhasePayload):
    phase_name: str = "06_query_orchestration"
    original_query: str
    route: str                         # "hybrid_rag" | "direct" | "agentic_decompose"
    sub_queries: list[str]
    hyde_passage: str
    metadata_filters: dict[str, Any]
    index_snapshot: Phase05IndexedOutput


class RetrievedCandidate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    chunk_id: str
    doc_id: str
    contextualized_text: str
    parent_markdown: str
    dense_score: float
    sparse_score: float
    rrf_fused_score: float


class Phase07RetrievedOutput(BasePhasePayload):
    phase_name: str = "07_hybrid_retrieval"
    query_plan: Phase06QueryPlanOutput
    candidates: list[RetrievedCandidate]


class RerankedContextItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    chunk_id: str
    doc_id: str
    cross_encoder_score: float
    expanded_parent_context: str


class Phase08RerankedOutput(BasePhasePayload):
    phase_name: str = "08_rerank_context"
    original_query: str
    xml_context_block: str
    top_contexts: list[RerankedContextItem]


class Phase09GenerationOutput(BasePhasePayload):
    phase_name: str = "09_crag_generation"
    original_query: str
    crag_verdict: str                  # "GROUNDED" | "AMBIGUOUS" | "REWRITE_REQUIRED"
    grounded_confidence: float
    synthesized_answer: str
    citations: list[str]
    xml_context_block: str


class Phase10EvalOutput(BasePhasePayload):
    phase_name: str = "10_telemetry_eval"
    run_id: str
    ndcg_at_k: float
    context_precision: float
    faithfulness_score: float
    answer_relevance: float
    hallucination_detected: bool
    final_answer: str


# --- ORCHESTRATOR LINEAGE SCHEMAS (Phase 00) ---
class CRAGAttemptRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    attempt: int
    query_used: str
    crag_verdict: str
    grounded_confidence: float
    top_chunk_ids: list[str]
    rewrite_reason: str | None = None


class PhaseCRAGLoopOutput(BasePhasePayload):
    phase_name: str = "00_crag_orchestrator"
    initial_query: str
    final_query: str
    total_attempts: int
    converged: bool
    attempts_history: list[CRAGAttemptRecord]
    final_generation: Phase09GenerationOutput
    final_evaluation: Phase10EvalOutput


# --- GENERIC TYPE-AWARE TRI-PLEX CLI ENGINE ---
T_In = TypeVar("T_In", bound=BasePhasePayload)
T_Out = TypeVar("T_Out", bound=BasePhasePayload)


class PhaseCLI(Generic[T_In, T_Out]):
    """
    Enforces strict Pydantic input validation from stdin or --in-file,
    dumps formatted summary to stderr console, persists JSON to --out-file,
    and streams raw validated JSON to stdout for the next phase.
    """

    def __init__(
        self,
        phase_title: str,
        input_model: type[T_In] | None,
        output_model: type[T_Out],
        default_out_path: str,
    ):
        ensure_utf8_streams()
        self.phase_title = phase_title
        self.input_model = input_model
        self.output_model = output_model
        self.default_out_path = default_out_path

    def load_upstream(self, in_file: Path | None) -> T_In:
        ensure_utf8_streams()
        if self.input_model is None:
            raise RuntimeError("Phase 01 has no upstream phase.")
        raw_json: str
        if in_file and in_file.exists():
            raw_json = in_file.read_text(encoding="utf-8-sig")
        elif not sys.stdin.isatty():
            raw_json = sys.stdin.read()
        else:
            raise typer.BadParameter(
                f"[{self.phase_title}] Expected upstream JSON via stdin pipe or --in-file"
            )
        raw_json = raw_json.lstrip("\ufeff").strip()
        # Strict runtime type verification of previous phase's output
        return self.input_model.model_validate_json(raw_json)

    def emit(self, payload: T_Out, out_file: Path, quiet: bool = False) -> None:
        ensure_utf8_streams()
        # Re-validate output contract before emitting
        validated = self.output_model.model_validate(payload.model_dump())
        json_str = validated.model_dump_json(indent=2)

        # 1. Persist to file
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json_str, encoding="utf-8")

        # 2. Dump human-readable telemetry to console (stderr so pipes stay clean)
        if not quiet:
            preview = (
                json_str
                if len(json_str) < 900
                else json_str[:900] + "\n  ... [truncated in console preview]"
            )
            err_console.print(
                Panel(
                    Syntax(preview, "json", theme="monokai", word_wrap=True),
                    title=f"[bold cyan]{self.phase_title}[/bold cyan] -> Persisted: [yellow]{out_file}[/yellow]",
                    subtitle=f"Schema: {self.output_model.__name__}",
                    border_style="cyan",
                )
            )

        # 3. Stream pure JSON to stdout for the next CLI phase
        sys.stdout.write(json_str + "\n")
        sys.stdout.flush()
