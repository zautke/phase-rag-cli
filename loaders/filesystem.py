"""Filesystem loader backend: discover -> sniff (<= 8 KiB) -> one bounded read + decode.
Defaults mirrored in .env.example (RAG_LOAD_*); the rest are module constants, not config."""

from __future__ import annotations

import codecs
import hashlib
import os
import stat
import time
from collections.abc import Iterator
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePath

from loaders.base import LoadedDoc, LoadFailure, Skip, Sniff, SourceRef

DEFAULT_LOAD_BACKEND = "filesystem"
DEFAULT_LOAD_RECURSIVE = True
DEFAULT_LOAD_INCLUDE = ""
DEFAULT_LOAD_EXCLUDE = ""
DEFAULT_LOAD_INCLUDE_HIDDEN = False
DEFAULT_LOAD_MAX_FILES = 10000
DEFAULT_LOAD_MAX_FILE_BYTES = 268435456  # 256 MiB per file
DEFAULT_LOAD_MAX_TOTAL_BYTES = 536870912  # 512 MiB of supported files per run
DEFAULT_LOAD_TYPES = "text/markdown,text/html,text/plain,text/csv"
DEFAULT_LOAD_ENCODING_POLICY = "strict"
DEFAULT_LOAD_ENCODING = ""
DEFAULT_LOAD_STRICT = False

SNIFF_BYTES = 8192
STABILITY_RETRIES = 1
LOCK_RETRIES = 3
LOCK_BACKOFF_MS = 500
RETRY_LOCKS = os.name == "nt"  # a sharing violation is transient on Windows; EACCES on POSIX is not
DEDUP = "skip"

SIGNATURES = (
    (b"%PDF-", "application/pdf"), (b"PK\x03\x04", "application/zip"), (b"\x89PNG", "image/png"),
    (b"\xd0\xcf\x11\xe0", "application/x-ole-storage"), (b"\x1f\x8b", "application/gzip"),
    (b"\x7fELF", "application/x-elf"),
)
BOMS = (  # longest first: the UTF-32-LE BOM starts with the UTF-16-LE one
    (codecs.BOM_UTF32_LE, "utf-32-le"), (codecs.BOM_UTF32_BE, "utf-32-be"), (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be"),
)
EXT_MIME = {
    ".md": "text/markdown", ".markdown": "text/markdown", ".html": "text/html", ".htm": "text/html",
    ".txt": "text/plain", ".log": "text/plain", ".csv": "text/csv", ".tsv": "text/tab-separated-values",
    ".json": "application/json", ".ndjson": "application/x-ndjson", ".yaml": "application/yaml",
    ".yml": "application/yaml", ".toml": "application/toml", ".xml": "application/xml",
}
POLICY_ERRORS = {"strict": "strict", "replace": "rag-count-replace", "escape": "backslashreplace"}
HIDDEN_NAMES = {"desktop.ini", "thumbs.db"}
FILE_ATTRIBUTE_HIDDEN, FILE_ATTRIBUTE_SYSTEM = 0x2, 0x4
CLOUD_RECALL = 0x400000 | 0x40000  # RECALL_ON_DATA_ACCESS | RECALL_ON_OPEN: reading would download
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003  # junction; stat only defines it on Windows

_replacements = [0]


def _count_replace(e: UnicodeDecodeError) -> tuple[str, int]:
    _replacements[0] += 1  # one per replaced sequence
    return "\ufffd", e.end


codecs.register_error("rag-count-replace", _count_replace)


@dataclass(frozen=True)
class FilesystemOptions:
    recursive: bool = DEFAULT_LOAD_RECURSIVE
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    include_hidden: bool = DEFAULT_LOAD_INCLUDE_HIDDEN
    max_file_bytes: int = DEFAULT_LOAD_MAX_FILE_BYTES
    types: tuple[str, ...] = tuple(DEFAULT_LOAD_TYPES.split(","))
    encoding_policy: str = DEFAULT_LOAD_ENCODING_POLICY
    encoding: str = DEFAULT_LOAD_ENCODING  # "" = BOM, else utf-8
    exclude_dir: str | None = None  # the --out-file directory when it sits inside the root


def display_path(s: str) -> tuple[str, bool]:
    """Lone surrogates (undecodable POSIX names) cannot be JSON-encoded: escape them, flag lossy."""
    try:
        s.encode("utf-8")
        return s, False
    except UnicodeEncodeError:
        return s.encode("utf-8", "backslashreplace").decode("ascii"), True


def strip_long_prefix(p: str) -> str:
    if p.startswith("\\\\?\\UNC\\"):
        return "\\\\" + p[8:]
    return p.removeprefix("\\\\?\\")


def long_path(p: str) -> str:
    """Windows: always walk from \\\\?\\ + abspath so paths beyond MAX_PATH are not silently lost."""
    if p.startswith("\\\\?\\"):
        return p
    a = os.path.abspath(p)
    if os.name != "nt":
        return a
    return "\\\\?\\UNC\\" + a[2:] if a.startswith("\\\\") else "\\\\?\\" + a


def is_link(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or getattr(st, "st_reparse_tag", 0) == IO_REPARSE_TAG_MOUNT_POINT


def is_hidden(name: str, st: os.stat_result) -> bool:
    attrs = getattr(st, "st_file_attributes", 0)
    return (name.startswith((".", "~$")) or name.lower() in HIDDEN_NAMES
            or bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)))


def newline_counts(text: str) -> tuple[str, dict[str, int]]:
    crlf = text.count("\r\n")
    counts = {"newline_crlf": crlf, "newline_cr": text.count("\r") - crlf, "newline_lf": text.count("\n") - crlf}
    kinds = [k for k, v in zip(("crlf", "cr", "lf"), counts.values(), strict=True) if v]
    return ("none" if not kinds else kinds[0] if len(kinds) == 1 else "mixed"), counts


class FilesystemLoader:
    name = "filesystem"

    def __init__(self, opts: FilesystemOptions) -> None:
        self.opts = opts

    # --- pass 1 ------------------------------------------------------------------------------------
    def discover(self, root: str) -> Iterator[SourceRef | Skip | LoadFailure]:
        top = long_path(root)
        if os.path.isfile(top):  # a single named file bypasses every filter
            st = os.stat(top)
            yield SourceRef(top, display_path(os.path.basename(root))[0], st.st_size, st.st_mtime_ns)
            return
        excl = os.path.normcase(long_path(self.opts.exclude_dir)) if self.opts.exclude_dir else None
        walk_errors: list[OSError] = []
        for dirpath, dirs, files in os.walk(top, followlinks=False, onerror=walk_errors.append):
            for err in walk_errors:
                yield LoadFailure("discover", str(err.strerror or err), path=self._rel(top, err.filename or dirpath),
                                  errno=err.errno, exc_type=type(err).__name__)
            walk_errors.clear()
            keep = []
            for d in sorted(dirs):
                full = os.path.join(dirpath, d)
                rel = self._rel(top, full)
                try:
                    st = os.lstat(full)
                except OSError as e:
                    yield LoadFailure("discover", str(e.strerror or e), path=rel, errno=e.errno, exc_type=type(e).__name__)
                    continue
                if is_link(st):
                    yield Skip(rel, "link")
                elif is_hidden(d, st) and not self.opts.include_hidden:
                    yield Skip(rel, "hidden")  # one record per pruned directory
                elif excl is not None and os.path.normcase(full) == excl:
                    yield Skip(rel, "out_dir")
                else:
                    keep.append(d)
            dirs[:] = keep if self.opts.recursive else []
            for f in sorted(files):
                full = os.path.join(dirpath, f)
                rel = self._rel(top, full)
                try:
                    st = os.lstat(full)
                except OSError as e:
                    yield LoadFailure("discover", str(e.strerror or e), path=rel, errno=e.errno, exc_type=type(e).__name__)
                    continue
                if is_link(st):
                    yield Skip(rel, "link")
                elif not stat.S_ISREG(st.st_mode):
                    yield Skip(rel, "not_regular_file")
                elif getattr(st, "st_file_attributes", 0) & CLOUD_RECALL:
                    yield Skip(rel, "cloud_placeholder", st.st_size)
                elif is_hidden(f, st) and not self.opts.include_hidden:
                    yield Skip(rel, "hidden", st.st_size)
                elif (self.opts.include and not any(fnmatchcase(rel, g) for g in self.opts.include)) or any(
                        fnmatchcase(rel, g) for g in self.opts.exclude):
                    yield Skip(rel, "excluded", st.st_size)
                else:
                    yield SourceRef(full, rel, st.st_size, st.st_mtime_ns)

    @staticmethod
    def _rel(top: str, full: str) -> str:
        return display_path(PurePath(os.path.relpath(full, top)).as_posix())[0]

    # --- pass 2 ------------------------------------------------------------------------------------
    def sniff(self, ref: SourceRef) -> Sniff:
        if ref.size_bytes == 0:
            return Sniff("application/octet-stream", "default", "utf-8", 0, False, "empty")
        with self._open(ref) as f:
            head = f.read(SNIFF_BYTES)
        for sig, mime in SIGNATURES:
            if head.startswith(sig):
                return Sniff(mime, "signature", "", 0, False, f"binary:{mime}")
        if head.startswith(b"MZ") and b"\0" in head:  # a PE header always carries NULs
            return Sniff("application/x-msdownload", "signature", "", 0, False, "binary:application/x-msdownload")
        enc, bom_len = next(((e, len(b)) for b, e in BOMS if head.startswith(b)), (self.opts.encoding or "utf-8", 0))
        if b"\0" in head and not enc.startswith(("utf-16", "utf-32")):
            return Sniff("application/octet-stream", "content", enc, bom_len, False, "binary:nul_bytes")
        ext = os.path.splitext(ref.rel_path)[1].lower()
        if ext in EXT_MIME:
            mime, source = EXT_MIME[ext], "extension"
        else:
            lead = head[bom_len:bom_len + 512].decode(enc, "ignore").lstrip().lower()
            if lead.startswith(("<!doctype html", "<html")):
                mime, source = "text/html", "content"
            elif lead.startswith("<?xml"):
                mime, source = "application/xml", "content"
            else:
                mime, source = "text/plain", "default"
        if mime not in self.opts.types:
            return Sniff(mime, source, enc, bom_len, False, f"type_not_allowed:{mime}")
        if ref.size_bytes > self.opts.max_file_bytes:
            raise LoadFailure("limit", f"{ref.size_bytes} bytes > max_file_bytes {self.opts.max_file_bytes}",
                              path=ref.rel_path, bytes_read=len(head))
        return Sniff(mime, source, enc, bom_len, True)

    # --- pass 3 ------------------------------------------------------------------------------------
    def load(self, ref: SourceRef, sniff: Sniff) -> LoadedDoc | Skip:
        cap = self.opts.max_file_bytes
        for _ in range(STABILITY_RETRIES + 1):
            with self._open(ref) as f:
                st0 = os.fstat(f.fileno())
                # one bounded read; read(n) pre-allocates n bytes, so size it by the file (+1 detects growth)
                data = f.read(min(cap, st0.st_size) + 1)
                st1 = os.fstat(f.fileno())
            if len(data) > cap:
                raise LoadFailure("limit", f"file grew past max_file_bytes {cap}", path=ref.rel_path,
                                  bytes_read=len(data))
            if len(data) == st0.st_size and (st1.st_size, st1.st_mtime_ns) == (st0.st_size, st0.st_mtime_ns):
                break
        else:
            raise LoadFailure("unstable", "file changed while being read", path=ref.rel_path, bytes_read=len(data))
        sha = hashlib.sha256(data).hexdigest()
        body = memoryview(data)[sniff.bom_len:]  # no copy of the payload
        _replacements[0] = 0
        try:
            text = str(body, sniff.encoding, POLICY_ERRORS[self.opts.encoding_policy])
        except UnicodeDecodeError as e:
            off = sniff.bom_len + e.start
            tail = e.reason in ("unexpected end of data", "truncated data") and e.start >= len(body) - 3
            ctx = data[max(0, off - 16):off + 16].hex()
            raise LoadFailure("decode", f"{'TRUNCATED_TAIL' if tail else e.reason} at byte {off} ({sniff.encoding});"
                              f" context={ctx}", path=ref.rel_path, offset=off, bytes_read=len(data),
                              exc_type="UnicodeDecodeError") from None
        finally:
            body.release()
        if (nul := text.find("\0")) >= 0:
            return Skip(ref.rel_path, "binary:nul_bytes", len(data), f"first_nul_char={nul}")
        style, meta = newline_counts(text)
        if self.opts.encoding_policy == "replace":
            meta["decode_replacements"] = _replacements[0]
        if feff := text.count("\ufeff"):
            meta["feff_count"] = feff
        if display_path(ref.uri)[1]:
            meta["path_lossy"] = True
        bom = sniff.encoding if sniff.bom_len else None
        return LoadedDoc(ref.rel_path, display_path(strip_long_prefix(ref.uri))[0], sniff.mime_type, text, sha,
                         len(data), sniff.encoding, bom, style, self.name, sniff.mime_source, dict(meta))

    def _open(self, ref: SourceRef):
        for attempt in range(LOCK_RETRIES + 1):
            try:
                return open(ref.uri, "rb")
            except PermissionError as e:
                if not RETRY_LOCKS or attempt == LOCK_RETRIES:
                    raise LoadFailure("open", str(e.strerror or e), path=ref.rel_path, errno=e.errno,
                                      exc_type=type(e).__name__) from None
                time.sleep(LOCK_BACKOFF_MS / 1000)
            except OSError as e:
                raise LoadFailure("open", str(e.strerror or e), path=ref.rel_path, errno=e.errno,
                                  exc_type=type(e).__name__) from None
        raise AssertionError("unreachable")
