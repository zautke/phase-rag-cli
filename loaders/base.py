"""Loader seam: a backend is a SOURCE (filesystem now; http/s3/git/archive later).
A format is a decoder chosen inside `load()` by `Sniff.mime_type`. No imports from the pipeline."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SourceRef:
    uri: str  # openable locator (Windows: may carry the \\?\ prefix)
    rel_path: str  # POSIX, relative to the root, display-safe (lone surrogates escaped)
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class Skip:
    """A file or directory that is deliberately not loaded (policy, not failure)."""

    path: str
    reason: str
    size_bytes: int = 0
    detail: str | None = None


@dataclass(frozen=True)
class Sniff:
    mime_type: str
    mime_source: str  # signature | extension | content | default
    encoding: str
    bom_len: int
    reason: str | None = None  # skip reason; None = supported, load it


@dataclass(frozen=True)
class LoadedDoc:
    doc_id: str
    source_uri: str
    mime_type: str
    raw_content: str
    sha256: str
    size_bytes: int
    encoding: str
    bom: str | None
    newline_style: str
    loader: str
    mime_source: str
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)


class LoadFailure(Exception):
    """One in-scope file could not be loaded; the run records it and continues."""

    def __init__(self, stage: str, message: str, *, path: str = "", offset: int | None = None,
                 errno: int | None = None, bytes_read: int = 0, exc_type: str = "LoadFailure") -> None:
        super().__init__(message)
        self.stage, self.message, self.path, self.offset = stage, message, path, offset
        self.errno, self.bytes_read, self.exc_type = errno, bytes_read, exc_type


class LoaderBackend(Protocol):
    name: str

    def discover(self, root: str) -> Iterator[SourceRef | Skip | LoadFailure]: ...

    def sniff(self, ref: SourceRef) -> Sniff: ...

    def load(self, ref: SourceRef, sniff: Sniff) -> LoadedDoc | Skip: ...
