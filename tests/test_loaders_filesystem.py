#!/usr/bin/env python3
# tests/test_loaders_filesystem.py -- unit tests for loaders/filesystem.py (Load v2 §2-§3)
from __future__ import annotations

import builtins
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

import loaders.filesystem as fs
from loaders import FilesystemLoader, FilesystemOptions, LoadFailure, Skip, SourceRef, get_loader


def loader(**kw) -> FilesystemLoader:
    return FilesystemLoader(FilesystemOptions(**kw))


def ref_for(p: Path, rel: str | None = None) -> SourceRef:
    st = p.stat()
    return SourceRef(str(p), rel or p.name, st.st_size, st.st_mtime_ns)


def discover(ld: FilesystemLoader, root: Path) -> tuple[list[str], dict[str, str]]:
    refs, skips = [], {}
    for item in ld.discover(str(root)):
        if isinstance(item, SourceRef):
            refs.append(item.rel_path)
        elif isinstance(item, Skip):
            skips[item.path] = item.reason
        else:
            raise item
    return sorted(refs), skips


def load(ld: FilesystemLoader, p: Path):
    r = ref_for(p)
    return ld.load(r, ld.sniff(r))


# --- registry ---------------------------------------------------------------------------------------
def test_get_loader_known_and_unknown() -> None:
    assert isinstance(get_loader("filesystem", FilesystemOptions()), FilesystemLoader)
    with pytest.raises(ValueError, match="Known: filesystem"):
        get_loader("s3", FilesystemOptions())


# --- discovery --------------------------------------------------------------------------------------
def test_discover_prunes_hidden_dir_once_and_skips_hidden_files(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    for i in range(5):
        (tmp_path / ".git" / f"f{i}.md").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("b")
    (tmp_path / "a.md").write_text("a")
    (tmp_path / ".env").write_text("x")
    (tmp_path / "~$lock.md").write_text("x")
    (tmp_path / "README").write_text("extensionless")
    refs, skips = discover(loader(), tmp_path)
    assert refs == ["README", "a.md", "sub/b.md"]
    assert skips == {".git": "hidden", ".env": "hidden", "~$lock.md": "hidden"}
    refs, _ = discover(loader(include_hidden=True), tmp_path)
    assert ".git/f0.md" in refs and ".env" in refs


def test_discover_non_recursive_include_exclude_and_out_dir(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("b")
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "c.txt").write_text("c")
    assert discover(loader(recursive=False), tmp_path)[0] == ["a.md", "c.txt"]
    refs, skips = discover(loader(include=("*.md",), exclude=("sub/*",)), tmp_path)
    assert refs == ["a.md"] and skips == {"c.txt": "excluded", "sub/b.md": "excluded"}
    refs, skips = discover(loader(exclude_dir=str(tmp_path / "sub")), tmp_path)
    assert refs == ["a.md", "c.txt"] and skips == {"sub": "out_dir"}


def test_discover_single_file_root_bypasses_filters(tmp_path: Path) -> None:
    f = tmp_path / ".hidden.md"
    f.write_text("x")
    refs = list(loader(include=("*.txt",)).discover(str(f)))
    assert [r.rel_path for r in refs] == [".hidden.md"]


def test_discover_classifies_link_junction_placeholder_and_special(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for n in ("ok.md", "sym.md", "junc.md", "cloud.md", "fifo"):
        (tmp_path / n).write_text("x")
    real = fs.os.lstat

    def fake(p, *a, **k):
        name = Path(str(p)).name
        st = real(p, *a, **k)
        base = {"st_mode": st.st_mode, "st_size": st.st_size, "st_mtime_ns": st.st_mtime_ns,
                    "st_file_attributes": 0, "st_reparse_tag": 0}
        if name == "sym.md":
            base["st_mode"] = stat.S_IFLNK | 0o777
        elif name == "junc.md":
            base["st_reparse_tag"] = fs.IO_REPARSE_TAG_MOUNT_POINT
        elif name == "cloud.md":
            base["st_file_attributes"] = 0x400000
        elif name == "fifo":
            base["st_mode"] = stat.S_IFIFO | 0o644
        return SimpleNamespace(**base)

    monkeypatch.setattr(fs.os, "lstat", fake)
    refs, skips = discover(loader(), tmp_path)
    assert refs == ["ok.md"]
    assert skips == {"sym.md": "link", "junc.md": "link", "cloud.md": "cloud_placeholder", "fifo": "not_regular_file"}


# --- sniff ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "data", "mime", "source", "reason"),
    [
        ("e.md", b"", "application/octet-stream", "default", "empty"),
        ("x.md", b"%PDF-1.7\nrest", "application/pdf", "signature", "binary:application/pdf"),
        ("z.txt", b"PK\x03\x04data", "application/zip", "signature", "binary:application/zip"),
        ("n.txt", b"abc\x00def", "application/octet-stream", "content", "binary:nul_bytes"),
        ("mz.txt", b"MZ is a text file", "text/plain", "extension", None),
        ("U.MD", b"# hi", "text/markdown", "extension", None),
        ("README", b"plain words", "text/plain", "default", None),
        ("page", b"  <!DOCTYPE html><html>", "text/html", "content", None),
        ("d.json", b"{}", "application/json", "extension", "type_not_allowed:application/json"),
    ],
)
def test_sniff(tmp_path: Path, name: str, data: bytes, mime: str, source: str, reason: str | None) -> None:
    p = tmp_path / name
    p.write_bytes(data)
    s = loader().sniff(ref_for(p))
    assert (s.mime_type, s.mime_source, s.reason, s.supported) == (mime, source, reason, reason is None)


@pytest.mark.parametrize(
    ("bom", "enc", "bom_len"),
    [(b"\xef\xbb\xbf", "utf-8", 3), (b"\xff\xfe", "utf-16-le", 2), (b"\xfe\xff", "utf-16-be", 2),
     (b"\xff\xfe\x00\x00", "utf-32-le", 4), (b"\x00\x00\xfe\xff", "utf-32-be", 4)],
)
def test_sniff_bom_families_are_text_despite_nul_bytes(tmp_path: Path, bom: bytes, enc: str, bom_len: int) -> None:
    p = tmp_path / "b.txt"
    p.write_bytes(bom + "hi\r\n".encode(enc))
    s = loader().sniff(ref_for(p))
    assert (s.encoding, s.bom_len, s.supported) == (enc, bom_len, True)
    d = loader().load(ref_for(p), s)
    assert (d.raw_content, d.bom, d.newline_style) == ("hi\r\n", enc, "crlf")


def test_sniff_over_cap_is_a_limit_error_reading_at_most_8k(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "big.txt"
    p.write_bytes(b"a" * 100_000)
    reads = spy_reads(monkeypatch)
    with pytest.raises(LoadFailure) as ei:
        loader(max_file_bytes=10_000).sniff(ref_for(p))
    assert ei.value.stage == "limit" and ei.value.bytes_read <= 8192
    assert sum(reads) <= 8192


def test_sniff_over_cap_binary_is_a_skip_not_a_limit(tmp_path: Path) -> None:
    p = tmp_path / "big.png"
    p.write_bytes(b"\x89PNG\r\n" + b"\x00" * 50_000)
    assert loader(max_file_bytes=10_000).sniff(ref_for(p)).reason == "binary:image/png"


# --- load -------------------------------------------------------------------------------------------
def spy_reads(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    reads: list[int] = []
    real_open = builtins.open

    class Spy:
        def __init__(self, f):
            self.f = f

        def read(self, n=-1):
            b = self.f.read(n)
            reads.append(len(b))
            requested.append(n)
            return b

        def fileno(self):
            return self.f.fileno()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.f.close()

    monkeypatch.setattr(fs, "open", lambda *a, **k: Spy(real_open(*a, **k)), raising=False)
    return reads


requested: list[int] = []


def test_load_buffer_is_sized_by_the_file_not_the_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """read(n) pre-allocates n bytes: read(cap+1) cost 256 MiB of RSS for a 532-byte file (smoke run)."""
    p = tmp_path / "small.md"
    p.write_bytes(b"x" * 100)
    ld = loader()  # default cap 256 MiB
    r = ref_for(p)
    s = ld.sniff(r)
    spy_reads(monkeypatch)
    requested.clear()
    assert ld.load(r, s).size_bytes == 100
    assert max(requested) == 101  # size + 1 still detects growth (-> re-read / unstable / limit)


def test_load_reads_at_most_cap_plus_one_when_file_grew(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "grow.txt"
    p.write_bytes(b"a" * 100)
    ld = loader(max_file_bytes=1000)
    r = ref_for(p)
    s = ld.sniff(r)
    p.write_bytes(b"a" * 10_000)  # 10x the cap after sniff (TOCTOU)
    reads = spy_reads(monkeypatch)
    with pytest.raises(LoadFailure) as ei:
        ld.load(r, s)
    assert ei.value.stage == "limit" and ei.value.bytes_read == 1001 and sum(reads) == 1001


def test_load_utf8_bom_crlf_is_byte_faithful(tmp_path: Path) -> None:
    raw = "\ufeffa,b\r\n1,2\r\n".encode()
    p = tmp_path / "x.csv"
    p.write_bytes(raw)
    d = load(loader(), p)
    import hashlib

    assert d.raw_content == "a,b\r\n1,2\r\n" and d.bom == "utf-8" and d.mime_type == "text/csv"
    assert d.sha256 == hashlib.sha256(raw).hexdigest() and d.size_bytes == len(raw)
    assert (d.newline_style, d.metadata["newline_crlf"], d.doc_id) == ("crlf", 2, "x.csv")


@pytest.mark.parametrize(
    ("text", "style"), [("a\nb\n", "lf"), ("a\r\nb", "crlf"), ("a\rb", "cr"), ("a\nb\r\n", "mixed"), ("ab", "none")]
)
def test_newline_style(tmp_path: Path, text: str, style: str) -> None:
    p = tmp_path / "n.txt"
    p.write_bytes(text.encode())
    assert load(loader(), p).newline_style == style


def test_decode_error_offset_and_context(tmp_path: Path) -> None:
    p = tmp_path / "bad.txt"
    p.write_bytes(b"\xef\xbb\xbfhello\xffworld")
    with pytest.raises(LoadFailure) as ei:
        load(loader(), p)
    assert (ei.value.stage, ei.value.offset) == ("decode", 8)
    assert "invalid start byte" in ei.value.message and "ff" in ei.value.message


def test_decode_truncated_tail(tmp_path: Path) -> None:
    p = tmp_path / "t.txt"
    p.write_bytes(b"price \xe2\x82")
    with pytest.raises(LoadFailure) as ei:
        load(loader(), p)
    assert ei.value.offset == 6 and "TRUNCATED_TAIL" in ei.value.message


def test_replace_policy_counts_each_replaced_sequence(tmp_path: Path) -> None:
    p = tmp_path / "r.txt"
    p.write_bytes(b"a\xffb\xfe\xfec")
    d = load(loader(encoding_policy="replace"), p)
    assert d.raw_content == "a\ufffdb\ufffd\ufffdc" and d.metadata["decode_replacements"] == 3
    assert load(loader(encoding_policy="escape"), p).raw_content == "a\\xffb\\xfe\\xfec"


def test_nul_after_the_sniff_head_is_a_binary_skip(tmp_path: Path) -> None:
    p = tmp_path / "late.txt"
    p.write_bytes(b"a" * 9000 + b"\x00tail")
    res = load(loader(), p)
    assert isinstance(res, Skip) and res.reason == "binary:nul_bytes" and res.detail == "first_nul_char=9000"


def test_feff_inside_text_is_counted(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_bytes("a\ufeffb".encode())
    assert load(loader(), p).metadata["feff_count"] == 1


def test_unstable_file_is_reread_once_then_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "u.txt"
    p.write_bytes(b"hello")
    ld = loader()
    r = ref_for(p)
    s = ld.sniff(r)
    real, n = fs.os.fstat, [0]

    def drifting(fd):
        st = real(fd)
        n[0] += 1
        return SimpleNamespace(st_size=st.st_size, st_mtime_ns=st.st_mtime_ns + n[0])

    monkeypatch.setattr(fs.os, "fstat", drifting)
    with pytest.raises(LoadFailure) as ei:
        ld.load(r, s)
    assert ei.value.stage == "unstable" and n[0] == 4  # 2 attempts x (before, after)


def test_locked_file_is_retried_then_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "l.txt"
    p.write_bytes(b"hello")
    ld = loader()
    r = ref_for(p)
    s = ld.sniff(r)
    calls: list[int] = []
    real_open = builtins.open

    def locked(*a, **k):
        calls.append(1)
        if len(calls) <= 2:
            raise PermissionError(13, "sharing violation")
        return real_open(*a, **k)

    monkeypatch.setattr(fs, "RETRY_LOCKS", True)
    monkeypatch.setattr(fs.time, "sleep", lambda s: None)
    monkeypatch.setattr(fs, "open", locked, raising=False)
    assert ld.load(r, s).raw_content == "hello" and len(calls) == 3
    calls.clear()
    monkeypatch.setattr(fs, "open", lambda *a, **k: (_ for _ in ()).throw(PermissionError(13, "denied")), raising=False)
    with pytest.raises(LoadFailure) as ei:
        ld.load(r, s)
    assert (ei.value.stage, ei.value.errno) == ("open", 13)


def test_lone_surrogate_path_is_escaped(tmp_path: Path) -> None:
    rel, lossy = fs.display_path("bad_\udc80.txt")
    assert (rel, lossy) == ("bad_\\udc80.txt", True)
    assert fs.display_path("ok.txt") == ("ok.txt", False)
