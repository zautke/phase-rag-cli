#!/usr/bin/env python3
# tests/test_p00_orchestrator.py
"""p00 loop behaviour with child phases faked: no model loads, no subprocesses."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import p00_crag_orchestrator as p00
import rag_contracts as rc

PLAN_FIELDS: dict[str, Any] = {
    "route": "hybrid_rag",
    "sub_queries": ["q"],
    "hyde_passage": "h",
    "metadata_filters": {},
    "qdrant_collection": "c",
    "dense_backend": "sentence_transformers",
    "dense_model": "d",
    "sparse_model": "s",
}


def fresh_context(n: int) -> str:
    """Eight corpus words that appear in no earlier attempt and not in the query."""
    return " ".join(f"anchor{n}word{i}" for i in range(8))


class Harness:
    """Fake invoke_cli_phase: P08 contexts come from ctx_fn(attempt), P09 verdict from grounded_at."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        ctx_fn: Any = fresh_context,
        grounded_at: int | None = None,
    ) -> None:
        self.calls: list[tuple[str, list[str], bool]] = []
        self.tmp = tmp_path
        self.ctx_fn = ctx_fn
        self.grounded_at = grounded_at
        self.f05 = tmp_path / "05.json"
        self.f05.write_text(
            rc.Phase05IndexedOutput(
                run_id="r", qdrant_collection="c", indexed_records=[],
                dense_backend="sentence_transformers", dense_model="d", sparse_model="s",
            ).model_dump_json(),
            encoding="utf-8",
        )
        monkeypatch.setattr(p00, "invoke_cli_phase", self.fake)

    def count(self, script: str) -> int:
        return sum(1 for c in self.calls if c[0] == script)

    def args(self, script: str, nth: int = 0) -> list[str]:
        return [c[1] for c in self.calls if c[0] == script][nth]

    def fake(self, script: str, input_json: str, args: list[str], quiet_child: bool) -> str:
        self.calls.append((script, args, quiet_child))
        n = self.count(script)
        query = args[args.index("--query") + 1] if "--query" in args else "q"
        plan = rc.Phase06QueryPlanOutput(run_id="r", original_query=query, **PLAN_FIELDS)
        if script == "p06_query.py":
            return plan.model_dump_json()
        if script == "p07_retrieve.py":
            return rc.Phase07RetrievedOutput(run_id="r", query_plan=plan, candidates=[]).model_dump_json()
        if script == "p08_rerank.py":
            ctx = rc.RerankedContextItem(
                chunk_id=f"c{n}", doc_id="d", cross_encoder_score=0.1,
                expanded_parent_context=self.ctx_fn(n),
            )
            return rc.Phase08RerankedOutput(
                run_id="r", original_query=query, xml_context_block="<retrieved_context>\n</retrieved_context>",
                top_contexts=[ctx],
            ).model_dump_json()
        if script == "p09_generate.py":
            ok = self.grounded_at is not None and n >= self.grounded_at
            return rc.Phase09GenerationOutput(
                run_id="r", original_query=query,
                crag_verdict="GROUNDED" if ok else "REWRITE_REQUIRED",
                grounded_confidence=0.1, synthesized_answer="a", citations=[],
                xml_context_block="<retrieved_context>\n</retrieved_context>",
            ).model_dump_json()
        return rc.Phase10EvalOutput(
            run_id="r", ndcg_at_k=1.0, context_precision=0.1, faithfulness_score=1.0,
            answer_relevance=1.0, hallucination_detected=False, final_answer="a",
        ).model_dump_json()

    def run(self, *extra: str, input: str | None = None) -> Any:
        out = self.tmp / "out" / "00.json"
        res = CliRunner().invoke(
            p00.app, ["-i", str(self.f05), "-o", str(out), "-s", *extra], input=input
        )
        self.out = out
        return res

    def loop(self) -> rc.PhaseCRAGLoopOutput:
        return rc.PhaseCRAGLoopOutput.model_validate_json(self.out.read_text(encoding="utf-8"))


# --- D6: child stderr is inherited (live progress), only stdout is captured --------------------
def test_d6_child_stderr_inherited_stdout_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def spy(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"a": 1}\n')

    monkeypatch.setattr(p00.subprocess, "run", spy)
    assert p00.invoke_cli_phase("p06_query.py", "{}", [], False) == '{"a": 1}'
    assert "capture_output" not in seen and seen.get("stderr") is None
    assert seen["stdout"] == subprocess.PIPE


def test_d6_child_progress_reaches_our_stderr_live(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    child = tmp_path / "child.py"
    child.write_text(
        "import sys\nsys.stderr.write('progress-line\\n')\nsys.stdout.write('{\"ok\": true}')\n",
        encoding="utf-8",
    )
    assert p00.invoke_cli_phase(str(child), "{}", [], False) == '{"ok": true}'
    cap = capfd.readouterr()
    assert "progress-line" in cap.err and cap.out == ""


def test_d6_failed_child_raises_with_exit_code(tmp_path: Path) -> None:
    child = tmp_path / "bad.py"
    child.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"exit 3"):
        p00.invoke_cli_phase(str(child), "{}", [], False)


# --- D12: --max-retries N = N retries after the first attempt ----------------------------------
@pytest.mark.parametrize(("retries", "attempts"), [(0, 1), (1, 2), (2, 3), (3, 4)])
def test_d12_max_retries_is_retries_after_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, retries: int, attempts: int
) -> None:
    h = Harness(monkeypatch, tmp_path)
    res = h.run("-r", str(retries))
    assert res.exit_code == 0, res.output
    assert h.count("p06_query.py") == attempts
    loop = h.loop()
    assert loop.total_attempts == attempts and not loop.converged


def test_d12_default_is_two_retries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    h = Harness(monkeypatch, tmp_path)
    assert h.run().exit_code == 0
    assert h.count("p06_query.py") == 3


def test_d12_negative_retries_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    h = Harness(monkeypatch, tmp_path)
    assert h.run("-r", "-1").exit_code == 2
    assert h.calls == []
