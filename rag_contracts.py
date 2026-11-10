#!/usr/bin/env python3
# rag_contracts.py
from __future__ import annotations

import contextlib
import errno
import io
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

import typer
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

import loaders.filesystem as _load_fs  # module import: rag_contracts must not hold a DEFAULT_LOAD_* (SSoT)


def ensure_utf8_streams() -> None:
    """Reconfigure sys.stdin, sys.stdout, and sys.stderr to use utf-8 on Windows and POSIX."""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if isinstance(stream, io.TextIOWrapper):
            with contextlib.suppress( OSError, ValueError):
                stream.reconfigure(encoding="utf-8")


# One CRAG threshold default for P09 and P00 (mirrored in .env.example as RAG_CRAG_THRESHOLD)
DEFAULT_CRAG_THRESHOLD = 0.65
CragVerdict = Literal["GROUNDED", "REWRITE_REQUIRED"]

# Console strictly targets stderr so stdout remains a pure JSON pipe
err_console = Console(stderr=True)


class ExitCode(IntEnum):
    """Shared phase exit codes (pipes hide them: assert a phase's code standalone)."""

    OK = 0
    FATAL = 1  # unexpected error, artifact write failure, cap breach, --strict error
    USAGE = 2  # bad option / env / path
    PARTIAL = 3  # >= 1 error and >= 1 result
    EMPTY = 4  # 0 results
    INTERRUPTED = 130  # Ctrl-C / SIGBREAK / SIGTERM


REPLACE_RETRY_S = 2.0  # os.replace retry budget for a destination locked by a reader (Windows)
STALE_TMP_S = 3600  # leftover .<name>.*.tmp older than this is swept on the next write
# Largest upstream JSON a phase accepts. p01 caps supported input at DEFAULT_LOAD_MAX_TOTAL_BYTES; JSON
# escaping grows a byte to at most 6 (a C0 control char -> \u00XX), so every artifact p01 can emit at
# the default cap fits. Measured: real corpus 1.025x, CRLF/tab-heavy text <= 2x.
MAX_UPSTREAM_BYTES = 6 * _load_fs.DEFAULT_LOAD_MAX_TOTAL_BYTES
UPSTREAM_CHUNK = 2**20  # stdin is read in chunks: read(n) pre-allocates n bytes


class StdoutClosed(OSError):
    """The reader closed stdout AFTER the artifact was committed; carries the bytes that were written."""

    def __init__(self, data: bytes) -> None:
        super().__init__(errno.EPIPE, "stdout closed by the reader after the artifact was committed")
        self.data = data


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write `data` to `path` via a same-directory temp file + fsync + os.replace.
    A crash or ENOSPC leaves the previous file byte-identical and no temp file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for old in path.parent.glob(f".{path.name}.*.tmp"):
        with contextlib.suppress(OSError):
            if now - old.stat().st_mtime > STALE_TMP_S:
                old.unlink()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp, 0o666 & ~umask)  # mkstemp creates 0600; artifacts are shared files
        deadline = time.monotonic() + REPLACE_RETRY_S
        while True:
            try:
                os.replace(tmp, path)
                break
            except PermissionError as e:  # Windows: a reader holds the destination open
                if time.monotonic() >= deadline:
                    raise PermissionError(e.errno, f"destination locked, gave up after {REPLACE_RETRY_S}s: {path}") from e
                time.sleep(0.05)
        if os.name != "nt":  # committed already: the directory fsync is best effort, never a failure
            with contextlib.suppress(OSError):
                dfd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
    except OSError as e:
        if e.errno in (errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)):
            raise OSError(e.errno, f"disk full while writing {path}") from e
        raise
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


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
    doc_id: str  # POSIX path relative to the source root (single file: its name)
    source_uri: str
    mime_type: str
    raw_content: str  # byte-faithful decode: line endings kept, BOM stripped (see `bom`)
    sha256: str  # over the raw bytes, BOM included
    size_bytes: int
    encoding: str
    bom: str | None
    newline_style: Literal["lf", "crlf", "cr", "mixed", "none"]
    loader: str
    mime_source: Literal["signature", "extension", "content", "default"]
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class LoadError(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    path: str
    stage: Literal["discover", "open", "read", "decode", "limit", "unstable"]
    exc_type: str
    message: str
    bytes_read: int
    errno: int | None = None
    offset: int | None = None


class LoadSkip(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    path: str
    reason: str
    size_bytes: int
    detail: str | None = None


class Phase01LoadedOutput(BasePhasePayload):
    phase_name: str = "01_loading"
    documents: list[RawDocument]
    errors: list[LoadError] = Field(default_factory=list)
    skipped: list[LoadSkip] = Field(default_factory=list)
    corpus_origin: Literal["directory", "file", "builtin_demo"]


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
    chunk_strategy: str = "sliding_window"


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
    dense_backend: str
    dense_model: str
    sparse_model: str
    indexed_records: list[EnrichedIndexedChunk]


# --- RETRIEVAL & GENERATION SCHEMAS (Phases 6 - 10) ---
class Phase06QueryPlanOutput(BasePhasePayload):
    phase_name: str = "06_query_orchestration"
    original_query: str
    route: str                         # "hybrid_rag" | "direct" | "agentic_decompose"
    sub_queries: list[str]
    hyde_passage: str
    metadata_filters: dict[str, Any]
    qdrant_collection: str
    dense_backend: str
    dense_model: str
    sparse_model: str


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
    crag_verdict: CragVerdict
    grounded_confidence: float
    synthesized_answer: str
    citations: list[str]
    xml_context_block: str


class Phase10EvalOutput(BasePhasePayload):
    phase_name: str = "10_telemetry_eval"
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
    crag_verdict: CragVerdict
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


def payload_bytes(model: BaseModel) -> bytes:
    """Canonical wire form: UTF-8, no BOM, LF only, exactly one trailing newline.
    Serialized straight to bytes: no intermediate str (a str with one astral char is 4 B/char)."""
    return model.__pydantic_serializer__.to_json(model, indent=2) + b"\n"


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

    def load_upstream(self, in_file: Path | None, default_file: Path | None = None) -> T_In:
        """Upstream JSON from --in-file, else stdin (read once), else default_file if given."""
        ensure_utf8_streams()
        if self.input_model is None:
            raise RuntimeError("Phase 01 has no upstream phase.")
        # Bytes end to end: a decoded str of the upstream payload costs up to 4x its size.
        raw: bytes | bytearray = b""
        if in_file is not None:
            if not in_file.is_file():
                raise typer.BadParameter(f"--in-file not found: {in_file}")
            raw = self._read_capped_file(in_file)
        else:
            if not sys.stdin.isatty():
                raw = bytearray()
                while chunk := sys.stdin.buffer.read(UPSTREAM_CHUNK):
                    raw += chunk
                    if len(raw) > MAX_UPSTREAM_BYTES:
                        raise typer.BadParameter(f"[{self.phase_title}] stdin exceeds MAX_UPSTREAM_BYTES "
                                                 f"({MAX_UPSTREAM_BYTES} bytes)")
            if (not raw or raw.isspace()) and default_file is not None and default_file.is_file():
                raw = self._read_capped_file(default_file)
        if raw.startswith(b"\xef\xbb\xbf"):  # PowerShell pipes prepend a UTF-8 BOM
            raw = raw[3:]
        if not raw or raw.isspace():
            hint = f", or default {default_file}" if default_file is not None else ""
            raise typer.BadParameter(
                f"[{self.phase_title}] Expected upstream JSON via stdin pipe or --in-file{hint}"
            )
        # Strict runtime type verification of previous phase's output
        return self.input_model.model_validate_json(raw)

    def _read_capped_file(self, path: Path) -> bytes:
        if (size := path.stat().st_size) > MAX_UPSTREAM_BYTES:
            raise typer.BadParameter(f"[{self.phase_title}] {path} is {size} bytes > MAX_UPSTREAM_BYTES "
                                     f"({MAX_UPSTREAM_BYTES} bytes)")
        return path.read_bytes()

    def emit(self, payload: T_Out, out_file: Path, quiet: bool = False) -> bytes:
        """Serialize once; artifact (atomic) -> stderr panel -> stdout. Returns the bytes written."""
        ensure_utf8_streams()
        if type(payload) is not self.output_model:  # strict construction already validated it
            raise TypeError(f"{self.phase_title}: emit got {type(payload).__name__}, "
                            f"expected {self.output_model.__name__}")
        data = payload_bytes(payload)

        # 1. Persist to file (binary: no newline translation on Windows)
        atomic_write_bytes(out_file, data)

        # 2. Dump human-readable telemetry to console (stderr so pipes stay clean)
        if not quiet:
            preview = data[:900].decode("utf-8", "replace")
            if len(data) > 900:
                preview += "\n  ... [truncated in console preview]"
            err_console.print(
                Panel(
                    Syntax(preview, "json", theme="monokai", word_wrap=True),
                    title=f"[bold cyan]{self.phase_title}[/bold cyan] -> Persisted: [yellow]{out_file}[/yellow]",
                    subtitle=f"Schema: {self.output_model.__name__}",
                    border_style="cyan",
                )
            )

        # 3. Stream pure JSON to stdout for the next CLI phase (after the commit point: the artifact exists)
        try:
            sys.stdout.flush()
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        except OSError as e:  # Windows reports a closed pipe as EINVAL
            if isinstance(e, BrokenPipeError) or e.errno in (errno.EPIPE, errno.EINVAL):
                raise StdoutClosed(data) from e
            raise
        return data
