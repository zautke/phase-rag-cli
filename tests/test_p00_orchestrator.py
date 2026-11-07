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


# --- D7: anchors used are the only ones marked seen; no domain fallback; HyDE is corpus-agnostic --
DOMAIN_WORDS = ("qdrant", "hnsw", "splade", "fusion", "crag", "cross-encoder", "chunking")


def p08_with(text: str) -> rc.Phase08RerankedOutput:
    ctx = rc.RerankedContextItem(
        chunk_id="c", doc_id="d", cross_encoder_score=0.1, expanded_parent_context=text
    )
    return rc.Phase08RerankedOutput(
        run_id="r", original_query="q", xml_context_block="<retrieved_context>\n</retrieved_context>",
        top_contexts=[ctx],
    )


def test_d7_only_used_anchors_become_seen() -> None:
    seen: set[str] = set()
    got = p00.synthesize_rewritten_query("why", "why", 1, p08_with(fresh_context(1)), seen)
    assert got is not None
    query, _ = got
    used = {f"anchor1word{i}" for i in range(4)}
    assert seen == used
    assert all(w in query for w in used)
    assert "anchor1word4" not in query


def test_d7_unused_terms_stay_available_for_next_attempt() -> None:
    seen: set[str] = set()
    p08 = p08_with(fresh_context(1))
    first = p00.synthesize_rewritten_query("why", "why", 1, p08, seen)
    second = p00.synthesize_rewritten_query("why", "why", 2, p08, seen)
    assert first is not None and second is not None
    assert all(f"anchor1word{i}" in second[0] for i in range(4, 8))


def test_d7_no_new_anchors_returns_none_without_domain_fallback() -> None:
    seen: set[str] = set()
    assert p00.synthesize_rewritten_query("why", "why", 1, p08_with("the and for it is"), seen) is None
    assert p00.synthesize_rewritten_query("why", "why", 2, p08_with(""), seen) is None
    assert seen == set()


def test_d7_loop_stops_and_reports_non_convergence_without_anchors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = Harness(monkeypatch, tmp_path, ctx_fn=lambda n: "the and for it is")
    res = h.run()
    assert res.exit_code == 0, res.output
    loop = h.loop()
    assert h.count("p06_query.py") == 1
    assert loop.total_attempts == 1 and not loop.converged
    assert "no new" in (loop.attempts_history[0].rewrite_reason or "").lower()
    assert loop.final_query == loop.initial_query


def test_d7_loop_stops_when_corpus_anchors_are_exhausted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = Harness(monkeypatch, tmp_path, ctx_fn=lambda n: fresh_context(1))  # same 8 words each time
    assert h.run("-r", "5").exit_code == 0
    # attempt 1 uses words 0-3, attempt 2 words 4-7, attempt 3 finds none -> stop (not 6 attempts)
    assert h.count("p06_query.py") == 3
    loop = h.loop()
    assert loop.total_attempts == 3 and not loop.converged


def test_d7_rewrites_carry_no_hardcoded_domain_vocabulary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = Harness(monkeypatch, tmp_path)
    assert h.run("-r", "2", "-q", "How hot is boiling water?").exit_code == 0
    for rec in h.loop().attempts_history:
        low = (rec.query_used + (rec.rewrite_reason or "")).lower()
        assert not any(w in low for w in DOMAIN_WORDS), low


def test_d7_hyde_passage_is_corpus_agnostic(tmp_path: Path) -> None:
    import p06_query

    f05 = tmp_path / "05.json"
    f05.write_text(
        rc.Phase05IndexedOutput(
            run_id="r", qdrant_collection="c", indexed_records=[],
            dense_backend="sentence_transformers", dense_model="d", sparse_model="s",
        ).model_dump_json(),
        encoding="utf-8",
    )
    out = tmp_path / "06.json"
    res = CliRunner().invoke(
        p06_query.app, ["-i", str(f05), "-o", str(out), "-s", "-q", "How hot is boiling water?"]
    )
    assert res.exit_code == 0, res.output
    hyde = rc.Phase06QueryPlanOutput.model_validate_json(out.read_text(encoding="utf-8")).hyde_passage
    assert "boiling water" in hyde
    assert not any(w in hyde.lower() for w in (*DOMAIN_WORDS, "hybrid", "rrf", "reciprocal"))


# --- D9: --in-file must exist; stdin read once; empty stdin falls back to the default file ------
def test_d9_missing_in_file_is_a_usage_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import p06_query

    h = Harness(monkeypatch, tmp_path)
    missing = str(tmp_path / "nope.json")
    for app in (p00.app, p06_query.app):
        res = CliRunner().invoke(app, ["-i", missing, "-s"], input=h.f05.read_text(encoding="utf-8"))
        assert res.exit_code == 2, res.output
        assert "not found" in res.output.lower()
    assert h.calls == []  # stdin was not used as a silent substitute


def test_d9_empty_stdin_falls_back_to_default_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = Harness(monkeypatch, tmp_path)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "05_indexed.json").write_text(h.f05.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(p00.app, ["-s", "-r", "0", "-o", str(tmp_path / "o" / "00.json")], input="")
    assert res.exit_code == 0, res.output
    assert h.count("p06_query.py") == 1


def test_d9_empty_stdin_without_default_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h = Harness(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(p00.app, ["-s", "-o", str(tmp_path / "o.json")], input="")
    assert res.exit_code == 2, res.output
    assert h.calls == []


def test_d9_piped_stdin_is_read_once_and_used(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    h = Harness(monkeypatch, tmp_path)
    res = CliRunner().invoke(
        p00.app,
        ["-s", "-r", "0", "-o", str(tmp_path / "o" / "00.json")],
        input=h.f05.read_text(encoding="utf-8"),
    )
    assert res.exit_code == 0, res.output
    assert h.count("p06_query.py") == 1


def test_d9_other_phases_empty_stdin_is_a_usage_error(tmp_path: Path) -> None:
    import p06_query

    res = CliRunner().invoke(p06_query.app, ["-o", str(tmp_path / "o.json")], input="")
    assert res.exit_code == 2, res.output


# --- D13: P00 forwards only options the user set explicitly --------------------------------------
def test_d13_unset_options_are_not_forwarded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("RAG_CRAG_THRESHOLD", raising=False)
    monkeypatch.setenv("QDRANT_URL", "http://env-only:1")  # env-set, not on the command line
    h = Harness(monkeypatch, tmp_path)
    assert h.run("-r", "0").exit_code == 0
    assert sorted(a for a in h.args("p07_retrieve.py") if a.startswith("--")) == ["--out-file"]
    assert sorted(a for a in h.args("p08_rerank.py") if a.startswith("--")) == ["--out-file"]
    assert [a for a in h.args("p09_generate.py") if a.startswith("--")] == ["--out-file"]


def test_d13_explicit_options_are_forwarded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("RAG_CRAG_THRESHOLD", raising=False)
    h = Harness(monkeypatch, tmp_path)
    res = h.run("-r", "0", "-t", "0.8", "-b", "fastembed", "-m", "x/y", "-p", "/q", "-u", "http://x:1")
    assert res.exit_code == 0, res.output
    a09, a08, a07 = h.args("p09_generate.py"), h.args("p08_rerank.py"), h.args("p07_retrieve.py")
    assert a09[a09.index("--crag-threshold") + 1] == "0.8"
    assert a08[a08.index("--backend") + 1] == "fastembed" and a08[a08.index("--model") + 1] == "x/y"
    assert a07[a07.index("--qdrant-path") + 1] == "/q"
    assert a07[a07.index("--qdrant-url") + 1] == "http://x:1"


def test_d13_env_threshold_is_left_to_the_child(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RAG_CRAG_THRESHOLD", "0.9")
    h = Harness(monkeypatch, tmp_path)
    assert h.run("-r", "0").exit_code == 0
    assert "--crag-threshold" not in h.args("p09_generate.py")  # child inherits the env var
