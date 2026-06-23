# Evolution of the Pluggable SOTA RAG Architecture

This document transcribes the complete architectural evolution from rigid phase-to-phase Pydantic contracts to a **fully pluggable, capability-driven Blackboard Envelope (`PipelinePacket`)** and a **Singular Plugin Contract (`RAGPhasePlugin`)**.

---

## Phase 1: The Architectural Shift (Blackboard Envelope & Plugin Contract)

To make the pipeline phase-module agnostic—allowing you to swap a sliding chunker for a sentence chunker, or insert a GraphRAG stage without breaking adjacent code—we replaced fixed phase schemas with a universal JSONL wire envelope and a polymorphic plugin interface.

### Key Concepts
1. **Universal Wire Envelope (`PipelinePacket`):** Every JSONL record flowing across `stdin`/`stdout` or disk carries a dictionary of typed `artifacts` (keyed by `ArtifactSlot`), provenance `lineage`, and control flags.
2. **Singular Plugin Contract (`RAGPhasePlugin[T_Config]`):** Every module implements:
   - `plugin_id: str`
   - `requires: ClassVar[FrozenSet[ArtifactSlot]]`
   - `provides: ClassVar[FrozenSet[ArtifactSlot]]`
   - `async def transform(self, packet: PipelinePacket, config: T_Config) -> AsyncIterator[PipelinePacket]`
3. **Topological Validation:** Proves at startup that every plugin's requirements are satisfied by upstream providers before loading weights or data.

### Core Implementation (`rag_plugin_core.py`)
```python
from __future__ import annotations
import importlib.metadata
import time
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import (
    Any,
    AsyncIterator,
    ClassVar,
    Dict,
    FrozenSet,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
)
from pydantic import BaseModel, ConfigDict, Field
from jsonl_stream import StreamEnvelope, AsyncJSONLReader, AsyncJSONLWriter, err_console

class ArtifactSlot(StrEnum):
    RAW_PAYLOAD       = "raw_payload"
    CLEAN_MARKDOWN    = "clean_markdown"
    AST_SECTION       = "ast_section"
    CHUNK_NODE        = "chunk_node"
    DENSE_VECTOR      = "dense_vector"
    SPARSE_VECTOR     = "sparse_vector"
    INDEX_RECEIPT     = "index_receipt"
    QUERY_PLAN        = "query_plan"
    RETRIEVED_HITS    = "retrieved_hits"
    RERANKED_CONTEXT  = "reranked_context"
    GENERATION_RESULT = "generation_result"
    EVAL_METRICS      = "eval_metrics"

class RawPayloadSlot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    source_uri: str
    mime_type: str
    content: str

class CleanMarkdownSlot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    markdown: str
    frontmatter: Dict[str, Any] = {}

class ASTSectionSlot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    section_id: str
    header_path: List[str]
    body: str
    parent_markdown: str

class ChunkNodeSlot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    chunk_id: str
    text: str
    contextualized_text: str
    token_count: int
    header_path: List[str]
    parent_markdown: str

class DenseVectorSlot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    model_name: str
    vector: List[float]

class SparseVectorSlot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    model_name: str
    indices: List[int]
    values: List[float]

class IndexReceiptSlot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    collection: str
    point_uuid: str

class QueryPlanSlot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    query: str
    sub_queries: List[str]
    hyde_passage: str
    collection: str

class RetrievedHitsSlot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    candidates: List[Dict[str, Any]]

class RerankedContextSlot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    max_score: float
    xml_context_block: str
    top_items: List[Dict[str, Any]]

class GenerationResultSlot(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    crag_verdict: str
    confidence: float
    answer: str
    citations: List[str]

SLOT_SCHEMA_MAP = {
    ArtifactSlot.RAW_PAYLOAD: RawPayloadSlot,
    ArtifactSlot.CLEAN_MARKDOWN: CleanMarkdownSlot,
    ArtifactSlot.AST_SECTION: ASTSectionSlot,
    ArtifactSlot.CHUNK_NODE: ChunkNodeSlot,
    ArtifactSlot.DENSE_VECTOR: DenseVectorSlot,
    ArtifactSlot.SPARSE_VECTOR: SparseVectorSlot,
    ArtifactSlot.INDEX_RECEIPT: IndexReceiptSlot,
    ArtifactSlot.QUERY_PLAN: QueryPlanSlot,
    ArtifactSlot.RETRIEVED_HITS: RetrievedHitsSlot,
    ArtifactSlot.RERANKED_CONTEXT: RerankedContextSlot,
    ArtifactSlot.GENERATION_RESULT: GenerationResultSlot,
}

class PluginTrace(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    plugin_id: str
    elapsed_ms: float
    added_slots: List[str]

class PipelinePacket(StreamEnvelope):
    packet_id: str
    run_id: str
    artifacts: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    lineage: List[PluginTrace] = Field(default_factory=list)
    ControlFlags: Dict[str, Any] = Field(default_factory=dict)

    def get_slot(self, slot: ArtifactSlot, model_cls):
        if slot.value not in self.artifacts:
            raise KeyError(f"Packet missing required slot '{slot.value}'")
        return model_cls.model_validate(self.artifacts[slot.value])

    def set_slot(self, slot: ArtifactSlot, payload: BaseModel):
        expected_cls = SLOT_SCHEMA_MAP[slot]
        validated = expected_cls.model_validate(payload.model_dump())
        self.artifacts[slot.value] = validated.model_dump()
        return self

    def fork(self, suffix: str):
        return PipelinePacket(
            packet_id=f"{self.packet_id}::{suffix}",
            run_id=self.run_id,
            artifacts={k: dict(v) for k, v in self.artifacts.items()},
            lineage=list(self.lineage),
            ControlFlags=dict(self.ControlFlags),
        )

T_Config = TypeVar("T_Config", bound=BaseModel)

class EmptyPluginConfig(BaseModel):
    model_config = ConfigDict(strict=False, extra="allow")

class RAGPhasePlugin(ABC, Generic[T_Config]):
    plugin_id: ClassVar[str]
    requires: ClassVar[FrozenSet[ArtifactSlot]] = frozenset()
    provides: ClassVar[FrozenSet[ArtifactSlot]] = frozenset()
    config_model: ClassVar[Type[BaseModel]] = EmptyPluginConfig

    @abstractmethod
    async def transform(self, packet: PipelinePacket, config: T_Config) -> AsyncIterator[PipelinePacket]:
        yield packet

    async def execute_packet(self, packet: PipelinePacket, raw_config: Dict[str, Any]) -> AsyncIterator[PipelinePacket]:
        missing = [s.value for s in self.requires if s.value not in packet.artifacts]
        if missing:
            raise RuntimeError(f"Plugin '{self.plugin_id}' requires slots {missing}")
        parsed_cfg = self.config_model.model_validate(raw_config)
        t0 = time.perf_counter_ns()
        async for out_pkt in self.transform(packet, parsed_cfg):
            unfulfilled = [s.value for s in self.provides if s.value not in out_pkt.artifacts]
            if unfulfilled:
                raise RuntimeError(f"Plugin '{self.plugin_id}' failed to provide slots {unfulfilled}")
            elapsed_ms = round((time.perf_counter_ns() - t0) / 1_000_000.0, 3)
            out_pkt.lineage.append(PluginTrace(plugin_id=self.plugin_id, elapsed_ms=elapsed_ms, added_slots=[s.value for s in self.provides]))
            yield out_pkt

class PluginRegistry:
    _plugins: Dict[str, Type[RAGPhasePlugin[Any]]] = {}

    @classmethod
    def register(cls, plugin_cls: Type[RAGPhasePlugin[Any]]):
        cls._plugins[plugin_cls.plugin_id] = plugin_cls
        return plugin_cls

    @classmethod
    def get(cls, plugin_id: str) -> RAGPhasePlugin[Any]:
        if plugin_id not in cls._plugins:
            raise KeyError(f"Unknown plugin '{plugin_id}'")
        return cls._plugins[plugin_id]()

    @classmethod
    def validate_pipeline_topology(cls, plugin_ids: List[str]):
        available_slots: set[ArtifactSlot] = set()
        for step_idx, pid in enumerate(plugin_ids, start=1):
            plugin = cls.get(pid)
            missing = plugin.requires - available_slots
            if missing:
                raise ValueError(f"Topology Error at Step #{step_idx} ('{pid}'): Requires {[m.value for m in missing]}")
            available_slots |= set(plugin.provides)
```

---

## Phase 2: Swappable Standard Library Plugins

The standard library demonstrates hot-swappable chunking and encoding plugins (`rag_plugins_stdlib.py`).

```python
from __future__ import annotations
import hashlib, math, re
from typing import AsyncIterator
from pydantic import BaseModel
from rag_plugin_core import (
    ArtifactSlot, ASTSectionSlot, ChunkNodeSlot, CleanMarkdownSlot,
    DenseVectorSlot, EmptyPluginConfig, PipelinePacket, PluginRegistry,
    RAGPhasePlugin, RawPayloadSlot, SparseVectorSlot
)

@PluginRegistry.register
class BuiltinCorpusLoaderPlugin(RAGPhasePlugin[EmptyPluginConfig]):
    plugin_id = "loader.builtin_corpus"
    requires = frozenset()
    provides = frozenset({ArtifactSlot.RAW_PAYLOAD})

    async def transform(self, packet: PipelinePacket, config: EmptyPluginConfig) -> AsyncIterator[PipelinePacket]:
        samples = [("doc_01", "text/html", "<h1>Hybrid RAG</h1><p>Qdrant fuses Jina-v3 with SPLADE.</p>")]
        for doc_id, mime, text in samples:
            child = packet.fork(doc_id)
            child.set_slot(ArtifactSlot.RAW_PAYLOAD, RawPayloadSlot(source_uri=f"mem://{doc_id}", mime_type=mime, content=text))
            yield child

@PluginRegistry.register
class HtmlToMarkdownPlugin(RAGPhasePlugin[EmptyPluginConfig]):
    plugin_id = "preprocess.html_to_md"
    requires = frozenset({ArtifactSlot.RAW_PAYLOAD})
    provides = frozenset({ArtifactSlot.CLEAN_MARKDOWN})

    async def transform(self, packet: PipelinePacket, config: EmptyPluginConfig) -> AsyncIterator[PipelinePacket]:
        raw = packet.get_slot(ArtifactSlot.RAW_PAYLOAD, RawPayloadSlot)
        md = re.sub(r"<h1>(.*?)</h1>", r"# \1\n\n", raw.content, flags=re.I)
        md = re.sub(r"<p>(.*?)</p>", r"\1\n\n", md, flags=re.I).strip()
        packet.set_slot(ArtifactSlot.CLEAN_MARKDOWN, CleanMarkdownSlot(markdown=md))
        yield packet

class SlidingChunkConfig(BaseModel):
    max_words: int = 8
    overlap: int = 2

@PluginRegistry.register
class SlidingWindowChunkerPlugin(RAGPhasePlugin[SlidingChunkConfig]):
    plugin_id = "chunker.sliding_window"
    requires = frozenset({ArtifactSlot.AST_SECTION})
    provides = frozenset({ArtifactSlot.CHUNK_NODE})
    config_model = SlidingChunkConfig

    async def transform(self, packet: PipelinePacket, config: SlidingChunkConfig) -> AsyncIterator[PipelinePacket]:
        sec = packet.get_slot(ArtifactSlot.AST_SECTION, ASTSectionSlot)
        words = sec.body.split()
        step = max(1, config.max_words - config.overlap)
        for idx, start in enumerate(range(0, len(words), step)):
            slice_w = words[start : start + config.max_words]
            if not slice_w: continue
            text = " ".join(slice_w)
            child = packet.fork(f"chk_{idx}")
            child.set_slot(ArtifactSlot.CHUNK_NODE, ChunkNodeSlot(
                chunk_id=child.packet_id, text=text,
                contextualized_text=f"[{' > '.join(sec.header_path)}] {text}",
                token_count=len(slice_w), header_path=sec.header_path, parent_markdown=sec.parent_markdown
            ))
            yield child
```

---

## Phase 3: SOTA Neural Plugins (Qdrant, Jina-v3, SPLADE, Cross-Encoder, Claude XML)

Porting the heavy neural infrastructure into native `RAGPhasePlugin` classes (`rag_plugins_sota.py`).

```python
from __future__ import annotations
import os
from typing import AsyncIterator
from pydantic import BaseModel, Field
from qdrant_client import models
from rag_plugin_core import (
    ArtifactSlot, ChunkNodeSlot, DenseVectorSlot, GenerationResultSlot,
    IndexReceiptSlot, PipelinePacket, PluginRegistry, QueryPlanSlot,
    RAGPhasePlugin, RerankedContextSlot, RetrievedHitsSlot, SparseVectorSlot
)
from hybrid_engine import (
    DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, DEFAULT_RERANK_MODEL,
    embed_dense_batch, embed_sparse_batch, get_qdrant_client,
    ensure_hybrid_collection, deterministic_point_uuid, rerank_passages_batch
)

class QdrantIndexConfig(BaseModel):
    collection_name: str = "sota_hybrid_rag_v1"
    qdrant_path: str = "./qdrant_storage"
    qdrant_url: Optional[str] = Field(default_factory=lambda: os.getenv("QDRANT_URL"))
    recreate: bool = True

@PluginRegistry.register
class QdrantHybridIndexerPlugin(RAGPhasePlugin[QdrantIndexConfig]):
    plugin_id = "indexer.qdrant_hybrid"
    requires = frozenset({ArtifactSlot.CHUNK_NODE})
    provides = frozenset({ArtifactSlot.DENSE_VECTOR, ArtifactSlot.SPARSE_VECTOR, ArtifactSlot.INDEX_RECEIPT})
    config_model = QdrantIndexConfig

    async def transform(self, packet: PipelinePacket, config: QdrantIndexConfig) -> AsyncIterator[PipelinePacket]:
        chk = packet.get_slot(ArtifactSlot.CHUNK_NODE, ChunkNodeSlot)
        d_vec = embed_dense_batch([chk.contextualized_text])[0]
        s_idx, s_val = embed_sparse_batch([chk.contextualized_text])[0]

        client = get_qdrant_client(config.qdrant_url, config.qdrant_path)
        ensure_hybrid_collection(client, config.collection_name, recreate=config.recreate)
        point_id = deterministic_point_uuid(chk.chunk_id)
        client.upsert(
            collection_name=config.collection_name,
            points=[models.PointStruct(
                id=point_id,
                vector={DENSE_VECTOR_NAME: d_vec, SPARSE_VECTOR_NAME: models.SparseVector(indices=s_idx, values=s_val)},
                payload={"chunk_id": chk.chunk_id, "contextualized_text": chk.contextualized_text, "parent_markdown": chk.parent_markdown}
            )],
            wait=True
        )
        client.close()
        packet.set_slot(ArtifactSlot.DENSE_VECTOR, DenseVectorSlot(model_name="jinaai/jina-embeddings-v3", vector=d_vec))
        packet.set_slot(ArtifactSlot.SPARSE_VECTOR, SparseVectorSlot(model_name="prithivida/Splade_PP_en_v1", indices=s_idx, values=s_val))
        packet.set_slot(ArtifactSlot.INDEX_RECEIPT, IndexReceiptSlot(collection=config.collection_name, point_uuid=point_id))
        yield packet

class RRFRetrieveConfig(BaseModel):
    collection_name: str = "sota_hybrid_rag_v1"
    qdrant_path: str = "./qdrant_storage"
    qdrant_url: Optional[str] = Field(default_factory=lambda: os.getenv("QDRANT_URL"))
    prefetch_limit: int = 25
    rrf_k: int = 60
    top_k: int = 10

@PluginRegistry.register
class QdrantRRFRetrieverPlugin(RAGPhasePlugin[RRFRetrieveConfig]):
    plugin_id = "retriever.qdrant_rrf"
    requires = frozenset({ArtifactSlot.QUERY_PLAN})
    provides = frozenset({ArtifactSlot.RETRIEVED_HITS})
    config_model = RRFRetrieveConfig

    async def transform(self, packet: PipelinePacket, config: RRFRetrieveConfig) -> AsyncIterator[PipelinePacket]:
        qplan = packet.get_slot(ArtifactSlot.QUERY_PLAN, QueryPlanSlot)
        q_dense = embed_dense_batch([f"{qplan.query}\n{qplan.hyde_passage}"])
        q_s_idx, q_s_val = embed_sparse_batch([qplan.query])[0]
        q_sparse_vec = models.SparseVector(indices=q_s_idx, values=q_s_val)

        client = get_qdrant_client(config.qdrant_url, config.qdrant_path)
        fused_response = client.query_points(
            collection_name=config.collection_name,
            prefetch=[
                models.Prefetch(query=q_dense[0], using=DENSE_VECTOR_NAME, limit=config.prefetch_limit),
                models.Prefetch(query=q_sparse_vec, using=SPARSE_VECTOR_NAME, limit=config.prefetch_limit),
            ],
            query=models.RrfQuery(rrf=models.Rrf(k=config.rrf_k)),
            limit=config.top_k,
            with_payload=True,
        )
        client.close()

        candidates = [{
            "chunk_id": pt.payload.get("chunk_id", str(pt.id)),
            "contextualized_text": pt.payload.get("contextualized_text", ""),
            "parent_markdown": pt.payload.get("parent_markdown", ""),
            "rrf_fused_score": float(pt.score),
        } for pt in fused_response.points]

        packet.set_slot(ArtifactSlot.RETRIEVED_HITS, RetrievedHitsSlot(candidates=candidates))
        yield packet
```