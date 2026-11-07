#!/usr/bin/env python3
# verify_pipeline.py
"""Single battery core. verify_pipeline.ps1 / verify_pipeline.sh only forward flags here."""
from __future__ import annotations

import argparse
import ast
import importlib
import itertools
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = Path("artifacts")
QDRANT = "./qdrant_storage"
FE_RERANK = "jinaai/jina-reranker-v2-base-multilingual"
PHASES = [  # (number, module, output schema)
    ("01", "p01_load", "Phase01LoadedOutput"),
    ("02", "p02_markdown", "Phase02MarkdownOutput"),
    ("03", "p03_parse", "Phase03ParsedOutput"),
    ("04", "p04_chunk", "Phase04ChunkedOutput"),
    ("05", "p05_index", "Phase05IndexedOutput"),
    ("06", "p06_query", "Phase06QueryPlanOutput"),
    ("07", "p07_retrieve", "Phase07RetrievedOutput"),
    ("08", "p08_rerank", "Phase08RerankedOutput"),
    ("09", "p09_generate", "Phase09GenerationOutput"),
    ("10", "p10_evaluate", "Phase10EvalOutput"),
]
AUDITED = [m for _, m, _ in PHASES] + [
    "p00_crag_orchestrator", "rag_contracts", "hybrid_engine", "chunkers", "model_fetch"]
PIPE = [  # Stage 2: (cli, args)
    ("rag-p01", []), ("rag-p02", []), ("rag-p03", []),
    ("rag-p04", ["--max-words", "50", "--overlap", "10"]),
    ("rag-p05", ["--collection", "pipe_hybrid_qdrant", "--qdrant-path", QDRANT]),
    ("rag-p06", ["--query", "How does Qdrant fuse Jina-v3 dense and SPLADE sparse vectors?"]),
    ("rag-p07", ["--qdrant-path", QDRANT, "--rrf-k", "60", "--top-k", "5"]),
    ("rag-p08", ["--backend", "fastembed", "--model", FE_RERANK, "--top-n", "3"]),
    ("rag-p09", ["--crag-threshold", "0.50"]),
    ("rag-p10", []),
]


def Usage() -> str:
    return """Usage: verify_pipeline.py [-q | --quiet] [-s | --skip-sync] [-h | --help]

Runs the 4-stage verification battery (cwd-independent; PASS = exit 0):
  Stage 0: uv sync, ruff, AST syntax, zero print() in phase modules, strict+forbid schemas,
           phase type-chain continuity, client.close() in p05/p07; then wipes artifacts/ + qdrant_storage/
  Stage 1: isolated rag-p01..p10 (+ p04 -s recursive): exit 0, stderr panel, artifact on disk,
           stdout == disk validates with the phase model; negatives (strategy, dense backend,
           missing --in-file) must exit 2 with empty stdout
  Stage 2: full 10-phase `uv run` pipe via Popen chain, every exit checked
  Stage 3: rag-p00 CRAG loop: --crag-threshold 0.92 must NOT converge; default run must go
           REWRITE_REQUIRED -> GROUNDED

  -q, --quiet       Do not echo captured phase stderr (always kept in the log, shown on failure)
  -s, --skip-sync   Skip 'uv sync --all-extras'
  -h, --help        Show this help and exit

Log: verify_logs/verify_<host>_<UTC ts>.log (gitignored, never wiped). Last stderr line: JSON metrics."""


def a(name: str) -> str:
    return str(ART / name)


class Fail(Exception):
    pass


class Battery:
    def __init__(self, quiet: bool) -> None:
        self.quiet = quiet
        self.t0 = time.monotonic()
        (ROOT / "verify_logs").mkdir(exist_ok=True)  # D3: outside artifacts/, which Stage 0 wipes
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        self.log_path = ROOT / "verify_logs" / f"verify_{socket.gethostname().lower()}_{stamp}.log"
        self.log = self.log_path.open("a", encoding="utf-8")
        self.say(f"-> Log: {self.log_path}")

    def say(self, msg: str, echo: bool = True) -> None:
        self.log.write(msg + "\n")
        self.log.flush()
        if echo:
            print(msg, file=sys.stderr, flush=True)

    def banner(self, title: str) -> None:
        self.say(f"\n{'=' * 78}\n {title}\n{'=' * 78}")

    def check(self, ok: bool, msg: str) -> None:
        if not ok:
            raise Fail(msg)

    def run(self, label: str, tag: str, args: list[str], expect: int = 0) -> subprocess.CompletedProcess:
        """uv run <args> with stdin closed; stdout/stderr kept in artifacts/, stderr also logged."""
        self.say(f"-> {label}: uv run {' '.join(args)}")
        proc = subprocess.run(["uv", "run", *args], stdin=subprocess.DEVNULL, capture_output=True, check=False)
        (ART / f"stdout_{tag}.json").write_bytes(proc.stdout)
        (ART / f"stderr_{tag}.txt").write_bytes(proc.stderr)
        err = proc.stderr.decode("utf-8", errors="replace")
        self.say(err, echo=not self.quiet)
        if proc.returncode != expect:
            tail = "\n".join(err.splitlines()[-10:])
            raise Fail(f"{label}: exit={proc.returncode} (expected {expect}). stderr tail:\n{tail}")
        return proc

    def validate(self, label: str, disk: Path, stdout: bytes, schema: str):
        """Both the persisted artifact and the stdout stream must satisfy the strict phase model and agree."""
        import rag_contracts as rc

        self.check(disk.is_file() and disk.stat().st_size > 0, f"{label}: artifact {disk} missing or empty")
        model = getattr(rc, schema)
        d = model.model_validate_json(disk.read_text(encoding="utf-8-sig"))
        s = model.model_validate_json(stdout.decode("utf-8-sig"))
        self.check(d.model_dump() == s.model_dump(), f"{label}: disk JSON and stdout stream diverged")
        self.say(f"  [OK] {label}: {schema} run_id={d.run_id} | disk == stdout")
        return d

    def phase(self, label: str, tag: str, args: list[str], artifact: str, schema: str):
        proc = self.run(label, tag, args)
        self.check(bool(proc.stderr.strip()), f"{label}: stderr empty (Rich panel missing)")
        return self.validate(label, Path(artifact), proc.stdout, schema)

    def negative(self, label: str, tag: str, args: list[str], needle: str) -> None:
        proc = self.run(label, tag, args, expect=2)
        err = " ".join(proc.stderr.decode("utf-8", errors="replace").split())
        self.check(not proc.stdout, f"{label}: stdout not empty on a usage error")
        self.check(needle in err, f"{label}: {needle!r} missing from stderr")
        self.say(f"  [OK] {label}: exit 2, stdout empty, stderr has {needle!r}")

    # ---- stages -------------------------------------------------------------------------------
    def stage0(self, skip_sync: bool) -> None:
        self.banner("STAGE 0: ENVIRONMENT SYNC & STATIC REVIEW")
        if not skip_sync:
            self.say("-> uv sync --all-extras")
            self.check(subprocess.run(["uv", "sync", "--all-extras", "--quiet"], check=False).returncode == 0,
                       "uv sync failed")
        ruff = subprocess.run(["uv", "run", "ruff", "check", "."], capture_output=True, text=True, check=False)
        self.say(ruff.stdout + ruff.stderr, echo=ruff.returncode != 0)
        self.check(ruff.returncode == 0, "ruff check failed")
        for path in sorted(ROOT.glob("*.py")) + sorted((ROOT / "tests").glob("*.py")):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in AUDITED:
            tree = ast.parse((ROOT / f"{name}.py").read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
                        and all(k.arg != "file" or ast.unparse(k.value) == "sys.stdout"
                                for k in node.keywords)):  # file=<anything but sys.stdout> is fine
                    raise Fail(f"print() to stdout in {name}.py:{node.lineno} (corrupts the JSON pipe)")
        import rag_contracts as rc

        schemas = [o for o in vars(rc).values() if isinstance(o, type) and o.__module__ == "rag_contracts"
                   and hasattr(o, "model_validate_json")]
        for cls in schemas:
            cfg = cls.model_config
            self.check(cfg.get("strict") is True and cfg.get("extra") == "forbid",
                       f"{cls.__name__}: ConfigDict must be strict=True, extra='forbid'")
        engines = [importlib.import_module(m).cli_engine for _, m, _ in PHASES]
        self.check(engines[0].input_model is None, "Phase 01 input_model must be None")
        for up, down in itertools.pairwise(engines):
            self.check(up.output_model is down.input_model,
                       f"type mismatch {up.phase_title} ({up.output_model}) -> {down.phase_title}")
        for name in ("p05_index", "p07_retrieve"):
            self.check("client.close()" in (ROOT / f"{name}.py").read_text(encoding="utf-8"),
                       f"missing client.close() in {name}.py")
        self.say(f"  [OK] static review: ruff clean, {len(schemas)} strict schemas, 0 print leaks, chain aligned")
        shutil.rmtree(ART, ignore_errors=True)
        shutil.rmtree(ROOT / "qdrant_storage", ignore_errors=True)
        ART.mkdir()

    def stage1(self) -> dict[str, int]:
        self.banner("STAGE 1: ISOLATED PHASES 01 -> 10 + NEGATIVES")
        ph = self.phase
        ph("rag-p01", "01", ["rag-p01", "-o", a("01_loaded.json")], a("01_loaded.json"), "Phase01LoadedOutput")
        ph("rag-p02", "02", ["rag-p02", "-i", a("01_loaded.json"), "-o", a("02_markdown.json")],
           a("02_markdown.json"), "Phase02MarkdownOutput")
        ph("rag-p03", "03", ["rag-p03", "-i", a("02_markdown.json"), "-o", a("03_parsed.json")],
           a("03_parsed.json"), "Phase03ParsedOutput")
        sliding = ph("rag-p04", "04", ["rag-p04", "-i", a("03_parsed.json"), "-o", a("04_chunked.json"),
                                       "--max-words", "50", "--overlap", "10"],
                     a("04_chunked.json"), "Phase04ChunkedOutput")
        recursive = ph("rag-p04 -s recursive", "04_recursive",
                       ["rag-p04", "-i", a("03_parsed.json"), "-o", a("04_chunked_recursive.json"),
                        "-s", "recursive"], a("04_chunked_recursive.json"), "Phase04ChunkedOutput")
        self.negative("NEG rag-p04 --strategy nope", "neg_strategy",
                      ["rag-p04", "--strategy", "nope", "-i", a("03_parsed.json"), "-o", a("_neg.json")], "Known:")
        self.negative("NEG rag-p05 --dense-backend nope", "neg_backend",
                      ["rag-p05", "--dense-backend", "nope", "-i", a("04_chunked.json"), "-o", a("_neg.json")],
                      "Known:")
        self.negative("NEG rag-p02 missing --in-file", "neg_infile",
                      ["rag-p02", "-i", a("missing.json"), "-o", a("_neg.json")], "not found")
        ph("rag-p05", "05", ["rag-p05", "-i", a("04_chunked.json"), "-o", a("05_indexed.json"),
                             "--collection", "test_hybrid_qdrant", "--qdrant-path", QDRANT],
           a("05_indexed.json"), "Phase05IndexedOutput")
        ph("rag-p06", "06", ["rag-p06", "-i", a("05_indexed.json"), "-o", a("06_query_plan.json"), "--query",
                             "How does Hybrid RAG fuse dense and sparse vectors and when does CRAG rewrite?"],
           a("06_query_plan.json"), "Phase06QueryPlanOutput")
        ph("rag-p07", "07", ["rag-p07", "-i", a("06_query_plan.json"), "-o", a("07_retrieved.json"),
                             "--qdrant-path", QDRANT, "--rrf-k", "60", "--top-k", "6"],
           a("07_retrieved.json"), "Phase07RetrievedOutput")
        ph("rag-p08", "08", ["rag-p08", "-i", a("07_retrieved.json"), "-o", a("08_reranked.json"),
                             "--backend", "fastembed", "--model", FE_RERANK, "--top-n", "4"],
           a("08_reranked.json"), "Phase08RerankedOutput")
        ph("rag-p09", "09", ["rag-p09", "-i", a("08_reranked.json"), "-o", a("09_generated.json"),
                             "--crag-threshold", "0.55"], a("09_generated.json"), "Phase09GenerationOutput")
        ph("rag-p10", "10", ["rag-p10", "-i", a("09_generated.json"), "-o", a("10_evaluated.json")],
           a("10_evaluated.json"), "Phase10EvalOutput")
        return {"chunk_count_sliding": len(sliding.chunks), "chunk_count_recursive": len(recursive.chunks)}

    def stage2(self) -> None:
        self.banner("STAGE 2: FULL 10-PHASE PIPE")
        procs, upstream = [], subprocess.DEVNULL
        for cli, args in PIPE:
            err = (ART / f"stderr_pipe_{cli[-2:]}.txt").open("wb")
            p = subprocess.Popen(["uv", "run", cli, *args], stdin=upstream, stdout=subprocess.PIPE, stderr=err)
            if upstream is not subprocess.DEVNULL:
                upstream.close()
            upstream = p.stdout
            procs.append((cli, p, err))
        final = upstream.read()
        upstream.close()
        (ART / "pipe_final_stdout.json").write_bytes(final)
        codes, bad = [], []
        for cli, p, err in procs:
            p.wait()
            err.close()
            codes.append(p.returncode)
            log = (ART / f"stderr_pipe_{cli[-2:]}.txt").read_text(encoding="utf-8", errors="replace")
            self.say(log, echo=not self.quiet)
            if p.returncode:
                tail = "\n".join(log.splitlines()[-10:])
                bad.append(f"{cli}: exit={p.returncode}. stderr tail:\n{tail}")
        self.check(not bad, "pipe stage failed\n" + "\n".join(bad))
        self.say(f"  [OK] all {len(codes)} pipe stages exited 0 ({' '.join(map(str, codes))})")
        self.validate("PIPE_E2E", ART / "10_evaluated.json", final, "Phase10EvalOutput")

    def stage3(self) -> None:
        self.banner("STAGE 3: CRAG LOOPBACK")
        stress = ART / "crag_stress" / "00_crag_stress.json"
        out = self.phase("rag-p00 stress (-t 0.92)", "00_stress",
                         ["rag-p00", "-c", "-i", str(ART / "05_indexed.json"), "-o", str(stress),
                          "--qdrant-path", QDRANT, "--crag-threshold", "0.92", "--max-retries", "2"],
                         str(stress), "PhaseCRAGLoopOutput")
        self.check(not out.converged, f"0.92 run converged ({out.final_generation.crag_verdict}); must not")
        self.check(out.total_attempts == 3, f"0.92 run made {out.total_attempts} attempt(s); --max-retries 2 means 3")
        self.say(f"  [OK] 0.92 run did not converge after {out.total_attempts} attempts (rewrite loop exercised)")
        canon = ART / "00_crag_loop_summary.json"
        out = self.phase("rag-p00 default", "00_default",
                         ["rag-p00", "-c", "-i", str(ART / "05_indexed.json"), "-o", str(canon),
                          "--qdrant-path", QDRANT], str(canon), "PhaseCRAGLoopOutput")
        trail = " -> ".join(f"{r.grounded_confidence:.4f}" for r in out.attempts_history)
        first, verdict = out.attempts_history[0].crag_verdict, out.final_generation.crag_verdict
        self.check(first == "REWRITE_REQUIRED" and verdict == "GROUNDED" and out.converged,
                   f"default run: first={first} final={verdict} converged={out.converged} confidence {trail}")
        self.say(f"  [OK] default run REWRITE_REQUIRED -> GROUNDED in {out.total_attempts} attempt(s) | {trail}")


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False, usage="verify_pipeline.py [-q] [-s] [-h]  (see -h)")
    ap.add_argument("-q", "--quiet", action="store_true")
    ap.add_argument("-s", "--skip-sync", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    ns = ap.parse_args()
    if ns.help:
        print(Usage())
        return 0
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    bat = Battery(ns.quiet)
    metrics: dict[str, int | None] = {"chunk_count_sliding": None, "chunk_count_recursive": None}
    code = 0
    try:
        bat.stage0(ns.skip_sync)
        metrics.update(bat.stage1())
        bat.stage2()
        bat.stage3()
        bat.say("\nALL STATIC REVIEWS, ISOLATED PHASES, NEGATIVES, PIPE AND CRAG LOOP PASSED")
    except Exception as e:  # noqa: BLE001  Fail or anything else (ValidationError, missing uv, bad JSON)
        bat.say(f"\n[FAIL] {type(e).__name__}: {e}")
        bat.say(traceback.format_exc(), echo=False)
        code = 1
    metrics["verify_wall_ms"] = round((time.monotonic() - bat.t0) * 1000)
    bat.say(json.dumps(metrics))
    return code


if __name__ == "__main__":
    sys.exit(main())
