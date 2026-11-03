import subprocess
import sys
from pathlib import Path

import pytest

from chunkers import chunk_recursive, chunk_sliding_window, resolve_chunker
from rag_contracts import ParsedSection, Phase03ParsedOutput, Phase04ChunkedOutput

ROOT = Path(__file__).resolve().parent.parent


def sec(body: str) -> ParsedSection:
    return ParsedSection(section_id="s", doc_id="d", header_path=["H1", "H2"], body=body, metadata={})


def test_sliding_window_legacy_parity():
    chunks = chunk_sliding_window(sec(" ".join(f"w{i}" for i in range(20))), 8, 2)
    assert [c.chunk_id for c in chunks] == ["s_chk_0", "s_chk_1", "s_chk_2", "s_chk_3"]
    assert [c.text.split()[0] for c in chunks] == ["w0", "w6", "w12", "w18"]
    assert chunks[-1].text == "w18 w19"


def test_recursive_paragraphs_then_sentences():
    body = "Alpha beta gamma.\n\nOne two three. Four five six. Seven eight nine."
    chunks = chunk_recursive(sec(body), 5, 0)
    assert [c.text for c in chunks] == [
        "Alpha beta gamma.",
        "One two three.",
        "Four five six.",
        "Seven eight nine.",
    ]
    assert [c.chunk_id for c in chunks] == [f"s_rec_{i}" for i in range(4)]


def test_recursive_chunk_ids_unique_for_long_sentences():
    s1 = " ".join(f"a{i}" for i in range(12)) + "."
    s2 = " ".join(f"b{i}" for i in range(12)) + "."
    chunks = chunk_recursive(sec(f"{s1} {s2}"), 5, 0)
    ids = [c.chunk_id for c in chunks]
    assert len(chunks) == 6 and len(set(ids)) == 6
    assert all(c.text for c in chunks)


def test_recursive_empty_body_yields_no_chunks():
    assert chunk_recursive(sec("  \n\n "), 5, 0) == []


def test_resolve_chunker_unknown_lists_known_names():
    with pytest.raises(KeyError) as ei:
        resolve_chunker("nope")
    assert "sliding_window" in ei.value.args[0] and "recursive" in ei.value.args[0]


def test_phase04_output_without_chunk_strategy_still_validates():
    legacy = {"run_id": "r", "chunks": []}
    assert Phase04ChunkedOutput.model_validate(legacy).chunk_strategy == "sliding_window"


def test_p04_cli_unknown_strategy_exit2_clean_stdout(tmp_path):
    in03 = tmp_path / "03.json"
    in03.write_text(
        Phase03ParsedOutput(run_id="r", sections=[sec("a b c")]).model_dump_json(),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "p04_chunk.py", "-s", "nope", "-i", str(in03), "-o", str(tmp_path / "o.json")],
        cwd=ROOT,
        check=False,
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )
    assert proc.returncode == 2
    assert proc.stdout == b""
    assert b"Known:" in proc.stderr
