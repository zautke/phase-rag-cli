#!/usr/bin/env python3
# tests/test_verify_stage3.py -- D-D1: Stage 3 stress assertion (-t 0.99) over fake summaries
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

_spec = importlib.util.spec_from_file_location("verify_pipeline", Path(__file__).resolve().parent.parent / "verify_pipeline.py")
vp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vp)


def _summary(verdicts: list[str], queries: list[str], converged: bool = False) -> NS:
    hist = [NS(crag_verdict=v, query_used=q) for v, q in zip(verdicts, queries, strict=True)]
    return NS(converged=converged, total_attempts=len(hist), attempts_history=hist,
              final_generation=NS(crag_verdict=verdicts[-1]))


def test_converged_at_attempt_3_fails() -> None:
    bad = vp.stress_failures(_summary(["REWRITE_REQUIRED", "REWRITE_REQUIRED", "GROUNDED"], ["a", "b", "c"], converged=True))
    assert any("converged" in b for b in bad) and any("REWRITE_REQUIRED" in b for b in bad)


def test_three_rewrite_required_distinct_queries_pass() -> None:
    assert vp.stress_failures(_summary(["REWRITE_REQUIRED"] * 3, ["q", "q anchor1", "q anchor2"])) == []


def test_duplicate_queries_fail() -> None:
    assert any("distinct" in b for b in vp.stress_failures(_summary(["REWRITE_REQUIRED"] * 3, ["q", "q2", "q"])))


def test_wrong_attempt_count_fails() -> None:
    assert any("attempt" in b for b in vp.stress_failures(_summary(["REWRITE_REQUIRED"] * 2, ["q", "q2"])))
