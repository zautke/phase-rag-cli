#!/usr/bin/env python3
# tests/test_p01_to_p04.py
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

import p01_load
import p02_markdown
import p03_parse
import p04_chunk
import rag_contracts as rc

runner = CliRunner()


def test_strict_pydantic_contracts_reject_invalid_fields() -> None:
    """Verify extra='forbid' and strict=True on BasePhasePayload and ingestion schemas."""
    with pytest.raises(ValidationError):
        rc.Phase01LoadedOutput.model_validate(
            {
                "run_id": "20261031T000000Z",
                "phase_name": "01_loading",
                "timestamp": "2026-10-31T00:00:00Z",
                "documents": [],
                "extra_illegal_field": "forbidden",
            }
        )

    with pytest.raises(ValidationError):
        # strict=True rejects int where str is expected
        rc.RawDocument(
            doc_id=123,  # type: ignore[arg-type]
            source_uri="s3://bucket/doc.md",
            mime_type="text/markdown",
            raw_content="hello",
        )

    with pytest.raises(ValidationError):
        rc.DocumentChunk.model_validate(
            {
                "chunk_id": "c1",
                "parent_section_id": "s1",
                "doc_id": "d1",
                "text": "some words",
                "token_count": "not_an_int",
                "header_hierarchy": ["H1"],
                "parent_markdown": "### H1\nsome words",
            }
        )


def test_ast_no_bare_print_in_any_module() -> None:
    """Zero print() to stdout in every phase/engine module (stdout is the JSON payload only)."""
    root = Path(__file__).resolve().parent.parent
    modules = [*root.glob("p[0-9][0-9]_*.py"), *(root / f"{n}.py" for n in (
        "rag_contracts", "hybrid_engine", "chunkers", "model_fetch", "rag_logging")),
        *(root / "loaders").glob("*.py")]
    assert any(m.parent.name == "loaders" for m in modules)
    for fpath in modules:
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=fpath.name)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
                    and all(k.arg != "file" or ast.unparse(k.value) == "sys.stdout"
                            for k in node.keywords)):  # file=<anything but sys.stdout> is fine
                pytest.fail(f"print() to stdout found in {fpath.name}:{node.lineno}")


def test_contract_chain_continuity_p01_to_p04() -> None:
    """Verify Phase[N].output_model is Phase[N+1].input_model for Phases 01..04."""
    assert p01_load.cli_engine.input_model is None
    assert p01_load.cli_engine.output_model is rc.Phase01LoadedOutput
    assert p02_markdown.cli_engine.input_model is rc.Phase01LoadedOutput
    assert p02_markdown.cli_engine.output_model is rc.Phase02MarkdownOutput
    assert p03_parse.cli_engine.input_model is rc.Phase02MarkdownOutput
    assert p03_parse.cli_engine.output_model is rc.Phase03ParsedOutput
    assert p04_chunk.cli_engine.input_model is rc.Phase03ParsedOutput
    assert p04_chunk.cli_engine.output_model is rc.Phase04ChunkedOutput


def test_p01_to_p04_file_io_and_triplex_streams(tmp_path: Path) -> None:
    """Test p01 -> p02 -> p03 -> p04 via --in-file / --out-file with stderr Rich telemetry and pure stdout JSON."""
    root = Path(__file__).resolve().parent.parent
    f01 = tmp_path / "01_loaded.json"
    f02 = tmp_path / "02_markdown.json"
    f03 = tmp_path / "03_parsed.json"
    f04 = tmp_path / "04_chunked.json"

    # Phase 01
    proc01 = subprocess.run(
        [sys.executable, str(root / "p01_load.py"), "-o", str(f01)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert f01.exists()
    assert "Phase 01: Document Loading" in proc01.stderr
    out01_stdout = rc.Phase01LoadedOutput.model_validate_json(proc01.stdout)
    out01_disk = rc.Phase01LoadedOutput.model_validate_json(f01.read_text(encoding="utf-8"))
    assert out01_stdout.model_dump() == out01_disk.model_dump()
    assert len(out01_disk.documents) == 2

    # Phase 02
    proc02 = subprocess.run(
        [sys.executable, str(root / "p02_markdown.py"), "-i", str(f01), "-o", str(f02)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert f02.exists()
    assert "Phase 02: Pre-Process to Markdown" in proc02.stderr
    out02_stdout = rc.Phase02MarkdownOutput.model_validate_json(proc02.stdout)
    out02_disk = rc.Phase02MarkdownOutput.model_validate_json(f02.read_text(encoding="utf-8"))
    assert out02_stdout.model_dump() == out02_disk.model_dump()
    assert out02_disk.run_id == out01_disk.run_id
    assert "# Hybrid RAG Architecture" in out02_disk.documents[0].clean_markdown

    # Phase 03
    proc03 = subprocess.run(
        [sys.executable, str(root / "p03_parse.py"), "-i", str(f02), "-o", str(f03)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert f03.exists()
    assert "Phase 03: Structural Parsing" in proc03.stderr
    out03_stdout = rc.Phase03ParsedOutput.model_validate_json(proc03.stdout)
    out03_disk = rc.Phase03ParsedOutput.model_validate_json(f03.read_text(encoding="utf-8"))
    assert out03_stdout.model_dump() == out03_disk.model_dump()
    assert len(out03_disk.sections) == 3
    assert out03_disk.sections[1].header_path == ["Hybrid RAG Architecture", "Late Chunking"]

    # Phase 04
    proc04 = subprocess.run(
        [
            sys.executable,
            str(root / "p04_chunk.py"),
            "-i",
            str(f03),
            "-o",
            str(f04),
            "-m",
            "10",
            "-v",
            "2",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert f04.exists()
    assert "Phase 04: Semantic Chunking" in proc04.stderr
    out04_stdout = rc.Phase04ChunkedOutput.model_validate_json(proc04.stdout)
    out04_disk = rc.Phase04ChunkedOutput.model_validate_json(f04.read_text(encoding="utf-8"))
    assert out04_stdout.model_dump() == out04_disk.model_dump()
    assert len(out04_disk.chunks) >= 4
    assert all(chk.token_count <= 10 for chk in out04_disk.chunks)


def test_p01_to_p04_stdin_stdout_pipe_and_bom_tolerance(tmp_path: Path) -> None:
    """Verify p01 | p02 | p03 | p04 subprocess piping via stdin/stdout and UTF-8 BOM handling."""
    root = Path(__file__).resolve().parent.parent

    # Create custom source_dir with markdown and txt files
    src_dir = tmp_path / "corpus"
    src_dir.mkdir()
    (src_dir / "alpha.md").write_text(
        "# Section One\nFirst paragraph words here.\n## Sub Section\nMore technical content here.",
        encoding="utf-8",
    )

    p1 = subprocess.run(
        [
            sys.executable,
            str(root / "p01_load.py"),
            "--source-dir",
            str(src_dir),
            "--out-file",
            str(tmp_path / "p1.json"),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert p1.stderr == ""

    # Prepend UTF-8 BOM (\ufeff) to simulate PowerShell pipe behavior
    bom_prefixed_p1 = "\ufeff" + p1.stdout

    p2 = subprocess.run(
        [
            sys.executable,
            str(root / "p02_markdown.py"),
            "--out-file",
            str(tmp_path / "p2.json"),
            "--quiet",
        ],
        input=bom_prefixed_p1,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )

    p3 = subprocess.run(
        [
            sys.executable,
            str(root / "p03_parse.py"),
            "--out-file",
            str(tmp_path / "p3.json"),
            "--quiet",
        ],
        input=p2.stdout,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )

    p4 = subprocess.run(
        [
            sys.executable,
            str(root / "p04_chunk.py"),
            "--out-file",
            str(tmp_path / "p4.json"),
            "--max-words",
            "50",
            "--overlap",
            "10",
        ],
        input=p3.stdout,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )

    assert "Phase 04: Semantic Chunking" in p4.stderr
    final_obj = rc.Phase04ChunkedOutput.model_validate_json(p4.stdout)
    disk_obj = rc.Phase04ChunkedOutput.model_validate_json(
        (tmp_path / "p4.json").read_text(encoding="utf-8")
    )
    assert final_obj.model_dump() == disk_obj.model_dump()
    assert len(final_obj.chunks) == 2
    assert final_obj.chunks[0].doc_id == "alpha.md"  # doc_id = path relative to --source-dir
    assert final_obj.chunks[1].header_hierarchy == ["Section One", "Sub Section"]
    # same-stem / different-extension ids: tests/test_p01_load.py::test_n22_*

