# SOTA Hybrid RAG CLI Pipeline (`sota-hybrid-rag-cli`)

Decoupled 10-Phase SOTA Hybrid RAG CLI Pipeline with Pydantic v2 Tri-Plex I/O, Qdrant RRF (`jina-embeddings-v3` + `SPLADE`), Cross-Encoder Reranking, and Autonomous CRAG Loopback (`p00_crag_orchestrator.py`).

## Architecture & Tri-Plex I/O Engine

Every CLI phase (`rag-p01` through `rag-p10`, plus `rag-p00`) enforces strict Pydantic v2 (`ConfigDict(strict=True, extra="forbid")`) contracts at every boundary and uses a **Tri-Plex I/O Engine**:

1. **Console Telemetry (`stderr`):** Rich-formatted inspection panels and tables are written exclusively to `sys.stderr`.
2. **Artifact Persistence (`artifacts/`):** Validated JSON payloads are deterministically written to `--out-file` (`-o`).
3. **Downstream Pipe (`stdout`):** Pure, validated JSON is emitted to `sys.stdout` for zero-copy piping into the next phase.

## CLI Entrypoints

| Command | Module | Input Contract | Output Contract |
|---|---|---|---|
| `rag-p01` | `p01_load.py` | Filesystem (`--source-dir`, `-s`) | `Phase01LoadedOutput` |
| `rag-p02` | `p02_markdown.py` | `Phase01LoadedOutput` | `Phase02MarkdownOutput` |
| `rag-p03` | `p03_parse.py` | `Phase02MarkdownOutput` | `Phase03ParsedOutput` |
| `rag-p04` | `p04_chunk.py` | `Phase03ParsedOutput` | `Phase04ChunkedOutput` |
| `rag-p05` | `p05_index.py` | `Phase04ChunkedOutput` | `Phase05IndexedOutput` |
| `rag-p06` | `p06_query.py` | `Phase05IndexedOutput` | `Phase06QueryPlanOutput` |
| `rag-p07` | `p07_retrieve.py` | `Phase06QueryPlanOutput` | `Phase07RetrievedOutput` |
| `rag-p08` | `p08_rerank.py` | `Phase07RetrievedOutput` | `Phase08RerankedOutput` |
| `rag-p09` | `p09_generate.py` | `Phase08RerankedOutput` | `Phase09GenerationOutput` |
| `rag-p10` | `p10_evaluate.py` | `Phase09GenerationOutput` | `Phase10EvalOutput` |
| `rag-p00` | `p00_crag_orchestrator.py` | `Phase05IndexedOutput` | `PhaseCRAGLoopOutput` |

## Quickstart

```powershell
uv sync --all-extras
uv run pytest
```
