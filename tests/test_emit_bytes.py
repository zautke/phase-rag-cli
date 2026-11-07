#!/usr/bin/env python3
# tests/test_emit_bytes.py -- D-A1: stdout and --out-file get byte-identical UTF-8/LF payloads
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import rag_contracts as rc


def test_p01_stdout_and_artifact_are_byte_identical_lf(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.md").write_text("# Title\n\nbody text\n", encoding="utf-8")
    out = tmp_path / "01.json"
    proc = subprocess.run(
        [sys.executable, "-m", "p01_load", "-s", str(src), "-o", str(out), "-q"],
        capture_output=True,
        check=True,
    )
    art = out.read_bytes()
    assert proc.stdout == art
    assert b"\r" not in art
    assert art.endswith(b"}\n") and not art.endswith(b"\n\n")
    assert not art.startswith(b"\xef\xbb\xbf")
    rc.Phase01LoadedOutput.model_validate_json(art)  # load_upstream contract unchanged
