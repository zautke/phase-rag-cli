"""Engine plugin seams (dense / sparse / rerank), D1 calibration, D5 cache root, D8 qdrant probe.

All models are mocked; nothing is downloaded or loaded.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import types
import warnings
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest
from huggingface_hub import constants
from pydantic import ValidationError
from typer.testing import CliRunner

import hybrid_engine as he
import p05_index
import p06_query
import p07_retrieve
import rag_contracts as rc

ROOT = Path(__file__).resolve().parent.parent


def _noop(*_a, **_k) -> None:
    return None


# --- registry lookup -------------------------------------------------------------------------
def test_registries_hold_expected_names() -> None:
    assert set(he.DENSE_BACKENDS) == {"sentence_transformers", "fastembed"}
    assert set(he.SPARSE_BACKENDS) == {"fastembed"}
    assert set(he.RERANK_BACKENDS) == {"sentence_transformers", "fastembed"}


@pytest.mark.parametrize("registry", ["DENSE_BACKENDS", "SPARSE_BACKENDS", "RERANK_BACKENDS"])
def test_resolve_backend_known_and_unknown(registry: str) -> None:
    reg = getattr(he, registry)
    name = min(reg)
    assert he.resolve_backend(reg, name, "x") is reg[name]
    with pytest.raises(ValueError, match=r"Known: .*" + name):
        he.resolve_backend(reg, "nope", "x")


def test_get_dense_embedder_unknown_backend_raises() -> None:
    with pytest.raises(ValueError, match="Known:"):
        he.get_dense_embedder("nope", "m")


def test_rerank_unknown_backend_raises() -> None:
    with pytest.raises(ValueError, match="Known:"):
        he.rerank_passages_batch("q", ["p"], backend="nope")


# --- dense plugin: fastembed (multitask query/passage) + singleton + dim + cache root --------
class FakeTextEmbedding:
    made: ClassVar[list[FakeTextEmbedding]] = []

    def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
        self.model_name, self.cache_dir, self.calls = model_name, cache_dir, []
        FakeTextEmbedding.made.append(self)

    embedding_size = 6

    def query_embed(self, texts):
        self.calls.append(("query", list(texts)))
        for _ in self.calls[-1][1]:
            yield np.full(6, 0.25, dtype=np.float32)

    def passage_embed(self, texts):
        self.calls.append(("passage", list(texts)))
        for _ in self.calls[-1][1]:
            yield np.full(6, 0.75, dtype=np.float32)


def test_dense_fastembed_uses_query_and_passage_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTextEmbedding.made.clear()
    monkeypatch.setattr(he, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr(he, "prefetch_fastembed", _noop)

    q = he.embed_dense_batch(["a", "b"], "fastembed", "test/dense-fe", query=True)
    d = he.embed_dense_batch(["c"], "fastembed", "test/dense-fe")
    assert q == [[0.25] * 6, [0.25] * 6]
    assert d == [[0.75] * 6]

    (model,) = FakeTextEmbedding.made  # singleton: one load for both calls
    assert model.calls == [("query", ["a", "b"]), ("passage", ["c"])]
    assert model.cache_dir == constants.HF_HUB_CACHE  # D5: one HF cache root
    _embed, dim = he.get_dense_embedder("fastembed", "test/dense-fe")
    assert dim == 6  # vector size comes from the loaded model


def test_dense_singleton_is_keyed_by_backend_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTextEmbedding.made.clear()
    monkeypatch.setattr(he, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr(he, "prefetch_fastembed", _noop)
    a1 = he.get_dense_embedder("fastembed", "test/key-a")
    a2 = he.get_dense_embedder("fastembed", "test/key-a")
    b = he.get_dense_embedder("fastembed", "test/key-b")
    assert a1 is a2 and a1 is not b
    assert [m.model_name for m in FakeTextEmbedding.made] == ["test/key-a", "test/key-b"]


def test_dense_sentence_transformers_path_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeST:
        def __init__(self, name: str, trust_remote_code: bool = False) -> None:
            assert trust_remote_code is True

        def get_embedding_dimension(self) -> int:
            return 4

        def get_sentence_embedding_dimension(self) -> int:  # sentence-transformers 6.x: FutureWarning (D-B1)
            warnings.warn('renamed to get_embedding_dimension', FutureWarning, stacklevel=2)
            return 4

        def encode(self, texts, show_progress_bar, normalize_embeddings):
            assert show_progress_bar is False and normalize_embeddings is True
            return np.ones((len(texts), 4), dtype=np.float32)

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeST))
    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(PreTrainedModel=type("P", (), {})))
    monkeypatch.setattr(he, "prefetch_st", _noop)
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        out = he.embed_dense_batch(["x", "y"], "sentence_transformers", "test/st-dense", query=True)
        assert he.get_dense_embedder("sentence_transformers", "test/st-dense")[1] == 4
    assert out == [[1.0] * 4, [1.0] * 4]


# --- sparse plugin ---------------------------------------------------------------------------
def test_sparse_fastembed_keyed_by_model_and_hf_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[tuple[str, str | None]] = []

    class FakeSparse:
        def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
            made.append((model_name, cache_dir))

        def embed(self, texts):
            for _ in texts:
                yield types.SimpleNamespace(indices=np.array([1, 2]), values=np.array([0.5, 0.25]))

    monkeypatch.setattr(he, "SparseTextEmbedding", FakeSparse)
    monkeypatch.setattr(he, "prefetch_fastembed", _noop)
    assert he.embed_sparse_batch(["t"], "test/sparse-a") == [([1, 2], [0.5, 0.25])]
    he.embed_sparse_batch(["t"], "test/sparse-a")
    he.embed_sparse_batch(["t"], "test/sparse-b")
    assert made == [("test/sparse-a", constants.HF_HUB_CACHE), ("test/sparse-b", constants.HF_HUB_CACHE)]


# --- D5: knob is gone ------------------------------------------------------------------------
def test_d5_fastembed_cache_dir_knob_removed() -> None:
    assert not hasattr(he, "fastembed_cache_dir")
    assert "RAG_FASTEMBED_CACHE_DIR" not in (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "RAG_FASTEMBED_CACHE_DIR" not in Path(he.__file__).read_text(encoding="utf-8")


# --- D1: reranker calibration is monotonic ---------------------------------------------------
def test_d1_fastembed_rerank_keeps_logit_order(monkeypatch: pytest.MonkeyPatch) -> None:
    import fastembed.rerank.cross_encoder as fe_ce

    logits = [1.00, 1.05, -2.0]

    class FakeCE:
        def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
            self.cache_dir = cache_dir

        def rerank(self, query, passages, batch_size=64):
            return iter(logits)

    monkeypatch.setattr(fe_ce, "TextCrossEncoder", FakeCE)
    monkeypatch.setattr(he, "prefetch_fastembed", _noop)
    scores = he.rerank_passages_batch("q", ["a", "b", "c"], model_name="test/fe-rerank", backend="fastembed")
    order_in = sorted(range(3), key=lambda i: -logits[i])
    order_out = sorted(range(3), key=lambda i: -scores[i])
    assert order_out == order_in == [1, 0, 2]
    assert all(0.0 < s < 1.0 for s in scores)
    assert scores[0] == round(1 / (1 + np.exp(-1.0)), 4)  # 1.00 is sigmoided too, not passed through


def test_d5_fastembed_reranker_uses_hf_cache_root(monkeypatch: pytest.MonkeyPatch) -> None:
    import fastembed.rerank.cross_encoder as fe_ce

    seen: list[str | None] = []

    class FakeCE:
        def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
            seen.append(cache_dir)

        def rerank(self, query, passages, batch_size=64):
            return iter([0.0] * len(passages))

    monkeypatch.setattr(fe_ce, "TextCrossEncoder", FakeCE)
    monkeypatch.setattr(he, "prefetch_fastembed", _noop)
    he.rerank_passages_batch("q", ["a"], model_name="test/fe-rerank-cache", backend="fastembed")
    assert seen == [constants.HF_HUB_CACHE]


def test_st_rerank_keeps_model_activation_and_clips_to_unit_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCrossEncoder:
        def __init__(self, name: str, trust_remote_code: bool = False, max_length: int = 0) -> None:
            pass

        def predict(self, pairs, batch_size, apply_softmax, show_progress_bar):
            return [1.7, -0.5, 0.0123, 0.5]  # a head without sigmoid yields out-of-range values

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(CrossEncoder=FakeCrossEncoder))
    monkeypatch.setattr(he, "prefetch_st", _noop)
    scores = he.rerank_passages_batch(
        "q", ["a", "b", "c", "d"], model_name="test/st-rerank", backend="sentence_transformers"
    )
    # in-range scores pass through untouched (no second sigmoid); out-of-range ones are clipped to [0, 1]
    assert scores == [1.0, 0.0, 0.0123, 0.5]


# --- D8: quiet qdrant probe ------------------------------------------------------------------
def test_d8_remote_probe_disables_compat_check_and_announces_fallback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    kwargs_seen: list[dict] = []

    class FakeQdrant:
        def __init__(self, **kw) -> None:
            kwargs_seen.append(kw)

        def get_collections(self):
            raise OSError("connection refused")

    monkeypatch.setattr(he, "QdrantClient", FakeQdrant)
    client = he.get_qdrant_client("http://127.0.0.1:1", str(tmp_path / "q"))
    assert isinstance(client, FakeQdrant)
    assert kwargs_seen[0]["check_compatibility"] is False
    assert kwargs_seen[1] == {"path": str(tmp_path / "q")}
    cap = capsys.readouterr()
    assert cap.out == ""
    lines = [ln for ln in cap.err.splitlines() if ln.strip()]
    assert len(lines) == 1 and "embedded" in lines[0] and "127.0.0.1:1" in lines[0]


def test_d8_no_url_is_silent(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    class FakeQdrant:
        def __init__(self, **kw) -> None:
            pass

    monkeypatch.setattr(he, "QdrantClient", FakeQdrant)
    he.get_qdrant_client(None, str(tmp_path))
    assert capsys.readouterr().err == ""


# --- contracts -------------------------------------------------------------------------------
PLUGIN = {"dense_backend": "fastembed", "dense_model": "m-d", "sparse_model": "m-s"}


def test_phase05_and_phase06_carry_plugin_fields_round_trip() -> None:
    p05 = rc.Phase05IndexedOutput(run_id="r", qdrant_collection="c", indexed_records=[], **PLUGIN)
    assert rc.Phase05IndexedOutput.model_validate_json(p05.model_dump_json()) == p05
    p06 = rc.Phase06QueryPlanOutput(
        run_id="r", original_query="q", route="x", sub_queries=["q"], hyde_passage="h",
        metadata_filters={}, qdrant_collection="c", **PLUGIN,
    )
    assert rc.Phase06QueryPlanOutput.model_validate_json(p06.model_dump_json()) == p06
    for model, payload in ((rc.Phase05IndexedOutput, p05), (rc.Phase06QueryPlanOutput, p06)):
        d = json.loads(payload.model_dump_json())
        for k in PLUGIN:
            bad = {kk: v for kk, v in d.items() if kk != k}
            with pytest.raises(ValidationError):
                model.model_validate(bad)


def test_p06_copies_plugin_fields_from_p05(tmp_path: Path) -> None:
    f05 = tmp_path / "05.json"
    f05.write_text(
        rc.Phase05IndexedOutput(run_id="r", qdrant_collection="col", indexed_records=[], **PLUGIN).model_dump_json(),
        encoding="utf-8",
    )
    out = tmp_path / "06.json"
    res = CliRunner().invoke(p06_query.app, ["-i", str(f05), "-o", str(out), "-s"])
    assert res.exit_code == 0, res.output
    p06 = rc.Phase06QueryPlanOutput.model_validate_json(out.read_text(encoding="utf-8"))
    assert (p06.dense_backend, p06.dense_model, p06.sparse_model) == ("fastembed", "m-d", "m-s")


def test_p07_encodes_with_exactly_the_upstream_backend_and_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plan = rc.Phase06QueryPlanOutput(
        run_id="r", original_query="q", route="x", sub_queries=["q"], hyde_passage="h",
        metadata_filters={}, qdrant_collection="c", **PLUGIN,
    )
    f06 = tmp_path / "06.json"
    f06.write_text(plan.model_dump_json(), encoding="utf-8")
    seen: dict = {}

    class Stop(Exception):
        pass

    def fake_dense(texts, backend, model, query=False):
        seen["dense"] = (backend, model, query)
        return [[0.0]]

    def fake_sparse(texts, model):
        seen["sparse"] = model
        return [([1], [1.0])]

    def stop(*_a, **_k):
        raise Stop

    monkeypatch.setattr(p07_retrieve, "embed_dense_batch", fake_dense)
    monkeypatch.setattr(p07_retrieve, "embed_sparse_batch", fake_sparse)
    monkeypatch.setattr(p07_retrieve, "get_qdrant_client", stop)
    res = CliRunner().invoke(p07_retrieve.app, ["-i", str(f06), "-o", str(tmp_path / "07.json")])
    assert isinstance(res.exception, Stop)
    assert seen == {"dense": ("fastembed", "m-d", True), "sparse": "m-s"}


# --- CLI: unknown backend -> exit 2, empty stdout, 'Known:' on stderr -------------------------
def _run(script: str, args: list[str], env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run([sys.executable, str(ROOT / script), *args], capture_output=True, env=env, check=False)


@pytest.mark.parametrize(
    ("script", "args", "env"),
    [
        ("p05_index.py", ["-b", "nope"], {}),
        ("p05_index.py", [], {"RAG_DENSE_BACKEND": "nope"}),  # envvar wiring
        ("p08_rerank.py", ["-b", "nope"], {}),
    ],
)
def test_cli_unknown_backend_exit2_clean_stdout(script: str, args: list[str], env: dict[str, str]) -> None:
    proc = _run(script, args, env)
    assert proc.returncode == 2
    assert proc.stdout == b""
    assert b"Known:" in proc.stderr


def test_p05_exposes_plugin_flags_in_help() -> None:
    proc = _run("p05_index.py", ["--help"])
    assert proc.returncode == 0
    text = proc.stdout.decode()
    for flag in ("--dense-backend", "--dense-model", "--sparse-model"):
        assert flag in text
    usage = p05_index.Usage()
    for flag in ("--dense-backend / -b", "--dense-model / -m", "--sparse-model / -s"):
        assert flag in usage


# --- D-E1: bounded encode batches (a 184-chunk real document exhausted 15.6 GiB inside SPLADE) --------
class _Recorder:
    """Embedder stand-in recording the length of every list it receives."""

    def __init__(self) -> None:
        self.sizes: list[int] = []

    def dense(self, texts, query):
        self.sizes.append(len(texts))
        return [[float(len(t))] for t in texts]

    def sparse(self, texts):
        self.sizes.append(len(texts))
        return [([i], [float(len(t))]) for i, t in enumerate(texts)]


@pytest.mark.parametrize("n", [0, 1, 16, 17, 184])
def test_dense_encode_is_batched(monkeypatch: pytest.MonkeyPatch, n: int, capsys: pytest.CaptureFixture[str]) -> None:
    rec = _Recorder()
    monkeypatch.setitem(he.DENSE_BACKENDS, "rec", lambda _m: (rec.dense, 1))
    texts = [f"t{i}" for i in range(n)]
    out = he.embed_dense_batch(texts, "rec", f"model-dense-{n}", batch_size=16)
    assert out == [[float(len(t))] for t in texts]  # order and total preserved
    assert sum(rec.sizes) == n and all(s <= 16 for s in rec.sizes)
    err = capsys.readouterr().err
    if n > 16:
        assert f"embedding dense {n}/{n}\n" in err and ("embedding dense 32/" in err) == (n >= 32)
        assert err.count("embedding dense") == len(rec.sizes)  # one line per batch
    else:
        assert err == ""  # a single batch stays silent


@pytest.mark.parametrize("n", [1, 17, 184])
def test_sparse_encode_is_batched(monkeypatch: pytest.MonkeyPatch, n: int, capsys: pytest.CaptureFixture[str]) -> None:
    rec = _Recorder()
    monkeypatch.setitem(he.SPARSE_BACKENDS, "fastembed", lambda _m: rec.sparse)
    texts = [f"t{i}" for i in range(n)]
    out = he.embed_sparse_batch(texts, f"model-sparse-{n}", batch_size=16)
    assert len(out) == n and sum(rec.sizes) == n and all(s <= 16 for s in rec.sizes)
    assert capsys.readouterr().err.count("embedding sparse") == (len(rec.sizes) if n > 16 else 0)


def test_embed_batch_size_default_and_wiring() -> None:
    import typer.main

    assert he.DEFAULT_EMBED_BATCH_SIZE == 16
    params = {p.name: p for p in typer.main.get_command(p05_index.app).params}
    assert params["embed_batch_size"].envvar == "RAG_EMBED_BATCH_SIZE"
    assert params["embed_batch_size"].default == he.DEFAULT_EMBED_BATCH_SIZE
    assert "--embed-batch-size / -e" in p05_index.Usage()
