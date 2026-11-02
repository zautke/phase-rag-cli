# INSTRUCTIONAL INSIGHTS

## Reusable Patterns & Engineering Lessons

### 1. FastEmbed vs. SentenceTransformers Dual Backend Strategy
- **Context:** `jinaai/jina-embeddings-v3` has a 2.3GB ONNX distribution in FastEmbed, but users often have existing PyTorch weights in their local HuggingFace cache (`HF_HOME`).
- **Insight:** `hybrid_engine.py` implements a dual loader: if the local model weights are present, it loads via `SentenceTransformer` (with `trust_remote_code=True`), falling back to FastEmbed `TextEmbedding`.
- **Transformers Attribute Guard:** When loading newer models via `trust_remote_code=True`, monkey-patching `PreTrainedModel.all_tied_weights_keys = {}` prevents attribute errors across differing library versions.

### 2. Windows PowerShell Subprocess Pipeline Encoding
- **Issue:** Windows PowerShell (`powershell.exe`) defaults to UTF-16 or OEM code pages for stdout redirection, corrupting JSON pipes between CLI commands.
- **Solution:** Always set UTF-8 without BOM in PowerShell scripts before piping:
  ```powershell
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [Console]::OutputEncoding = $utf8NoBom
  [Console]::InputEncoding = $utf8NoBom
  $OutputEncoding = $utf8NoBom
  ```
- In Python `subprocess.run()`, always pass `text=True, encoding="utf-8"` explicitly.

### 3. Qdrant Reciprocal Rank Fusion (RRF) with Named Vectors
- **Pattern:** Rather than manually scoring and combining dense and sparse vectors in application code, use Qdrant native `Prefetch` with `RrfQuery`:
  ```python
  client.query_points(
      collection_name=collection_name,
      prefetch=[
          models.Prefetch(query=dense_vec, using="jina-dense", limit=top_k * 2),
          models.Prefetch(query=models.SparseVector(indices=sp_indices, values=sp_values), using="splade-sparse", limit=top_k * 2),
      ],
      query=models.RrfQuery(rrf=models.Rrf(k=rrf_k)),
      limit=top_k,
  )
  ```
- This allows Qdrant's query optimizer to handle rank normalization and score distribution discrepancies natively.

### 4. CRAG Query Rewriting with Corpus Lexical Anchors
- **Pattern:** When CRAG evaluates a query below `--crag-threshold`, blindly rewriting the query via standard LLM prompts often hallucinates or remains divergent from the actual indexed corpus.
- **Solution:** In `p00_crag_orchestrator.py`, extract the highest-scoring candidate chunks from Phase 08, parse salient nouns and domain terms (anchors), and synthesize the rewritten query around those anchors. This guarantees deterministic convergence towards indexed documents within 1–2 loop iterations.
