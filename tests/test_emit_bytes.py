#!/usr/bin/env python3
# tests/test_emit_bytes.py -- D-A1: stdout and --out-file get byte-identical UTF-8/LF payloads
from __future__ import annotations

import errno
import io
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import rag_contracts as rc


def test_p01_stdout_and_artifact_are_byte_identical_lf(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text("# Title\n\nbody text\n", encoding="utf-8")
    out = tmp_path / "01.json"
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "p01_load.py"), "-s", str(src), "-o", str(out), "-q"],
        capture_output=True,
        check=True,
    )
    art = out.read_bytes()
    assert proc.stdout == art
    assert b"\r" not in art
    assert art.endswith(b"}\n") and not art.endswith(b"\n\n")
    assert not art.startswith(b"\xef\xbb\xbf")
    rc.Phase01LoadedOutput.model_validate_json(art)  # load_upstream contract unchanged


# --- single-serialization emit, bytes load_upstream, atomic writes (Load v2 §7) ---------------------
def _p02_payload() -> rc.Phase02MarkdownOutput:
    return rc.Phase02MarkdownOutput(
        run_id="r1", timestamp="t", documents=[rc.MarkdownDocument(doc_id="d", source_uri="u", clean_markdown="é 😀 x" * 200)]
    )


def _fake_stdout(monkeypatch: pytest.MonkeyPatch) -> io.BytesIO:
    buf = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(buf, encoding="utf-8"))
    return buf


def test_payload_bytes_is_the_single_serializer_and_matches_model_dump_json() -> None:
    m = _p02_payload()
    assert rc.payload_bytes(m) == (m.model_dump_json(indent=2) + "\n").encode("utf-8")


def test_emit_returns_the_bytes_written_to_artifact_and_stdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    buf = _fake_stdout(monkeypatch)
    cli = rc.PhaseCLI("t", rc.Phase01LoadedOutput, rc.Phase02MarkdownOutput, "x")
    out = tmp_path / "sub" / "02.json"
    data = cli.emit(_p02_payload(), out, quiet=True)
    assert data == rc.payload_bytes(_p02_payload()) == out.read_bytes() == buf.getvalue()
    assert [p.name for p in out.parent.iterdir()] == ["02.json"]  # no tmp left behind


def test_emit_rejects_a_payload_of_the_wrong_model(tmp_path: Path) -> None:
    cli = rc.PhaseCLI("t", None, rc.Phase01LoadedOutput, "x")
    with pytest.raises(TypeError):
        cli.emit(_p02_payload(), tmp_path / "o.json", quiet=True)  # type: ignore[arg-type]


def test_load_upstream_reads_bytes_and_strips_utf8_bom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli = rc.PhaseCLI("t", rc.Phase02MarkdownOutput, rc.Phase03ParsedOutput, "x")
    data = rc.payload_bytes(_p02_payload())
    f = tmp_path / "02.json"
    f.write_bytes(b"\xef\xbb\xbf" + data)
    assert cli.load_upstream(f) == _p02_payload()

    class FakeStdin:
        buffer = io.BytesIO(b"\xef\xbb\xbf" + data)

        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(sys, "stdin", FakeStdin())
    assert cli.load_upstream(None) == _p02_payload()


def test_load_upstream_empty_stdin_is_a_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import typer

    class FakeStdin:
        buffer = io.BytesIO(b" \n")

        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(sys, "stdin", FakeStdin())
    with pytest.raises(typer.BadParameter):
        rc.PhaseCLI("t", rc.Phase02MarkdownOutput, rc.Phase03ParsedOutput, "x").load_upstream(None)


def test_exit_codes() -> None:
    assert [int(c) for c in rc.ExitCode] == [0, 1, 2, 3, 4, 130]


def test_atomic_write_enospc_keeps_previous_file_and_no_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "a.json"
    out.write_bytes(b"old")

    def boom(fd: int) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(rc.os, "fsync", boom)
    with pytest.raises(OSError, match="disk full while writing"):
        rc.atomic_write_bytes(out, b"new")
    assert out.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_atomic_write_retries_a_transient_replace_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real, calls = os.replace, []

    def flaky(src: str, dst: str) -> None:
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(13, "locked")
        real(src, dst)

    monkeypatch.setattr(rc.os, "replace", flaky)
    rc.atomic_write_bytes(tmp_path / "a.json", b"x")
    assert (tmp_path / "a.json").read_bytes() == b"x" and len(calls) == 3


def test_atomic_write_gives_up_after_the_budget_naming_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(src: str, dst: str) -> None:
        raise PermissionError(13, "locked")

    monkeypatch.setattr(rc.os, "replace", locked)
    monkeypatch.setattr(rc, "REPLACE_RETRY_S", 0.05)
    with pytest.raises(PermissionError, match="a.json"):
        rc.atomic_write_bytes(tmp_path / "a.json", b"x")
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_sweeps_stale_tmp_only(tmp_path: Path) -> None:
    stale, fresh = tmp_path / ".a.json.old.tmp", tmp_path / ".a.json.new.tmp"
    stale.write_bytes(b"")
    fresh.write_bytes(b"")
    old = time.time() - 7200
    os.utime(stale, (old, old))
    rc.atomic_write_bytes(tmp_path / "a.json", b"x")
    assert not stale.exists() and fresh.exists()
