#!/usr/bin/env python3
# p01_load.py
"""Phase 01: load every document under --source-dir faithfully, boundedly, observably.
Every file not loaded is recorded (skipped[] or errors[]); the run report sidecar says what happened."""
from __future__ import annotations

import codecs
import contextlib
import errno
import hashlib
import json
import os
import platform
import signal
import socket
import time
import unicodedata
from dataclasses import asdict
from datetime import UTC, datetime
from enum import Enum
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Annotated, Any

import typer

from loaders import FilesystemOptions, LoadFailure, Skip, SourceRef, get_loader
from loaders.filesystem import (
    DEFAULT_LOAD_BACKEND,
    DEFAULT_LOAD_ENCODING,
    DEFAULT_LOAD_ENCODING_POLICY,
    DEFAULT_LOAD_EXCLUDE,
    DEFAULT_LOAD_INCLUDE,
    DEFAULT_LOAD_INCLUDE_HIDDEN,
    DEFAULT_LOAD_MAX_FILE_BYTES,
    DEFAULT_LOAD_MAX_FILES,
    DEFAULT_LOAD_MAX_TOTAL_BYTES,
    DEFAULT_LOAD_RECURSIVE,
    DEFAULT_LOAD_STRICT,
    DEFAULT_LOAD_TYPES,
    newline_counts,
)
from rag_contracts import (
    ExitCode,
    LoadError,
    LoadSkip,
    Phase01LoadedOutput,
    PhaseCLI,
    RawDocument,
    atomic_write_bytes,
)
from rag_logging import DEFAULT_LOG_LEVEL, LOG_LEVELS, get_logger, peak_rss_bytes

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)
cli_engine = PhaseCLI(
    "Phase 01: Document Loading",
    None,
    Phase01LoadedOutput,
    "artifacts/01_loaded.json",
)
REPORT_SCHEMA = "rag-load-report/1"


class EncodingPolicy(str, Enum):
    strict = "strict"
    replace = "replace"
    escape = "escape"


DEFAULT_POLICY = EncodingPolicy(DEFAULT_LOAD_ENCODING_POLICY)


def Usage() -> str:
    return (
        "Usage: rag-p01 [--source-dir / -s PATH] [--out-file / -o PATH] [--quiet / -q]\n"
        "[--backend / -b NAME] [--recursive / -r | --no-recursive / -R] [--include / -I GLOBS]\n"
        "[--exclude / -x GLOBS] [--include-hidden / -H] [--max-files / -n N] [--max-file-bytes / -m N]\n"
        "[--max-total-bytes / -M N] [--types / -t MIMES] [--encoding-policy / -E strict|replace|escape]\n"
        "[--encoding / -e CODEC] [--strict / -S] [--log-level / -L LEVEL]\n"
        "Loads every document under --source-dir (omitted: the built-in demo corpus).\n"
        "Exit: 0 ok, 1 fatal, 2 usage, 3 partial (errors[]), 4 no documents, 130 interrupted."
    )


class Fatal(Exception):
    pass


def demo_documents() -> list[RawDocument]:
    """Built-in 2-document corpus for zero-config runs (`rag-p01 | rag-p02 | ...`)."""
    corpus = [
        ("doc_arch_01", "s3://rag-corpus/hybrid_search_spec.html", "text/html",
         ("<html><body><h1>Hybrid RAG Architecture</h1>"
          "<p>Combine Qdrant HNSW dense vectors (jina-embeddings-v3) with SPLADE sparse vectors "
          "using Reciprocal Rank Fusion (k=60).</p>"
          "<h2>Late Chunking</h2>"
          "<p>Apply long-context token pooling before segmentation to preserve cross-paragraph anaphora.</p>"
          "</body></html>")),
        ("doc_sec_02", "s3://rag-corpus/crag_verification.md", "text/markdown",
         ("# Corrective RAG (CRAG)\n"
          "If the cross-encoder score falls below 0.65, trigger a query rewrite loop "
          "before invoking the generator LLM.")),
    ]
    docs = []
    for doc_id, uri, mime, text in corpus:
        raw = text.encode("utf-8")
        style, counts = newline_counts(text)
        docs.append(RawDocument(
            doc_id=doc_id, source_uri=uri, mime_type=mime, raw_content=text,
            sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw), encoding="utf-8", bom=None,
            newline_style=style, loader="builtin", mime_source="default", metadata=dict(counts)))
    return docs


def split_csv(s: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in s.split(",") if x.strip())


def tool_version() -> str:
    try:
        return importlib_metadata.version("sota-hybrid-rag-cli")
    except importlib_metadata.PackageNotFoundError:
        return "unknown"


class Run:
    """One p01 run: three passes, records, report. Exit code from `execute()`."""

    def __init__(self, loader, source: Path | None, out_file: Path, max_files: int, max_total: int,
                 strict: bool, quiet: bool, args: dict[str, Any], log) -> None:
        self.loader, self.source, self.out_file, self.max_files, self.max_total = loader, source, out_file, \
            max_files, max_total
        self.strict, self.quiet, self.args, self.log = strict, quiet, args, log
        self.run_id = Phase01LoadedOutput.model_fields["run_id"].default_factory()
        self.started, self.t0 = datetime.now(UTC).isoformat(), time.monotonic()
        self.docs: list[RawDocument] = []
        self.skips: list[LoadSkip] = []
        self.errors: list[LoadError] = []
        self.files: dict[str, dict[str, Any]] = {}
        self.discovered = 0

    # --- records -----------------------------------------------------------------------------------
    def row(self, path: str, status: str, **kw: Any) -> None:
        base = {"rel_path": path, "status": status, "reason": None, "stage": None, "size_bytes": 0, "sha256": None,
                "mime": None, "encoding": None, "bom": None, "newline_style": None, "mtime_ns": None, "ms": None}
        self.files[path] = {**base, **kw}

    def skip(self, s: Skip, **kw: Any) -> None:
        self.skips.append(LoadSkip(path=s.path, reason=s.reason, size_bytes=s.size_bytes, detail=s.detail))
        self.row(s.path, "skipped", reason=s.reason, size_bytes=s.size_bytes, **kw)
        self.log.info(f"skip {s.path} {s.reason}" + (f" ({s.detail})" if s.detail else ""))

    def fail(self, e: LoadFailure, path: str, **kw: Any) -> None:
        path = e.path or path
        self.errors.append(LoadError(path=path, stage=e.stage, exc_type=e.exc_type, message=e.message,
                                     bytes_read=e.bytes_read, errno=e.errno, offset=e.offset))
        self.row(path, "failed", stage=e.stage, **kw)
        self.log.error(f"error {path} {e.stage} {e.message}")
        if self.strict:
            raise Fatal(f"--strict: {path} failed at stage {e.stage}")

    # --- passes ------------------------------------------------------------------------------------
    def collect(self) -> str:
        if self.source is None:
            self.log.warning("using built-in demo corpus (pass --source-dir to load your documents)")
            self.docs = demo_documents()
            return "builtin_demo"
        self.log.info(f"load start root={self.source} backend={self.loader.name}")
        refs: list[SourceRef] = []
        for item in self.loader.discover(str(self.source)):  # pass 1: discover, bounded during the walk
            self.discovered += 1
            if self.discovered > self.max_files:
                raise Fatal(f"more than max_files={self.max_files} entries under {self.source}; "
                            "narrow --source-dir/--include or raise --max-files")
            if isinstance(item, SourceRef):
                refs.append(item)
            elif isinstance(item, Skip):
                self.skip(item)
            else:
                self.fail(item, item.path)
        refs.sort(key=lambda r: r.rel_path)  # code-point order, stable across OSes
        todo = []
        for ref in refs:  # pass 2: sniff (<= 8 KiB each), then the total cap over supported files
            try:
                sn = self.loader.sniff(ref)
            except LoadFailure as e:
                self.fail(e, ref.rel_path, size_bytes=ref.size_bytes, mtime_ns=ref.mtime_ns)
                continue
            if not sn.supported:
                self.skip(Skip(ref.rel_path, sn.reason or "unsupported", ref.size_bytes), mime=sn.mime_type,
                          mtime_ns=ref.mtime_ns)
                continue
            todo.append((ref, sn))
        total = sum(ref.size_bytes for ref, _ in todo)
        if total > self.max_total:
            raise Fatal(f"supported files total {total} bytes > max_total_bytes {self.max_total}; nothing loaded")
        seen: dict[str, str] = {}
        folded: dict[str, str] = {}
        for k, (ref, sn) in enumerate(todo, start=1):  # pass 3: load
            t = time.monotonic()
            try:
                res = self.loader.load(ref, sn)
            except LoadFailure as e:
                self.fail(e, ref.rel_path, size_bytes=ref.size_bytes, mime=sn.mime_type, mtime_ns=ref.mtime_ns)
                continue
            except (OSError, UnicodeError, MemoryError) as e:
                stage = "decode" if isinstance(e, UnicodeError) else "read"
                self.fail(LoadFailure(stage, str(e), errno=getattr(e, "errno", None), exc_type=type(e).__name__),
                          ref.rel_path, size_bytes=ref.size_bytes, mime=sn.mime_type, mtime_ns=ref.mtime_ns)
                continue
            if isinstance(res, Skip):
                self.skip(res, mime=sn.mime_type, mtime_ns=ref.mtime_ns)
                continue
            if res.sha256 in seen:  # DEDUP = "skip": first in sorted order wins
                self.skip(Skip(res.doc_id, "duplicate", res.size_bytes, f"duplicate_of={seen[res.sha256]}"),
                          sha256=res.sha256, mime=res.mime_type, mtime_ns=ref.mtime_ns)
                continue
            seen[res.sha256] = res.doc_id
            key = unicodedata.normalize("NFC", res.doc_id.casefold())
            if key in folded:
                self.log.warning(f"doc_id {res.doc_id} collides with {folded[key]} on case-insensitive filesystems")
            folded[key] = res.doc_id
            self.docs.append(RawDocument(**asdict(res)))
            ms = round((time.monotonic() - t) * 1000, 1)
            self.row(res.doc_id, "loaded", size_bytes=res.size_bytes, sha256=res.sha256, mime=res.mime_type,
                     encoding=res.encoding, bom=res.bom, newline_style=res.newline_style, mtime_ns=ref.mtime_ns, ms=ms)
            self.log.info(f"load {k}/{len(todo)} {res.doc_id} {res.size_bytes} {res.mime_type}")
        return "file" if self.source.is_file() else "directory"

    # --- run ---------------------------------------------------------------------------------------
    def execute(self) -> int:
        try:
            origin = self.collect()
            self.skips.sort(key=lambda s: s.path)
            self.errors.sort(key=lambda e: e.path)
            if not self.docs:
                self.log.warning("no documents loaded; artifact not written")
                return self.finish(ExitCode.EMPTY, "empty", None)
            payload = Phase01LoadedOutput(run_id=self.run_id, documents=self.docs, errors=self.errors,
                                          skipped=self.skips, corpus_origin=origin)
            code = ExitCode.PARTIAL if self.errors else ExitCode.OK
            try:
                data = cli_engine.emit(payload, self.out_file, self.quiet)
                art = {"path": str(self.out_file), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            except (BrokenPipeError, OSError) as e:
                if not isinstance(e, BrokenPipeError) and e.errno != errno.EINVAL:
                    raise Fatal(f"artifact write failed: {e}") from e
                with contextlib.suppress(OSError, ValueError, AttributeError):  # reader closed stdout
                    os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
                self.log.warning("stdout closed by the reader after the artifact was committed")
                with self.out_file.open("rb") as f:
                    art = {"path": str(self.out_file), "bytes": self.out_file.stat().st_size,
                           "sha256": hashlib.file_digest(f, "sha256").hexdigest()}
            self.log.info(f"write {self.out_file} {art['bytes']}")
            return self.finish(code, "partial" if self.errors else "ok", art)
        except Fatal as e:
            self.log.error(str(e))
            return self.finish(ExitCode.FATAL, "failed", None)
        except (KeyboardInterrupt, typer.Exit):
            raise
        except Exception as e:  # unexpected: FATAL with a report, traceback at DEBUG
            self.log.error(f"unexpected {type(e).__name__}: {e}")
            self.log.debug("traceback", exc_info=True)
            return self.finish(ExitCode.FATAL, "failed", None)

    def finish(self, code: int, status: str, art: dict | None) -> int:
        peak = peak_rss_bytes()
        lines = "".join(f"{d.doc_id}\t{d.sha256}\n" for d in self.docs)
        rep = {
            "schema": REPORT_SCHEMA,
            "metadata": {"run_id": self.run_id, "phase": "01_loading", "tool_version": tool_version(),
                         "host": socket.gethostname(), "python": platform.python_version(),
                         "started_at": self.started, "finished_at": datetime.now(UTC).isoformat()},
            "args": self.args,
            "status": status,
            "exit_code": int(code),
            "elapsed_s": round(time.monotonic() - self.t0, 3),
            "totals": {"discovered": self.discovered, "loaded": len(self.docs), "skipped": len(self.skips),
                       "failed": len(self.errors), "bytes_read": sum(d.size_bytes for d in self.docs)
                       + sum(e.bytes_read for e in self.errors),
                       "bytes_emitted": art["bytes"] if art else 0, "peak_rss_bytes": peak},
            "corpus_fingerprint": hashlib.sha256(lines.encode("utf-8")).hexdigest(),
            "artifact": art,
            "files": [self.files[k] for k in sorted(self.files)],
        }
        path = self.out_file.with_name(self.out_file.stem + ".report.json")
        try:
            atomic_write_bytes(path, (json.dumps(rep, indent=2) + "\n").encode("utf-8"))
        except OSError as e:  # telemetry, not the contract: the exit code stands
            self.log.warning(f"report not written: {e}")
        if not self.quiet:
            self.log.info(f"done run_id={self.run_id} loaded={len(self.docs)} skipped={len(self.skips)} "
                          f"failed={len(self.errors)} bytes={rep['totals']['bytes_read']} "
                          f"peak_rss_mib={peak / 2**20:.0f} exit={int(code)}")
        return int(code)


def _interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


@app.command(epilog=Usage())
def main(
    source_dir: Annotated[
        Path | None,
        typer.Option("--source-dir", "-s", exists=True, help="Directory or single file to load (omitted: demo corpus)"),
    ] = None,
    out_file: Annotated[
        Path,
        typer.Option("--out-file", "-o", help="Output JSON artifact path"),
    ] = Path("artifacts/01_loaded.json"),
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress the Rich panel and INFO lines (warnings still shown)"),
    ] = False,
    backend: Annotated[
        str, typer.Option("--backend", "-b", envvar="RAG_LOAD_BACKEND", help="Loader backend")
    ] = DEFAULT_LOAD_BACKEND,
    recursive: Annotated[
        bool, typer.Option("--recursive/--no-recursive", "-r/-R", envvar="RAG_LOAD_RECURSIVE",
                           help="Descend into subdirectories")
    ] = DEFAULT_LOAD_RECURSIVE,
    include: Annotated[
        str, typer.Option("--include", "-I", envvar="RAG_LOAD_INCLUDE",
                          help="Comma-separated globs on the relative POSIX path; only matches load")
    ] = DEFAULT_LOAD_INCLUDE,
    exclude: Annotated[
        str, typer.Option("--exclude", "-x", envvar="RAG_LOAD_EXCLUDE", help="Comma-separated globs to skip")
    ] = DEFAULT_LOAD_EXCLUDE,
    include_hidden: Annotated[
        bool, typer.Option("--include-hidden", "-H", envvar="RAG_LOAD_INCLUDE_HIDDEN",
                           help="Load dot/hidden/system files and directories")
    ] = DEFAULT_LOAD_INCLUDE_HIDDEN,
    max_files: Annotated[
        int, typer.Option("--max-files", "-n", envvar="RAG_LOAD_MAX_FILES", min=1,
                          help="Fatal when discovery sees more entries")
    ] = DEFAULT_LOAD_MAX_FILES,
    max_file_bytes: Annotated[
        int, typer.Option("--max-file-bytes", "-m", envvar="RAG_LOAD_MAX_FILE_BYTES", min=1,
                          help="Per-file cap; larger files are 'limit' errors")
    ] = DEFAULT_LOAD_MAX_FILE_BYTES,
    max_total_bytes: Annotated[
        int, typer.Option("--max-total-bytes", "-M", envvar="RAG_LOAD_MAX_TOTAL_BYTES", min=1,
                          help="Fatal when supported files exceed this total")
    ] = DEFAULT_LOAD_MAX_TOTAL_BYTES,
    types: Annotated[
        str, typer.Option("--types", "-t", envvar="RAG_LOAD_TYPES", help="Comma-separated MIME allowlist")
    ] = DEFAULT_LOAD_TYPES,
    encoding_policy: Annotated[
        EncodingPolicy, typer.Option("--encoding-policy", "-E", envvar="RAG_LOAD_ENCODING_POLICY",
                                     help="Undecodable bytes: strict (error), replace (U+FFFD, counted), escape")
    ] = DEFAULT_POLICY,
    encoding: Annotated[
        str, typer.Option("--encoding", "-e", envvar="RAG_LOAD_ENCODING",
                          help="Codec for files without a BOM (default utf-8)")
    ] = DEFAULT_LOAD_ENCODING,
    strict: Annotated[
        bool, typer.Option("--strict", "-S", envvar="RAG_LOAD_STRICT", help="First error is fatal; nothing written")
    ] = DEFAULT_LOAD_STRICT,
    log_level: Annotated[
        str, typer.Option("--log-level", "-L", envvar="RAG_LOG_LEVEL", help="DEBUG, INFO, WARNING or ERROR")
    ] = DEFAULT_LOG_LEVEL,
) -> None:
    if log_level.upper() not in LOG_LEVELS:
        raise typer.BadParameter(f"{log_level!r} is not one of {', '.join(LOG_LEVELS)}", param_hint="--log-level")
    if encoding:
        try:
            encoding = codecs.lookup(encoding).name
        except LookupError:
            raise typer.BadParameter(f"unknown codec {encoding!r}", param_hint="--encoding") from None
    exclude_dir = None
    out_dir = out_file.resolve().parent
    if source_dir is not None and source_dir.is_dir():
        src = source_dir.resolve()
        if out_dir != src and out_dir.is_relative_to(src):
            exclude_dir = str(out_dir)
    opts = FilesystemOptions(
        recursive=recursive, include=split_csv(include), exclude=split_csv(exclude), include_hidden=include_hidden,
        max_file_bytes=max_file_bytes, types=split_csv(types), encoding_policy=encoding_policy.value,
        encoding=encoding, exclude_dir=exclude_dir)
    try:
        loader = get_loader(backend, opts)
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="--backend") from None
    log = get_logger("p01", "WARNING" if quiet else log_level)
    args = {"source_dir": str(source_dir) if source_dir else None, "out_file": str(out_file), "backend": backend,
            "recursive": recursive, "include": include, "exclude": exclude, "include_hidden": include_hidden,
            "max_files": max_files, "max_file_bytes": max_file_bytes, "max_total_bytes": max_total_bytes,
            "types": types, "encoding_policy": encoding_policy.value, "encoding": encoding, "strict": strict}
    before = out_file.stat().st_mtime_ns if out_file.exists() else None
    previous = {}
    for name in ("SIGBREAK", "SIGTERM"):  # Windows Ctrl-Break / POSIX kill -> KeyboardInterrupt -> 130
        sig = getattr(signal, name, None)
        if sig is not None and (name == "SIGBREAK") == (os.name == "nt"):
            with contextlib.suppress(ValueError):  # not the main thread
                previous[sig] = signal.signal(sig, _interrupt)
    try:
        code = Run(loader, source_dir, out_file, max_files, max_total_bytes, strict, quiet, args, log).execute()
    except KeyboardInterrupt:
        now = out_file.stat().st_mtime_ns if out_file.exists() else None
        log.error(f"interrupted; artifact {'committed' if now != before else 'untouched'}")
        raise typer.Exit(ExitCode.INTERRUPTED) from None
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
