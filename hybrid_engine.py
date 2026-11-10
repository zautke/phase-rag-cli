#!/usr/bin/env python3
# hybrid_engine.py
"""Hybrid retrieval engine. Dense embedder, sparse embedder and reranker are plugins:
each seam is a module-level dict name -> loader (DENSE_BACKENDS, SPARSE_BACKENDS, RERANK_BACKENDS)."""
from __future__ import annotations

import functools
import json
import math
import sys
import uuid
from collections.abc import Callable
from typing import Any

import numpy as np
from fastembed import SparseTextEmbedding, TextEmbedding
from huggingface_hub import constants
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from model_fetch import ensure_model

# Defaults mirrored in .env.example (RAG_DENSE_BACKEND / RAG_DENSE_MODEL / RAG_SPARSE_MODEL).
DEFAULT_DENSE_BACKEND = "sentence_transformers"
DEFAULT_DENSE_MODEL = "jinaai/jina-embeddings-v3"
DEFAULT_SPARSE_MODEL = "prithivida/Splade_PP_en_v1"
DEFAULT_QDRANT_PATH = "./qdrant_storage"  # mirrored in .env.example (QDRANT_PATH)
# Texts per encode call, mirrored in .env.example (RAG_EMBED_BATCH_SIZE); SPLADE logits are
# batch x tokens x 30522 floats, so one unbatched call over a real document exhausts RAM (D-E1).
DEFAULT_EMBED_BATCH_SIZE = 16
DENSE_VECTOR_NAME = "jina-dense"
SPARSE_VECTOR_NAME = "splade-sparse"

DEFAULT_RERANK_BACKEND = "sentence_transformers"
DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_FASTEMBED_RERANK_MODEL = "jinaai/jina-reranker-v2-base-multilingual"

FASTEMBED_BASE_FILES = (
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "preprocessor_config.json",
)
ST_EXCLUDE = ("onnx/*", "openvino/*", "assets/*", "*.onnx", "*.onnx_data")


def resolve_backend(registry: dict[str, Any], name: str, kind: str) -> Any:
    """Look up a plugin by name; unknown name -> ValueError listing the known ones."""
    try:
        return registry[name]
    except KeyError:
        raise ValueError(f"Unknown {kind} backend '{name}'. Known: {', '.join(sorted(registry))}") from None


def prefetch_st(model_name: str) -> None:
    """aria2c-fetch a sentence-transformers repo plus any remote-code repo its config.json names."""
    snap = ensure_model(model_name, exclude=ST_EXCLUDE)
    config = snap / "config.json"
    auto_map = json.loads(config.read_text(encoding="utf-8")).get("auto_map", {}) if config.is_file() else {}
    for ref in {v for v in auto_map.values() if isinstance(v, str) and "--" in v}:
        ensure_model(ref.split("--")[0], include=("*.py", "*.json"))


def prefetch_fastembed(model_cls: Any, model_name: str) -> None:
    """aria2c-fetch a fastembed model's files into the HF cache root before it loads."""
    desc = next(
        (d for d in model_cls.list_supported_models() if d["model"].lower() == model_name.lower()), None
    )
    hf = (desc or {}).get("sources", {}).get("hf")
    if desc and hf:
        files = (*FASTEMBED_BASE_FILES, desc["model_file"], *desc.get("additional_files", []))
        ensure_model(hf, include=files)


# --- DENSE plugins: loader(model_name) -> (embed(texts, query) -> vectors, vector size) ------------
def _dense_sentence_transformers(model_name: str) -> tuple[Callable[[list[str], bool], list[list[float]]], int]:
    from sentence_transformers import SentenceTransformer
    from transformers import PreTrainedModel

    if not hasattr(PreTrainedModel, "all_tied_weights_keys"):
        PreTrainedModel.all_tied_weights_keys = {}  # type: ignore[attr-defined]
    prefetch_st(model_name)
    st = SentenceTransformer(model_name, trust_remote_code=True)

    def embed(texts: list[str], query: bool) -> list[list[float]]:
        return st.encode(texts, show_progress_bar=False, normalize_embeddings=True).tolist()

    return embed, int(st.get_embedding_dimension())


def _dense_fastembed(model_name: str) -> tuple[Callable[[list[str], bool], list[list[float]]], int]:
    prefetch_fastembed(TextEmbedding, model_name)
    fe = TextEmbedding(model_name=model_name, cache_dir=constants.HF_HUB_CACHE)

    def embed(texts: list[str], query: bool) -> list[list[float]]:
        # query_embed / passage_embed select the task for multitask models (jina-embeddings-v3)
        vecs = fe.query_embed(texts) if query else fe.passage_embed(texts)
        return [[float(x) for x in v.tolist()] for v in vecs]

    return embed, int(fe.embedding_size)


DENSE_BACKENDS: dict[str, Callable[[str], Any]] = {
    "sentence_transformers": _dense_sentence_transformers,
    "fastembed": _dense_fastembed,
}


@functools.cache
def get_dense_embedder(backend: str, model_name: str) -> tuple[Callable[[list[str], bool], list[list[float]]], int]:
    """Singleton per (backend, model): returns (embed(texts, query), vector size)."""
    return resolve_backend(DENSE_BACKENDS, backend, "dense")(model_name)


def _embed_in_batches(kind: str, texts: list[str], batch_size: int, embed: Callable[[list[str]], list]) -> list:
    """Run `embed` over slices of at most `batch_size` texts (bounds peak RAM for every backend,
    including third-party plugins). Emits one stderr line per slice when there is more than one."""
    size = max(1, batch_size)
    out: list = []
    for start in range(0, len(texts), size):
        out.extend(embed(texts[start : start + size]))
        if len(texts) > size:
            sys.stderr.write(f"embedding {kind} {len(out)}/{len(texts)}\n")
            sys.stderr.flush()
    return out


def embed_dense_batch(
    texts: list[str], backend: str, model_name: str, query: bool = False, batch_size: int = DEFAULT_EMBED_BATCH_SIZE
) -> list[list[float]]:
    if not texts:
        return []
    embed = get_dense_embedder(backend, model_name)[0]
    return _embed_in_batches("dense", texts, batch_size, lambda chunk: embed(chunk, query))


# --- SPARSE plugins: loader(model_name) -> embed(texts) -> [(indices, values)] -------------------
def _sparse_fastembed(model_name: str) -> Callable[[list[str]], list[tuple[list[int], list[float]]]]:
    prefetch_fastembed(SparseTextEmbedding, model_name)
    fe = SparseTextEmbedding(model_name=model_name, cache_dir=constants.HF_HUB_CACHE)
    return lambda texts: [(sp.indices.tolist(), sp.values.tolist()) for sp in fe.embed(texts)]


SPARSE_BACKENDS: dict[str, Callable[[str], Any]] = {"fastembed": _sparse_fastembed}


@functools.cache
def get_sparse_embedder(model_name: str) -> Callable[[list[str]], list[tuple[list[int], list[float]]]]:
    """Singleton per model."""
    return resolve_backend(SPARSE_BACKENDS, "fastembed", "sparse")(model_name)


def embed_sparse_batch(
    texts: list[str], model_name: str, batch_size: int = DEFAULT_EMBED_BATCH_SIZE
) -> list[tuple[list[int], list[float]]]:
    if not texts:
        return []
    return _embed_in_batches("sparse", texts, batch_size, get_sparse_embedder(model_name))


def get_qdrant_client(qdrant_url: str | None, qdrant_path: str) -> QdrantClient:
    """
    Connects to a remote Qdrant server if --qdrant-url is set and reachable,
    else falls back to local disk persistence at qdrant_path (announced on stderr).
    """
    if qdrant_url:
        try:
            remote_client = QdrantClient(url=qdrant_url, timeout=2, check_compatibility=False)
            remote_client.get_collections()
            return remote_client
        except (ResponseHandlingException, UnexpectedResponse, OSError) as exc:
            sys.stderr.write(
                f"qdrant: {qdrant_url} unreachable ({type(exc).__name__}); "
                f"using embedded store at {qdrant_path}\n"
            )
    return QdrantClient(path=qdrant_path)


def ensure_hybrid_collection(
    client: QdrantClient, collection_name: str, dense_dim: int, recreate: bool = False
) -> None:
    exists = client.collection_exists(collection_name=collection_name)
    if exists and recreate:
        client.delete_collection(collection_name=collection_name)
        exists = False

    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(
                    size=dense_dim,
                    distance=models.Distance.COSINE,
                    on_disk=False,
                    quantization_config=models.ScalarQuantization(
                        scalar=models.ScalarQuantizationConfig(
                            type=models.ScalarType.INT8,
                            quantile=0.99,
                            always_ram=True,
                        )
                    ),
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=False)
                )
            },
        )


def deterministic_point_uuid(chunk_id: str) -> str:
    """Generates a deterministic UUIDv5 from chunk_id for idempotent Qdrant upserts."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, x))))


def resolve_rerank_model(model_name: str, backend: str) -> str:
    """fastembed cannot serve the default torch model; swap in its ONNX default."""
    if backend == "fastembed" and model_name == DEFAULT_RERANK_MODEL:
        return DEFAULT_FASTEMBED_RERANK_MODEL
    return model_name


# --- RERANK plugins: scorer(query, passages, model_name, batch_size) -> scores in [0, 1] ---------
@functools.cache
def _fastembed_cross_encoder(model_name: str) -> Any:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    prefetch_fastembed(TextCrossEncoder, model_name)
    return TextCrossEncoder(model_name=model_name, cache_dir=constants.HF_HUB_CACHE)


@functools.cache
def _st_cross_encoder(model_name: str) -> Any:
    from sentence_transformers import CrossEncoder

    prefetch_st(model_name)
    return CrossEncoder(model_name, trust_remote_code=True, max_length=1024)


def _rerank_fastembed(query: str, passages: list[str], model_name: str, batch_size: int) -> list[float]:
    # fastembed returns raw logits: always sigmoid, so calibration is monotonic
    raw = _fastembed_cross_encoder(model_name).rerank(query, passages, batch_size=batch_size)
    return [round(_sigmoid(float(s)), 4) for s in raw]


def _rerank_sentence_transformers(query: str, passages: list[str], model_name: str, batch_size: int) -> list[float]:
    # sentence-transformers >= 6.2 applies the model's own Sigmoid for num_labels=1; clip guards
    # models whose head has no sigmoid so the [0, 1] contract holds for every backend
    preds = _st_cross_encoder(model_name).predict(
        [[query, p] for p in passages],
        batch_size=batch_size,
        apply_softmax=False,
        show_progress_bar=False,
    )
    return [round(float(s), 4) for s in np.clip(np.asarray(preds, dtype=float), 0.0, 1.0)]


RERANK_BACKENDS: dict[str, Callable[..., list[float]]] = {
    "sentence_transformers": _rerank_sentence_transformers,
    "fastembed": _rerank_fastembed,
}


def rerank_passages_batch(
    query: str,
    passages: list[str],
    model_name: str = DEFAULT_RERANK_MODEL,
    backend: str = DEFAULT_RERANK_BACKEND,
    batch_size: int = 16,
) -> list[float]:
    """Calibrated [0.0, 1.0] cross-encoder relevance scores for (query, passage) pairs."""
    scorer = resolve_backend(RERANK_BACKENDS, backend, "rerank")
    if not passages:
        return []
    return scorer(query, passages, resolve_rerank_model(model_name, backend), batch_size)
