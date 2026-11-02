#!/usr/bin/env python3
# hybrid_engine.py
from __future__ import annotations

import contextlib
import math
import uuid
from typing import Any, Literal

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

DENSE_MODEL_NAME = "jinaai/jina-embeddings-v3"
SPARSE_MODEL_NAME = "prithivida/Splade_PP_en_v1"
DENSE_VECTOR_NAME = "jina-dense"
SPARSE_VECTOR_NAME = "splade-sparse"
DENSE_DIM = 1024  # Jina v3 default output dimension (supports MRL truncation)

RerankBackend = Literal["transformers", "fastembed"]
DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_FASTEMBED_RERANK_MODEL = "jinaai/jina-reranker-v2-base-multilingual"

_dense_model: Any = None
_dense_backend: Literal["sentence_transformers", "fastembed"] | None = None
_sparse_model: SparseTextEmbedding | None = None
_fe_reranker: Any = None
_st_reranker: Any = None
_loaded_rerank_key: str | None = None


def get_dense_embedder() -> tuple[Any, Literal["sentence_transformers", "fastembed"]]:
    """
    Singleton loader for jinaai/jina-embeddings-v3 (1024-d dense vectors).
    Uses SentenceTransformer when DENSE_MODEL_NAME == 'jinaai/jina-embeddings-v3'
    (leverages existing local HuggingFace cache without redownloading 2.3GB ONNX),
    or tries FastEmbed TextEmbedding first and falls back to SentenceTransformer.
    """
    global _dense_model, _dense_backend
    if _dense_model is not None and _dense_backend is not None:
        return _dense_model, _dense_backend

    if DENSE_MODEL_NAME == "jinaai/jina-embeddings-v3":
        from sentence_transformers import SentenceTransformer
        from transformers import PreTrainedModel

        if not hasattr(PreTrainedModel, "all_tied_weights_keys"):
            PreTrainedModel.all_tied_weights_keys = {}  # type: ignore[attr-defined]
        _dense_model = SentenceTransformer(DENSE_MODEL_NAME, trust_remote_code=True)
        _dense_backend = "sentence_transformers"
        return _dense_model, _dense_backend

    try:
        _dense_model = TextEmbedding(model_name=DENSE_MODEL_NAME)
        _dense_backend = "fastembed"
    except (ValueError, RuntimeError):
        from sentence_transformers import SentenceTransformer
        from transformers import PreTrainedModel

        if not hasattr(PreTrainedModel, "all_tied_weights_keys"):
            PreTrainedModel.all_tied_weights_keys = {}  # type: ignore[attr-defined]
        _dense_model = SentenceTransformer(DENSE_MODEL_NAME, trust_remote_code=True)
        _dense_backend = "sentence_transformers"

    return _dense_model, _dense_backend


def get_sparse_embedder() -> SparseTextEmbedding:
    global _sparse_model
    if _sparse_model is None:
        _sparse_model = SparseTextEmbedding(model_name=SPARSE_MODEL_NAME)
    return _sparse_model


def embed_dense_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    embedder, backend = get_dense_embedder()
    if backend == "sentence_transformers":
        vecs = embedder.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        return [[float(x) for x in row[:DENSE_DIM]] for row in vecs.tolist()]
    return [[float(x) for x in vec.tolist()[:DENSE_DIM]] for vec in embedder.embed(texts)]


def embed_sparse_batch(texts: list[str]) -> list[tuple[list[int], list[float]]]:
    if not texts:
        return []
    embedder = get_sparse_embedder()
    return [(sp.indices.tolist(), sp.values.tolist()) for sp in embedder.embed(texts)]


def get_qdrant_client(qdrant_url: str | None, qdrant_path: str) -> QdrantClient:
    """
    Connects to a remote Qdrant server if --qdrant-url is set and reachable,
    else falls back to local disk persistence at qdrant_path.
    """
    if qdrant_url:
        with contextlib.suppress(ResponseHandlingException, UnexpectedResponse, OSError):
            remote_client = QdrantClient(url=qdrant_url, timeout=2)
            remote_client.get_collections()
            return remote_client
    return QdrantClient(path=qdrant_path)


def ensure_hybrid_collection(
    client: QdrantClient, collection_name: str, recreate: bool = False
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
                    size=DENSE_DIM,
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


def rerank_passages_batch(
    query: str,
    passages: list[str],
    model_name: str = DEFAULT_RERANK_MODEL,
    backend: RerankBackend = "transformers",
    batch_size: int = 16,
) -> list[float]:
    """
    Computes calibrated [0.0, 1.0] cross-encoder relevance scores for (query, passage) pairs.
    Supports HuggingFace/SentenceTransformers (BAAI/bge-reranker-v2-m3, jinaai/jina-reranker-v3)
    and FastEmbed ONNX (jinaai/jina-reranker-v2-base-multilingual, BAAI/bge-reranker-base).
    """
    if not passages:
        return []

    global _fe_reranker, _st_reranker, _loaded_rerank_key
    cache_key = f"{backend}:{model_name}"

    if backend == "fastembed":
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        if _fe_reranker is None or _loaded_rerank_key != cache_key:
            _fe_reranker = TextCrossEncoder(model_name=model_name)
            _loaded_rerank_key = cache_key

        raw_scores = list(_fe_reranker.rerank(query, passages, batch_size=batch_size))
        return [
            round(_sigmoid(float(s)) if (s < 0.0 or s > 1.0) else float(s), 4)
            for s in raw_scores
        ]

    # Default: HuggingFace / SentenceTransformers CrossEncoder (FP16/BF16 on CUDA/MPS, FP32 on CPU)
    from sentence_transformers import CrossEncoder

    if _st_reranker is None or _loaded_rerank_key != cache_key:
        _st_reranker = CrossEncoder(
            model_name,
            trust_remote_code=True,
            max_length=1024,
        )
        _loaded_rerank_key = cache_key

    pairs = [[query, passage] for passage in passages]
    preds = _st_reranker.predict(
        pairs,
        batch_size=batch_size,
        apply_softmax=False,
        show_progress_bar=False,
    )
    return [
        round(_sigmoid(float(s)) if (s < 0.0 or s > 1.0) else float(s), 4)
        for s in preds
    ]
