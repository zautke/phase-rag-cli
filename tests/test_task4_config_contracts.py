#!/usr/bin/env python3
# tests/test_task4_config_contracts.py
"""D13 single threshold source, D16 Usage in --help, contract tightening, p07 plugin errors."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

import hybrid_engine as he
import p00_crag_orchestrator as p00
import p01_load
import p02_markdown
import p03_parse
import p04_chunk
import p05_index
import p06_query
import p07_retrieve
import p08_rerank
import p09_generate
import p10_evaluate
import rag_contracts as rc

ROOT = Path(__file__).resolve().parent.parent
ALL_CLIS = (p00, p01_load, p02_markdown, p03_parse, p04_chunk, p05_index, p06_query,
            p07_retrieve, p08_rerank, p09_generate, p10_evaluate)


def env_example() -> dict[str, str]:
    pairs = (ln.split("=", 1) for ln in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#"))
    return {k: v for k, v in pairs}


# --- D13 ------------------------------------------------------------------------------------------
def test_d13_env_example_threshold_matches_the_single_code_default() -> None:
    assert float(env_example()["RAG_CRAG_THRESHOLD"]) == rc.DEFAULT_CRAG_THRESHOLD
    assert env_example()["QDRANT_PATH"] == he.DEFAULT_QDRANT_PATH


def test_d13_every_env_example_key_is_read_by_code() -> None:
    sources = "\n".join(p.read_text(encoding="utf-8") for p in ROOT.glob("*.py"))
    for key in env_example():
        assert f'envvar="{key}"' in sources, f"{key} is in .env.example but nothing reads it"


def test_d13_no_second_literal_threshold_default() -> None:
    for mod in (p00, p09_generate):
        text = Path(mod.__file__).read_text(encoding="utf-8")
        assert not re.search(r"\]\s*=\s*0\.\d+", text), mod.__name__


def p08_file(tmp_path: Path, score: float) -> Path:
    f = tmp_path / "08.json"
    f.write_text(
        rc.Phase08RerankedOutput(
            run_id="r", original_query="how does it work",
            xml_context_block="<retrieved_context>\n</retrieved_context>",
            top_contexts=[rc.RerankedContextItem(
                chunk_id="c", doc_id="d", cross_encoder_score=score,
                expanded_parent_context="It works by doing things.")],
        ).model_dump_json(),
        encoding="utf-8",
    )
    return f


def verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: str | None, *args: str) -> str:
    if env is None:
        monkeypatch.delenv("RAG_CRAG_THRESHOLD", raising=False)
    else:
        monkeypatch.setenv("RAG_CRAG_THRESHOLD", env)
    out = tmp_path / "09.json"
    res = CliRunner().invoke(p09_generate.app, ["-i", str(p08_file(tmp_path, 0.8)), "-o", str(out), "-q", *args])
    assert res.exit_code == 0, res.output
    return rc.Phase09GenerationOutput.model_validate_json(out.read_text(encoding="utf-8")).crag_verdict


def test_d13_p09_reads_threshold_from_env_and_flag_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert verdict(tmp_path, monkeypatch, None) == "GROUNDED"  # 0.8 >= default 0.65
    assert verdict(tmp_path, monkeypatch, "0.95") == "REWRITE_REQUIRED"
    assert verdict(tmp_path, monkeypatch, "0.95", "-t", "0.5") == "GROUNDED"


# --- D16 ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mod", ALL_CLIS, ids=lambda m: m.__name__)
def test_d16_usage_text_is_shown_by_help(mod) -> None:
    res = CliRunner().invoke(mod.app, ["--help"], terminal_width=200)
    assert res.exit_code == 0, res.output
    norm = lambda s: re.sub(r"\s+", " ", s)
    for line in mod.Usage().splitlines():
        assert norm(line) in norm(res.output), line


# --- contracts ------------------------------------------------------------------------------------
def gen_kwargs(verdict_value: str) -> dict:
    return {"run_id": "r", "original_query": "q", "crag_verdict": verdict_value, "grounded_confidence": 0.1,
                "synthesized_answer": "a", "citations": [], "xml_context_block": "x"}


def test_crag_verdict_is_a_closed_literal() -> None:
    rc.Phase09GenerationOutput(**gen_kwargs("GROUNDED"))
    rc.Phase09GenerationOutput(**gen_kwargs("REWRITE_REQUIRED"))
    with pytest.raises(ValidationError):
        rc.Phase09GenerationOutput(**gen_kwargs("AMBIGUOUS"))
    with pytest.raises(ValidationError):
        rc.CRAGAttemptRecord(attempt=1, query_used="q", crag_verdict="MAYBE", grounded_confidence=0.0,
                             top_chunk_ids=[])


def test_phase10_does_not_redeclare_base_run_id() -> None:
    assert "run_id" not in rc.Phase10EvalOutput.__annotations__
    assert "metadata_filters" not in rc.BasePhasePayload.model_fields
    assert list(rc.Phase06QueryPlanOutput.__annotations__).count("metadata_filters") == 1


# --- p07: unusable embedder named by the P06 artifact -> exit 2, clean stdout ----------------------
@pytest.mark.parametrize(
    ("dense_backend", "dense_model", "sparse_model", "needle"),
    [
        ("nope", "m", "prithivida/Splade_PP_en_v1", "Unknown dense backend"),
        ("fastembed", "no/such-dense-model", "prithivida/Splade_PP_en_v1", "no/such-dense-model"),
    ],
)
def test_p07_unknown_backend_or_model_exit2(
    tmp_path: Path, dense_backend: str, dense_model: str, sparse_model: str, needle: str
) -> None:
    plan = rc.Phase06QueryPlanOutput(
        run_id="r", original_query="q", route="x", sub_queries=["q"], hyde_passage="h",
        metadata_filters={}, qdrant_collection="c", dense_backend=dense_backend,
        dense_model=dense_model, sparse_model=sparse_model,
    )
    f06 = tmp_path / "06.json"
    f06.write_text(plan.model_dump_json(), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "p07_retrieve.py"), "-i", str(f06), "-o", str(tmp_path / "07.json"),
         "-p", str(tmp_path / "q")],
        capture_output=True, env={**os.environ, "HF_HUB_OFFLINE": "1"}, check=False,
    )
    assert proc.returncode == 2, proc.stderr.decode()[-600:]
    assert proc.stdout == b""
    flat = re.sub(rb"[\s\xe2\x94\x80-\x94\x9f]+", b"", proc.stderr)  # drop Rich box + wrapping
    assert needle.replace(" ", "").encode() in flat and b"Traceback" not in proc.stderr


def test_p07_unknown_sparse_model_exit2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = rc.Phase06QueryPlanOutput(
        run_id="r", original_query="q", route="x", sub_queries=["q"], hyde_passage="h",
        metadata_filters={}, qdrant_collection="c", dense_backend="fastembed",
        dense_model="m", sparse_model="no/such-sparse-model",
    )
    f06 = tmp_path / "06.json"
    f06.write_text(plan.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(p07_retrieve, "embed_dense_batch", lambda *a, **k: [[0.0]])  # no dense load
    res = CliRunner().invoke(p07_retrieve.app, ["-i", str(f06), "-o", str(tmp_path / "07.json"), "-p", str(tmp_path)])
    assert res.exit_code == 2, res.output
    assert "no/such-sparse-model" in re.sub(r"[\s│]+", "", res.output)
