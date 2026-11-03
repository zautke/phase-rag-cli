import subprocess
import sys
from pathlib import Path

from p04b_graph import build_graph, extract_entities_heuristic
from rag_contracts import (
    DocumentChunk,
    GraphArtifact,
    ParsedSection,
    Phase03ParsedOutput,
)

ROOT = Path(__file__).resolve().parent.parent


def chunk(cid: str, text: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=cid,
        parent_section_id="s",
        doc_id="d",
        text=text,
        token_count=len(text.split()),
        header_hierarchy=["H"],
        parent_markdown=text,
    )


def run(args: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        input=stdin,
        stdin=None if stdin is not None else subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )


def make_04(tmp_path: Path, body: str) -> Path:
    sec = ParsedSection(section_id="s", doc_id="d", header_path=["H"], body=body, metadata={})
    in03 = tmp_path / "03.json"
    in03.write_text(Phase03ParsedOutput(run_id="r1", sections=[sec]).model_dump_json(), encoding="utf-8")
    proc = run(["p04_chunk.py", "-s", "recursive", "-i", str(in03), "-o", str(tmp_path / "04.json"), "-q"])
    assert proc.returncode == 0, proc.stderr
    return tmp_path / "04.json"


def test_extract_entities_heuristic_basic():
    text = "Qdrant fuses Jina-v3 with SPLADE. The end."
    assert extract_entities_heuristic(text) == ["Qdrant", "Jina-v3", "SPLADE"]


def test_extract_entities_strips_leading_stopwords():
    assert extract_entities_heuristic("The Qdrant fuses SPLADE.") == ["Qdrant", "SPLADE"]
    assert extract_entities_heuristic("The. It And") == []


def test_build_graph_cooccurrence_weight():
    chunks = [chunk("c1", "Qdrant uses SPLADE here."), chunk("c2", "SPLADE and Qdrant again.")]
    nodes, edges = build_graph(chunks)
    assert len(edges) == 1
    e = edges[0]
    assert (e.source, e.target, e.weight) == ("Qdrant", "SPLADE", 2)
    assert len(e.chunk_ids) == 2
    assert {n.entity for n in nodes} == {"Qdrant", "SPLADE"}


def test_p04b_passthrough_byte_identical(tmp_path):
    in04 = make_04(tmp_path, "Qdrant fuses SPLADE. Jina helps Qdrant.\n\nSPLADE rocks.")
    raw = in04.read_bytes().replace(b"\r\n", b"\n")
    graph = tmp_path / "g.json"
    proc = run(["p04b_graph.py", "-i", str(in04), "-o", str(tmp_path / "out.json"), "-g", str(graph), "-q"])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.replace(b"\r\n", b"\n") == raw.rstrip(b"\n") + b"\n"
    assert b'"chunk_strategy": "recursive"' in proc.stdout
    art = GraphArtifact.model_validate_json(graph.read_text(encoding="utf-8"))
    assert art.run_id == "r1"
    assert art.nodes


def test_p04b_zero_entities_still_passes_through(tmp_path):
    in04 = make_04(tmp_path, "nothing capitalised here at all.")
    graph = tmp_path / "g.json"
    proc = run(["p04b_graph.py", "-i", str(in04), "-o", str(tmp_path / "out.json"), "-g", str(graph), "-q"])
    assert proc.returncode == 0, proc.stderr
    art = GraphArtifact.model_validate_json(graph.read_text(encoding="utf-8"))
    assert art.nodes == [] and art.edges == []
