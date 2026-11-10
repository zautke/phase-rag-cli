#!/usr/bin/env python3
# tests/test_p01_load.py -- rag-p01 (Load v2): CLI, exit codes, report sidecar, negatives (SPEC §9)
from __future__ import annotations

import errno
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import loaders.filesystem as fs
import p01_load
import rag_contracts as rc
import rag_logging

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "docs" / "__test_data__"
MANIFEST = ROOT / "docs" / "TEST_DATA_MANIFEST.json"


# --- helpers ----------------------------------------------------------------------------------------
def invoke(*args: str, env: dict[str, str] | None = None):
    return CliRunner().invoke(p01_load.app, list(args), env=env)


def subproc(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "p01_load.py"), *args], capture_output=True,
                          env=env, check=False, cwd=ROOT)


def artifact(out: Path) -> rc.Phase01LoadedOutput:
    return rc.Phase01LoadedOutput.model_validate_json(out.read_bytes())


def report(out: Path) -> dict:
    return json.loads(out.with_name(out.stem + ".report.json").read_bytes())


def corpus(tmp_path: Path, files: dict[str, bytes]) -> Path:
    src = tmp_path / "src"
    for name, data in files.items():
        (src / name).parent.mkdir(parents=True, exist_ok=True)
        (src / name).write_bytes(data)
    src.mkdir(exist_ok=True)
    return src


def no_tmp(d: Path) -> bool:
    return not [p for p in d.iterdir() if p.name.endswith(".tmp")]


GOOD = {"good.md": b"# good\n"}


# --- logging ----------------------------------------------------------------------------------------
def test_logger_setup_is_idempotent_and_named() -> None:
    a = rag_logging.get_logger("p01")
    b = rag_logging.get_logger("p01", "WARNING")
    assert a is b and a.name == "rag.p01"
    assert len(logging.getLogger("rag").handlers) == 1
    assert logging.getLogger("rag").level == logging.WARNING
    assert not logging.getLogger("rag").propagate


def test_peak_rss_is_measured() -> None:
    assert rag_logging.peak_rss_bytes() > 10 * 2**20  # a Python process with pydantic loaded is > 10 MiB


# --- positives ----------------------------------------------------------------------------------------
SYNTH = {
    "data.csv": b"\xef\xbb\xbfa,b\r\n1,2\r\n",
    "crlf.txt": b"line one\r\nline two\r\n",
    "big.html": b"<html><body>" + b"x" * (16 * 2**20) + b"</body></html>",
    "wide.txt": b"\xff\xfe" + "UTF-16 text\n".encode("utf-16-le"),
    "README": b"no extension here\n",
    "UPPER.MD": b"# upper\n",
}


def test_synthetic_corpus_loads_byte_faithful_with_matching_stdout_and_report(tmp_path: Path) -> None:
    src = corpus(tmp_path, SYNTH)
    out = tmp_path / "a" / "01.json"
    proc = subproc("-s", str(src), "-o", str(out))
    assert proc.returncode == 0, proc.stderr.decode()[-800:]
    assert proc.stdout == out.read_bytes()
    loaded = artifact(out)
    assert [d.doc_id for d in loaded.documents] == ["README", "UPPER.MD", "big.html", "crlf.txt", "data.csv",
                                                     "wide.txt"]  # code-point order
    by = {d.doc_id: d for d in loaded.documents}
    for name, data in SYNTH.items():
        assert by[name].sha256 == hashlib.sha256(data).hexdigest() and by[name].size_bytes == len(data)
    assert by["data.csv"].raw_content == "a,b\r\n1,2\r\n" and by["data.csv"].bom == "utf-8"
    assert by["crlf.txt"].newline_style == "crlf" and by["wide.txt"].raw_content == "UTF-16 text\n"
    assert by["wide.txt"].encoding == "utf-16-le" and by["UPPER.MD"].mime_type == "text/markdown"
    assert by["README"].mime_type == "text/plain" and len(by["big.html"].raw_content) == len(SYNTH["big.html"])
    assert loaded.corpus_origin == "directory" and loaded.errors == [] and loaded.skipped == []
    rep = report(out)
    assert rep["schema"] == "rag-load-report/1" and rep["status"] == "ok" and rep["exit_code"] == 0
    assert rep["metadata"]["run_id"] == loaded.run_id
    assert rep["artifact"] == {"path": str(out), "bytes": len(proc.stdout),
                               "sha256": hashlib.sha256(proc.stdout).hexdigest()}
    assert rep["totals"]["loaded"] == 6 and rep["totals"]["peak_rss_bytes"] > 0
    assert [f["rel_path"] for f in rep["files"]] == sorted(SYNTH)
    lines = "".join(f"{d.doc_id}\t{d.sha256}\n" for d in loaded.documents)
    assert rep["corpus_fingerprint"] == hashlib.sha256(lines.encode()).hexdigest()


def test_rerun_is_deterministic_except_run_id_and_timestamp(tmp_path: Path) -> None:
    src = corpus(tmp_path, {"b.md": b"b", "sub/a.md": b"a\n", "c.txt": b"c\r\n"})
    o1, o2 = tmp_path / "1.json", tmp_path / "2.json"
    assert invoke("-s", str(src), "-o", str(o1), "-q").exit_code == 0
    assert invoke("-s", str(src), "-o", str(o2), "-q").exit_code == 0
    ex = {"run_id", "timestamp"}
    assert artifact(o1).model_dump(exclude=ex) == artifact(o2).model_dump(exclude=ex)
    assert [d.doc_id for d in artifact(o1).documents] == ["b.md", "c.txt", "sub/a.md"]
    assert report(o1)["corpus_fingerprint"] == report(o2)["corpus_fingerprint"]


def test_single_file_source(tmp_path: Path) -> None:
    src = corpus(tmp_path, {"one.md": b"# one\n"})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src / "one.md"), "-o", str(out)).exit_code == 0
    assert [d.doc_id for d in artifact(out).documents] == ["one.md"] and artifact(out).corpus_origin == "file"


def test_demo_corpus_when_source_dir_omitted(tmp_path: Path) -> None:
    out = tmp_path / "o.json"
    assert invoke("-o", str(out), "-q").exit_code == 0
    loaded = artifact(out)
    assert loaded.corpus_origin == "builtin_demo" and len(loaded.documents) == 2
    d = loaded.documents[0]
    assert (d.loader, d.mime_source) == ("builtin", "default")
    assert d.sha256 == hashlib.sha256(d.raw_content.encode()).hexdigest()


def test_two_pass_total_cap_counts_supported_files_only(tmp_path: Path) -> None:
    src = corpus(tmp_path, {"a.md": b"tiny", "pic.png": b"\x89PNG\r\n" + b"\x00" * 5000})
    out = tmp_path / "o.json"
    res = invoke("-s", str(src), "-o", str(out), "-M", "100")
    assert res.exit_code == 0, res.output
    assert [(s.path, s.reason) for s in artifact(out).skipped] == [("pic.png", "binary:image/png")]


def test_env_vars_configure_the_run(tmp_path: Path) -> None:
    src = corpus(tmp_path, {"a.json": b"{}", ".h.md": b"h", "sub/b.md": b"b"})
    out = tmp_path / "o.json"
    env = {"RAG_LOAD_TYPES": "application/json,text/markdown", "RAG_LOAD_INCLUDE_HIDDEN": "true",
           "RAG_LOAD_RECURSIVE": "false"}
    assert invoke("-s", str(src), "-o", str(out), env=env).exit_code == 0
    assert [d.doc_id for d in artifact(out).documents] == [".h.md", "a.json"]


# --- negatives (SPEC §9) -----------------------------------------------------------------------------
def test_n1_missing_source_dir_exits_2_without_writing(tmp_path: Path) -> None:
    out = tmp_path / "o.json"
    proc = subproc("-s", str(tmp_path / "nope"), "-o", str(out))
    assert proc.returncode == 2 and proc.stdout == b"" and not out.exists()


def test_n2_empty_dir_exits_4_with_empty_report(tmp_path: Path) -> None:
    src = corpus(tmp_path, {})
    out = tmp_path / "o.json"
    res = invoke("-s", str(src), "-o", str(out))
    assert res.exit_code == 4 and not out.exists()
    assert report(out)["status"] == "empty" and report(out)["artifact"] is None


def test_n3_unreadable_file_plus_three_good_is_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = corpus(tmp_path, {"a.md": b"a", "b.md": b"b", "c.md": b"c", "locked.md": b"x"})
    real = open

    def guarded(path, *a, **k):
        if str(path).endswith("locked.md"):
            raise PermissionError(errno.EACCES, "Permission denied")
        return real(path, *a, **k)

    monkeypatch.setattr(fs, "open", guarded, raising=False)
    monkeypatch.setattr(fs, "RETRY_LOCKS", False)
    out = tmp_path / "o.json"
    res = invoke("-s", str(src), "-o", str(out))
    assert res.exit_code == 3, res.output
    loaded = artifact(out)
    assert len(loaded.documents) == 3
    assert [(e.path, e.stage, e.errno) for e in loaded.errors] == [("locked.md", "open", errno.EACCES)]
    assert report(out)["status"] == "partial"


def test_n4_nul_txt_is_binary_skip(tmp_path: Path) -> None:
    src = corpus(tmp_path, {**GOOD, "n.txt": b"ab\x00cd"})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 0
    assert [(s.path, s.reason) for s in artifact(out).skipped] == [("n.txt", "binary:nul_bytes")]


def test_n4b_pdf_signature_in_md_is_binary_skip(tmp_path: Path) -> None:
    src = corpus(tmp_path, {**GOOD, "fake.md": b"%PDF-1.4\n..."})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 0
    assert [(s.path, s.reason) for s in artifact(out).skipped] == [("fake.md", "binary:application/pdf")]


def test_n5_invalid_utf8_plus_good_is_partial_with_offset(tmp_path: Path) -> None:
    src = corpus(tmp_path, {**GOOD, "bad.txt": b"abc\xffdef"})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 3
    (err,) = artifact(out).errors
    assert (err.path, err.stage, err.offset, err.exc_type) == ("bad.txt", "decode", 3, "UnicodeDecodeError")


def test_n5a_replace_policy_loads_and_counts(tmp_path: Path) -> None:
    src = corpus(tmp_path, {**GOOD, "bad.txt": b"abc\xffdef"})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out), "-E", "replace").exit_code == 0
    bad = next(d for d in artifact(out).documents if d.doc_id == "bad.txt")
    assert bad.raw_content == "abc\ufffddef" and bad.metadata["decode_replacements"] == 1


def test_n5b_truncated_tail(tmp_path: Path) -> None:
    src = corpus(tmp_path, {**GOOD, "t.txt": b"euro \xe2\x82"})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 3
    assert "TRUNCATED_TAIL" in artifact(out).errors[0].message


def test_n5c_utf16_bom_loads(tmp_path: Path) -> None:
    src = corpus(tmp_path, {"w.txt": b"\xfe\xff" + "big endian".encode("utf-16-be")})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 0
    assert artifact(out).documents[0].raw_content == "big endian"


def test_n6_over_file_cap_is_limit_error_reading_at_most_8k(tmp_path: Path) -> None:
    src = corpus(tmp_path, {**GOOD, "huge.txt": b"a" * 50_000})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out), "-m", "1000").exit_code == 3
    (err,) = artifact(out).errors
    assert (err.path, err.stage) == ("huge.txt", "limit") and err.bytes_read <= 8192


def test_n7_over_total_cap_is_fatal_and_loads_nothing(tmp_path: Path) -> None:
    src = corpus(tmp_path, {"a.md": b"a" * 60, "b.md": b"b" * 60})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out), "-M", "100").exit_code == 1
    assert not out.exists() and report(out)["status"] == "failed" and report(out)["artifact"] is None


def test_max_files_breach_is_fatal(tmp_path: Path) -> None:
    src = corpus(tmp_path, {"a.md": b"a", "b.md": b"b", "c.md": b"c"})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out), "-n", "2").exit_code == 1 and not out.exists()


def test_n8_enospc_keeps_previous_artifact_and_no_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = corpus(tmp_path, GOOD)
    out = tmp_path / "o" / "01.json"
    out.parent.mkdir()
    out.write_bytes(b"previous")

    def full(fd: int) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(rc.os, "fsync", full)
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 1
    assert out.read_bytes() == b"previous" and no_tmp(out.parent)


def test_n9_kill_during_replace_never_leaves_partial_json(tmp_path: Path) -> None:
    src = corpus(tmp_path, GOOD)
    out = tmp_path / "01.json"
    out.write_bytes(b"previous")
    code = "import os, sys, rag_contracts; rag_contracts.os.replace = lambda *a: os._exit(9); " \
           "import p01_load; p01_load.app()"
    proc = subprocess.run([sys.executable, "-c", code, "-s", str(src), "-o", str(out)], cwd=ROOT,
                          capture_output=True, check=False)
    assert proc.returncode == 9 and out.read_bytes() == b"previous" and proc.stdout == b""


def test_n10_interrupt_exits_130_without_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = corpus(tmp_path, GOOD)
    out = tmp_path / "01.json"

    def interrupted(self, ref, sniff):
        raise KeyboardInterrupt

    monkeypatch.setattr(fs.FilesystemLoader, "load", interrupted)
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 130
    assert not out.exists() and no_tmp(tmp_path)


def test_n11_strict_first_error_is_fatal_and_writes_nothing(tmp_path: Path) -> None:
    src = corpus(tmp_path, {**GOOD, "bad.txt": b"\xff"})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out), "-S").exit_code == 1 and not out.exists()


def test_n14_redirected_stderr_has_no_ansi_and_n15_stdout_is_pure_under_errors(tmp_path: Path) -> None:
    src = corpus(tmp_path, {**GOOD, "bad.txt": b"\xff", "n.txt": b"\x00"})
    out = tmp_path / "o.json"
    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "TERM")}  # rely on non-TTY detection
    proc = subproc("-s", str(src), "-o", str(out), env=env)
    assert proc.returncode == 3
    assert b"\x1b[" not in proc.stderr and b"bad.txt" in proc.stderr
    assert proc.stdout == out.read_bytes()
    rc.Phase01LoadedOutput.model_validate_json(proc.stdout)


def test_n20_duplicate_content_is_skipped_first_wins(tmp_path: Path) -> None:
    src = corpus(tmp_path, {"a.md": b"same", "b.md": b"same"})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 0
    assert [d.doc_id for d in artifact(out).documents] == ["a.md"]
    assert [(s.path, s.reason, s.detail) for s in artifact(out).skipped] == [("b.md", "duplicate", "duplicate_of=a.md")]


def test_n21_unknown_backend_exits_2_listing_known(tmp_path: Path) -> None:
    res = invoke("-s", str(corpus(tmp_path, GOOD)), "-o", str(tmp_path / "o.json"), "-b", "s3")
    assert res.exit_code == 2 and "Known: filesystem" in res.output


def test_n22_same_stem_different_extension_keeps_full_ids(tmp_path: Path) -> None:
    src = corpus(tmp_path, {"a.md": b"# md", "a.html": b"<h1>html</h1>"})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 0
    assert {d.doc_id: d.mime_type for d in artifact(out).documents} == {"a.html": "text/html", "a.md": "text/markdown"}


@pytest.mark.parametrize("args", [["-E", "ignore"], ["-E", "surrogateescape"], ["-e", "no-such-codec"],
                                  ["-L", "LOUD"]])
def test_n23_bad_policy_codec_or_level_exits_2(tmp_path: Path, args: list[str]) -> None:
    res = invoke("-s", str(corpus(tmp_path, GOOD)), "-o", str(tmp_path / "o.json"), *args)
    assert res.exit_code == 2 and not (tmp_path / "o.json").exists()


def test_n24_dot_dir_above_the_root_does_not_hide(tmp_path: Path) -> None:
    src = tmp_path / ".cache" / "corpus"
    src.mkdir(parents=True)
    (src / "a.md").write_bytes(b"a")
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 0
    assert [d.doc_id for d in artifact(out).documents] == ["a.md"]


@pytest.mark.skipif(sys.platform == "win32", reason="NTFS names are UTF-16; undecodable bytes are POSIX-only")
def test_n25_lone_surrogate_name_is_escaped(tmp_path: Path) -> None:
    src = corpus(tmp_path, GOOD)
    fd = os.open(os.fsencode(str(src)) + b"/bad_\x80.txt", os.O_WRONLY | os.O_CREAT, 0o644)
    os.write(fd, b"text")
    os.close(fd)
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 0
    bad = artifact(out).documents[0]
    assert bad.doc_id == "bad_\\udc80.txt" and bad.metadata["path_lossy"] is True


def test_n26_everything_policy_skipped_is_empty(tmp_path: Path) -> None:
    src = corpus(tmp_path, {"a.json": b"{}", "b.pdf": b"%PDF-1"})
    out = tmp_path / "o.json"
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 4 and not out.exists()


def test_n27_out_file_inside_source_dir_is_excluded(tmp_path: Path) -> None:
    src = corpus(tmp_path, {**GOOD, "art/old.json": b"{}"})
    out = src / "art" / "01.json"
    res = invoke("-s", str(src), "-o", str(out), "-t", "text/markdown,application/json")
    assert res.exit_code == 0, res.output
    assert [d.doc_id for d in artifact(out).documents] == ["good.md"]
    assert [(s.path, s.reason) for s in artifact(out).skipped] == [("art", "out_dir")]


def test_broken_stdout_after_commit_keeps_the_computed_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = corpus(tmp_path, {**GOOD, "bad.txt": b"\xff"})
    out = tmp_path / "o.json"
    real = p01_load.cli_engine.emit

    def emit_then_pipe_closed(payload, out_file, quiet=False):
        real(payload, out_file, quiet)
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")

    monkeypatch.setattr(p01_load.cli_engine, "emit", emit_then_pipe_closed)
    assert invoke("-s", str(src), "-o", str(out)).exit_code == 3
    assert report(out)["artifact"]["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()


# --- real corpus (live: adagio, docs/__test_data__ is not in git) -----------------------------------------
def manifest() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def check_doc(doc: rc.RawDocument, m: dict) -> None:
    assert (doc.doc_id, doc.sha256, doc.size_bytes) == (m["name"], m["sha256"], m["bytes"])
    assert (doc.bom == "utf-8") is m["bom"] and ("\r\n" in doc.raw_content) is m["crlf"]


@pytest.mark.live
@pytest.mark.skipif(not CORPUS.is_dir(), reason="real corpus absent")
def test_live_real_corpus_directory_matches_manifest(tmp_path: Path) -> None:
    out = tmp_path / "01.json"
    proc = subproc("-s", str(CORPUS), "-o", str(out), "-q")
    assert proc.returncode == 0, proc.stderr.decode()[-800:]
    assert proc.stdout == out.read_bytes()
    loaded = artifact(out)
    assert loaded.errors == [] and loaded.skipped == []
    by = {m["name"]: m for m in manifest()}
    assert sorted(d.doc_id for d in loaded.documents) == sorted(by)
    for doc in loaded.documents:
        check_doc(doc, by[doc.doc_id])


@pytest.mark.live
@pytest.mark.skipif(not CORPUS.is_dir(), reason="real corpus absent")
@pytest.mark.parametrize("m", manifest() if MANIFEST.is_file() else [], ids=lambda m: m["name"][:40])
def test_live_each_real_document_alone(tmp_path: Path, m: dict) -> None:
    out = tmp_path / "01.json"
    proc = subproc("-s", str(CORPUS / m["name"]), "-o", str(out), "-q")
    assert proc.returncode == 0, proc.stderr.decode()[-800:]
    (doc,) = artifact(out).documents
    check_doc(doc, m)
