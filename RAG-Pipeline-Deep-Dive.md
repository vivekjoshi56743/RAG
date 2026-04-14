# RAG Pipeline — Deep Technical Design (v2)

**This document is the single source of truth for all pipeline decisions.**

## Design Constraints

- **Corpus: Unknown and diverse.** Users upload anything — technical docs, textbooks, research papers, contracts, manuals, novels. The pipeline cannot assume structure, vocabulary, or domain.
- **Scale: 10K–200K+ pages.** The system must not degrade as the knowledge base grows. A 50-page upload and a 5,000-page documentation set must both work well.
- **Infrastructure: GCP (owner access)**
- **Query types: Everything.** Factual lookup ("what's the default timeout?"), conceptual ("explain how authentication works"), comparative ("how does Module A differ from Module B"), and conversational follow-ups.
- **Latency target: <2s to first streamed token**

---

## 1. Embedding Model Selection

### 1.1 What We Need From the Embedding Model

Since we don't control the corpus domain, the embedding model must be:

1. **Domain-agnostic.** Strong on technical, academic, legal, narrative, and conversational text — not tuned for one.
2. **High retrieval quality.** MTEB retrieval benchmarks are the best proxy we have. We want top-tier general retrieval, not a domain-specialist that falls apart on unfamiliar text.
3. **Long-ish context.** Our chunks will be ~512 tokens, but we prepend metadata context. 2K minimum, 8K+ preferred.
4. **Asymmetric query/document support.** The model should distinguish between "I'm encoding a document for storage" vs "I'm encoding a short question for search." This matters — queries and documents have fundamentally different distributions.
5. **Matryoshka / dimension flexibility.** At 200K+ pages (~1M chunks), storing full-width vectors gets expensive. Being able to truncate to 256-dim for initial filtering, then re-score at full width, is a real advantage.
6. **Reasonable cost.** Initial indexing of 200K pages ≈ 1M chunks ≈ ~50M tokens. At $0.13/1M that's $6.50. At $0.02/1M that's $1. Both fine, but a 6x difference compounds.
7. **API reliability.** The embedding model is on the critical path for every query. Downtime = the whole app is broken.

### 1.2 Candidates — Honest Evaluation

| Model | Dims | Max Context | MTEB Retrieval | Asymmetric | Matryoshka | Cost/1M tok | Reliability |
|-------|------|-------------|---------------|------------|------------|-------------|-------------|
| **Voyage AI voyage-3** | 1024 | 32K | **0.683** | Yes (`input_type`) | No | $0.06 | Good (smaller co.) |
| Voyage AI voyage-law-2 | 1024 | 16K | ~0.67 legal only | Yes | No | $0.12 | Good |
| **Cohere embed-v3.0** | 1024 | 512 | **0.675** | Yes (`input_type`) | Yes (down to 256) | $0.10 | **Excellent** |
| **OpenAI text-embedding-3-large** | 3072 | 8K | 0.644 | No | **Yes** (to 256) | $0.13 | **Excellent** |
| OpenAI text-embedding-3-small | 1536 | 8K | 0.622 | No | Yes (to 512) | $0.02 | Excellent |
| Vertex AI text-embedding-004 | 768 | 2048 | ~0.63 | Partial | No | $0.025 | Excellent (GCP) |
| Jina embeddings-v3 | 1024 | 8K | 0.662 | Yes (`task`) | Yes | $0.02 | Good |
| BGE-large-en-v1.5 | 1024 | 512 | 0.640 | Partial | No | Free (GPU) | Self-managed |
| Mixedbread mxbai-embed-large | 1024 | 512 | 0.651 | No | Yes | Free (GPU) | Self-managed |
| E5-mistral-7b-instruct | 4096 | 32K | 0.668 | Yes | No | Free (GPU) | Self-managed |

### 1.3 Decision: **Voyage AI voyage-3** (primary) with **Cohere embed-v3** as fallback

**Why voyage-law-2 is OUT:**
A domain-specific model is wrong when users upload anything. voyage-law-2 was fine-tuned on legal corpora. It'll underperform on Python documentation, physics textbooks, or fiction. We need the generalist.

**Why voyage-3 wins for a corpus-agnostic system:**

1. **Highest MTEB retrieval score (0.683).** On the actual task we care about — finding the right passage given a question — it's the best available API model. This isn't marginal; 0.683 vs 0.644 (OpenAI) means retrieving the correct chunk ~6% more often. Over thousands of queries, that's a meaningful UX difference.

2. **Asymmetric embedding.** Voyage supports `input_type="document"` vs `input_type="query"`. Documents and queries have fundamentally different distributions. A query is short, interrogative, and incomplete. A document chunk is long, declarative, and self-contained. Models that encode both identically leave quality on the table. In benchmarks, asymmetric embedding improves retrieval by 3–8%.

3. **32K context window.** Our chunks are ~512 tokens, but with metadata prefix they're ~600–700. 32K gives massive headroom. More importantly, it means we can experiment with larger chunks (1024, 2048 tokens) or even full-section embeddings without switching models.

4. **1024 dimensions.** The right balance:
   - 768 (Vertex): Too compressed at 1M+ chunks. Cosine similarity scores cluster, reducing discrimination.
   - 3072 (OpenAI): Overkill. 3x storage, 3x slower HNSW search, minimal quality gain.
   - 1024: Good separation, reasonable storage (~4KB per vector, ~4GB for 1M chunks).

5. **Cost.** $0.06/1M tokens. Indexing 200K pages (~50M tokens): $3. Per query (single embedding): $0.000003. Negligible.

6. **Domain-agnostic strength.** voyage-3 is trained on diverse data — technical, legal, scientific, narrative. Unlike voyage-law-2, it doesn't trade off general ability for domain specialization.

**Why Cohere is the fallback (not OpenAI):**
- Cohere has Matryoshka support (truncate to 256 dims for fast pre-filtering) which Voyage lacks.
- Cohere's `input_type` asymmetric support matches Voyage's API shape.
- If Voyage has reliability issues (they're a smaller company), Cohere is the seamless swap — same 1024 dims, same asymmetric API.
- OpenAI's model lacks asymmetric support and its MTEB retrieval score (0.644) is significantly lower.

**Why NOT self-hosted (BGE, E5-mistral, mxbai):**
- Self-hosting means provisioning GPUs on GCP, managing model serving, handling scaling. That's a whole infra project.
- The quality gap vs Voyage is real (0.640–0.668 vs 0.683).
- GPU instances cost $200+/month — far more than the $3 API cost for initial indexing.
- Only makes sense at 10M+ embeddings/month or air-gapped deployments.

### 1.4 Contextual Embedding Strategy

Don't embed raw chunk text. This is the #1 mistake in RAG systems.

**The problem:** A chunk saying "It supports both TCP and UDP protocols" is ambiguous without knowing whether it came from a Kubernetes networking guide or a router manual.

**The solution: Adaptive context prefixing.** Since we don't know the document domain, generate the prefix dynamically from whatever metadata is available:

```python
# backend/app/services/embedder.py

def build_embedding_text(chunk: dict) -> str:
    """Prepend whatever structural context we have."""
    prefix_parts = []

    if chunk.get("doc_name"):
        prefix_parts.append(f"Document: {chunk['doc_name']}")
    if chunk.get("detected_heading"):
        prefix_parts.append(f"Section: {chunk['detected_heading']}")
    if chunk.get("detected_subheading"):
        prefix_parts.append(f"Subsection: {chunk['detected_subheading']}")
    if chunk.get("doc_summary_short"):
        prefix_parts.append(f"Context: {chunk['doc_summary_short']}")

    prefix = " | ".join(prefix_parts)
    return f"[{prefix}]\n\n{chunk['text']}" if prefix else chunk["text"]


def build_query_text(query: str) -> str:
    """Instruction prefix for query-side embedding."""
    return f"Represent this question for retrieving relevant document passages: {query}"
```

**What gets embedded (examples across different corpus types):**

```
Technical docs:
[Document: kubernetes-networking.pdf | Section: Service Types | Context: Kubernetes cluster networking guide]
ClusterIP exposes the service on a cluster-internal IP...

Textbook:
[Document: intro-to-algorithms.pdf | Section: Chapter 4 — Divide and Conquer | Context: CS algorithms textbook]
The divide-and-conquer paradigm involves three steps...

Contract:
[Document: vendor-agreement-2024.pdf | Section: Payment Terms | Context: Vendor services agreement]
Payment shall be due within thirty (30) days...

Novel:
[Document: great-gatsby.pdf | Context: American literary fiction, 1920s]
In my younger and more vulnerable years my father gave me some advice...
```

### 1.5 Implementation

```python
# backend/app/services/embedder.py
import voyageai
from tenacity import retry, stop_after_attempt, wait_exponential

client = voyageai.AsyncClient()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed_documents(texts: list[str], batch_size: int = 128) -> list[list[float]]:
    """Embed document chunks in batches."""
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        result = await client.embed(batch, model="voyage-3", input_type="document", truncation=True)
        all_embeddings.extend(result.embeddings)
    return all_embeddings

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed_query(query: str) -> list[float]:
    """Embed a single search query."""
    result = await client.embed([build_query_text(query)], model="voyage-3", input_type="query", truncation=True)
    return result.embeddings[0]
```

---

## 2. Chunking Strategy

### 2.1 The Core Problem

We don't know what documents look like. A user might upload:
- A 5,000-page technical manual with deep header hierarchy
- A 300-page novel with chapters and no subheadings
- A 10-page contract with dense legal paragraphs
- A research paper with abstract, sections, figures, references
- A CSV-exported FAQ with 200 short Q&A pairs

A single chunking strategy will fail on some of these. We need an **adaptive chunker** that detects document structure and adjusts.

### 2.2 Approaches Evaluated

| Strategy | Strength | Weakness | Best For |
|----------|----------|----------|----------|
| Fixed-size | Simple, predictable | Breaks mid-sentence | Never best, never catastrophic |
| Recursive character | Respects text boundaries | No semantic awareness | Default fallback |
| **Semantic chunking** | **Topic-aligned, coherent** | **Expensive (embed per sentence)** | **Flat prose — novels, essays** |
| **Structure-aware** | **Preserves doc logic perfectly** | **Needs structure detection** | **Manuals, textbooks, specs** |
| Proposition-based | Maximum precision | Very expensive, slow | Not practical at 200K pages |

### 2.3 Our Choice: Adaptive Multi-Strategy Chunker

The chunker runs a **detection pass** first, then routes to the best strategy:

```
Document arrives
    │
    ▼
DETECTION PASS (scan first 5 pages)
  • Heading patterns? (markdown, numbered, CAPS)
  • Average paragraph length?
  • Code blocks? Tables?
    │
    ├─ Many headings ────→ STRUCTURED → Split at headers
    ├─ Some structure ───→ MIXED      → Recursive + heading awareness
    └─ No structure ─────→ FLAT       → Semantic chunking (similarity-based splits)
```

### 2.4 Structure Detection

```python
from enum import Enum

class DocumentStructure(Enum):
    STRUCTURED = "structured"   # Clear headings, hierarchy
    MIXED = "mixed"             # Some structure, some prose
    FLAT = "flat"               # No discernible structure

def detect_structure(text: str) -> tuple[DocumentStructure, dict]:
    """Analyze first ~15K chars to classify document structure."""
    sample = text[:15000]
    lines = sample.split("\n")

    md_headings = len(re.findall(r'^#{1,4}\s+\S', sample, re.MULTILINE))
    numbered = len(re.findall(r'^(?:\d+\.[\d.]*\s+[A-Z]|Section\s+\d|CHAPTER\s+\d)', sample, re.MULTILINE))
    caps_headings = len([
        l for l in lines
        if l.strip() and len(l.strip()) < 100
        and l.strip().isupper() and not l.strip().endswith(('.', ','))
    ])

    heading_density = (md_headings + numbered + caps_headings / 3) / max(len(lines), 1) * 100

    if heading_density > 3 or md_headings > 5 or numbered > 5:
        return DocumentStructure.STRUCTURED, {...}
    elif heading_density > 1 or caps_headings > 5:
        return DocumentStructure.MIXED, {...}
    else:
        return DocumentStructure.FLAT, {...}
```

### 2.5 Three Chunking Strategies

**Strategy 1: Structure-Aware** (for manuals, API docs, textbooks, specs)
- Extract headings using regex patterns (markdown, numbered, ALL CAPS, Chapter/Section)
- Split at each heading boundary
- Track heading hierarchy (H1/H2/H3) for context metadata
- If a section exceeds 512 tokens, recursive-split within it
- Each chunk inherits its parent heading chain

**Strategy 2: Recursive + Heading Awareness** (for papers, reports, contracts)
- Split at paragraph boundaries (double newline)
- Merge adjacent paragraphs up to 512 tokens
- Capture any nearby detected headings as context
- 50-token overlap between chunks

**Strategy 3: Semantic Chunking** (for novels, essays, transcripts, flat prose)
- Split into sentences
- Embed consecutive sentences (batch via Voyage)
- When cosine similarity between sentence N and N+1 drops below threshold (0.3), start a new chunk
- More expensive (requires embedding at chunk time) but produces the most coherent chunks for unstructured text
- Fallback: if too expensive or embedding fails, use recursive strategy

**Orchestrator:**
```python
async def chunk_document(pages, doc_id, doc_name, summary=""):
    full_text = "\n\n".join(page["text"] for page in pages)
    structure_type, patterns = detect_structure(full_text)

    if structure_type == DocumentStructure.STRUCTURED:
        return chunk_structured(full_text, doc_id, doc_name, pages, summary)
    elif structure_type == DocumentStructure.MIXED:
        return chunk_mixed(full_text, doc_id, doc_name, pages, summary)
    else:
        return await chunk_semantic(full_text, doc_id, doc_name, pages, summary)
```

### 2.6 Why 512 Tokens

| Chunk Size | Chunks per 10K pages | Context Usage (top-8) | Trade-off |
|-----------|---------------------|----------------------|-----------|
| 128 tokens | ~250K | ~1K tokens | Too granular, loses coherence |
| 256 tokens | ~125K | ~2K tokens | Good for Q&A, bad for explanations |
| **512 tokens** | **~60K** | **~4K tokens** | **Best general-purpose default** |
| 1024 tokens | ~30K | ~8K tokens | Better for narrative, worse for lookup |

512 is the default. Each chunk stores its `token_count`, enabling future experiments without re-architecting.

### 2.7 Chunk Enrichment: Hypothetical Question Generation

For each chunk, generate 2 questions it would answer. Embed these and store them separately. When a user asks a question, retrieval searches against both chunk content AND hypothetical questions — matching question-to-question is inherently easier than question-to-passage.

```python
async def generate_hypothetical_questions(chunk_text: str, heading: str = "", doc_name: str = "") -> list[str]:
    response = await anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"""Given this text from '{doc_name}' ({heading}):
{chunk_text[:1500]}

Write exactly 2 specific questions this text answers. One per line, no bullets."""
        }]
    )
    return [q.strip() for q in response.content[0].text.strip().split("\n") if q.strip()][:2]
```

**Cost:** ~$0.001/chunk. For 60K chunks: ~$60 one-time. Improves recall@8 by 5–10%.

---

## 3. Retrieval: 4-Stage Funnel

### Stage 1: Query Understanding (~100–500ms)

```python
async def process_query(raw_query, conversation_history):
    # Rewrite if conversation has context (resolve "it", "that", "the same one")
    if history and _has_references(raw_query):
        rewritten = await llm_rewrite(raw_query, history[-4:])
    else:
        rewritten = raw_query

    # Decompose comparison queries ("compare X vs Y" → two sub-queries)
    sub_queries = await decompose_if_needed(rewritten)

    # Embed
    embedding = await embed_query(rewritten)

    return {"rewritten": rewritten, "sub_queries": sub_queries, "embedding": embedding}
```

### Stage 2: Broad Retrieval — 3 Signals + RRF (~150ms)

Three retrieval signals run **in parallel**, then fuse with Reciprocal Rank Fusion:

| Signal | What It Catches | Index Used |
|--------|----------------|------------|
| **Dense (vector)** | Semantic similarity ("payment terms" ↔ "financial obligations") | pgvector HNSW |
| **Sparse (BM25)** | Exact terms, names, codes ("§201.56", "kubectl apply") | PostgreSQL GIN (tsvector) |
| **Question match** | Question-to-question similarity (user Q ↔ hypothetical Q) | pgvector HNSW on question_embedding |

**RRF Fusion:**
```
score(chunk) = Σ weight_i / (k + rank_i)
```
- k = 60 (from original RRF paper by Cormack et al.)
- Weights: dense 0.40, sparse 0.30, question 0.30
- Output: top 100 candidates

**Why three signals matter for diverse corpora:**
- Technical docs with code: BM25 catches exact function names that dense search fuzzes over.
- Narrative text: Dense search catches semantic meaning that BM25 misses entirely.
- Question match: Bridges the gap between how users ask and how documents state information.

### Stage 3: Cross-Encoder Re-Ranking (~300ms)

**Why this stage exists:** Embedding models (Stage 2) encode query and document independently — they're comparing two compressed representations. A cross-encoder sees the query and document together and can model token-level interactions.

```
Example:
  Query: "Can I use abbreviations on drug labels?"
  Chunk A: "Abbreviations may be used on labels only if..." (relevant)
  Chunk B: "Labels must include the abbreviation of the manufacturer..." (surface match, wrong sense)

  Bi-encoder: ranks B higher (more keyword overlap)
  Cross-encoder: ranks A higher (understands the question intent)
```

**Re-Ranker Options:**

| Model | Latency (100 docs) | Quality (NDCG@10) | Cost |
|-------|-------------------|-------------------|------|
| **Cohere Rerank 3.5** | ~300ms | **0.67** | **$0.002/search** |
| Voyage rerank-2 | ~250ms | 0.66 | $0.005/search |
| BGE-reranker-v2-m3 | ~500ms (CPU) | 0.64 | Free (GPU) |
| Jina Reranker v2 | ~350ms | 0.63 | $0.002/search |
| FlashRank | ~50ms (CPU) | 0.55 | Free (CPU) |
| **Claude LLM-as-reranker** | ~2000ms | **~0.70** | ~$0.01/search |

**Our choice: Cohere Rerank 3.5 (default) + Claude LLM (complex queries)**

- Cohere: Best quality-to-latency ratio. 300ms, 0.67 NDCG, $0.002/search. Handles 4096-token docs.
- Claude LLM: 2 seconds but highest quality (~0.70). Reserved for comparison/multi-hop queries where the extra latency is worth it.

```python
async def rerank(query, chunks, top_n=15, use_llm=False):
    if use_llm:
        return await _llm_rerank(query, chunks, top_n)

    response = await cohere_client.rerank(
        model="rerank-v3.5", query=query,
        documents=[c["content"] for c in chunks],
        top_n=top_n, return_documents=False,
    )
    return [chunks[r.index] | {"rerank_score": r.relevance_score} for r in response.results]
```

### Stage 4: User-Signal Re-Ranking (~50ms)

Covered in Section 4 below.

---

## 4. User Feedback & Learned Re-Ranking

### 4.1 Signals Collected

| Signal | Trigger | Weight | Type |
|--------|---------|--------|------|
| Thumbs up | User clicks 👍 | +3.0 | Explicit |
| Thumbs down | User clicks 👎 | -3.0 | Explicit |
| Citation click | User clicks [Source N] | +2.0 | Explicit |
| Copy text | User copies answer text | +1.0 | Explicit |
| Search result click | User clicks search result | +2.0 | Explicit |
| Search result skip | Shown but not clicked | -0.5 | Implicit |
| Query reformulation | User rephrases same question | -1.0 (prev results) | Implicit |
| Follow-up question | User asks related follow-up | +1.0 | Implicit |

### 4.2 How Preferences Are Applied

Three preference signals combined per chunk:

1. **Direct chunk preference** — Has this user engaged with this exact chunk before? (weight: 0.30)
2. **Document-level affinity** — Does this user frequently interact with this document? (weight: 0.15)
3. **Similar-query collaborative** — For queries similar to this one (cosine > 0.75 on query embeddings), what chunks did this user prefer? (weight: 0.30)
4. **Re-ranker base score** — Preserved from Stage 3. (weight: 0.25)

```python
async def apply_user_signals(user_id, query_embedding, chunks, top_n=8):
    # Cold start: skip for users with < 10 feedback signals
    if await feedback_count(user_id) < 10:
        return chunks[:top_n]

    # Fetch preferences from materialized views (fast, precomputed)
    chunk_prefs, doc_prefs, similar_prefs = await asyncio.gather(
        get_chunk_preferences(user_id, [c["id"] for c in chunks]),
        get_doc_preferences(user_id, [c["document_id"] for c in chunks]),
        get_similar_query_preferences(user_id, query_embedding, [c["id"] for c in chunks]),
    )

    for chunk in chunks:
        chunk["final_score"] = (
            0.25 * chunk.get("rerank_score", 0.5) +
            0.30 * sigmoid(chunk_prefs.get(chunk["id"], 0)) +
            0.15 * sigmoid(doc_prefs.get(chunk["document_id"], 0)) +
            0.30 * sigmoid(similar_prefs.get(chunk["id"], 0))
        )

    return sorted(chunks, key=lambda c: c["final_score"], reverse=True)[:top_n]
```

### 4.3 Storage

```sql
-- Raw signals
CREATE TABLE user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    query_text TEXT NOT NULL,
    query_embedding vector(1024),
    chunk_id UUID REFERENCES chunks(id),
    document_id UUID,
    signal_type TEXT NOT NULL,
    signal_weight FLOAT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Precomputed (refreshed every 15 min via Cloud Run Job)
CREATE MATERIALIZED VIEW user_chunk_prefs AS
SELECT user_id, chunk_id, document_id, SUM(signal_weight) AS score
FROM user_feedback WHERE created_at > now() - INTERVAL '90 days'
GROUP BY user_id, chunk_id, document_id;

CREATE MATERIALIZED VIEW user_doc_prefs AS
SELECT user_id, document_id, SUM(score) AS doc_score
FROM user_chunk_prefs GROUP BY user_id, document_id;
```

---

## 5. Full Pipeline: End-to-End

```
User Query: "How does the authentication middleware work?"
    │
    ▼
STAGE 1: QUERY UNDERSTANDING
  Rewrite: (self-contained, no change)
  Sub-queries: ["authentication middleware"]
  Embed with Voyage voyage-3 (query mode)
    │
    ▼
STAGE 2: BROAD RETRIEVAL (parallel)
  ① Dense:    auth-middleware.ts chunk (0.91), jwt-config.md (0.87), ...
  ② Sparse:   auth-middleware.ts (BM25: 14.2), session-handler (9.1), ...
  ③ Question:  "How does auth work?" matched → auth-middleware.ts (0.93)
  → RRF fusion → 100 candidates
    │
    ▼
STAGE 3: RE-RANKING (Cohere Rerank 3.5)
  Score all 100 (query, chunk) pairs → top 15
  auth-middleware.ts/chunk-3 (0.96), jwt-config/chunk-1 (0.89), ...
    │
    ▼
STAGE 4: USER SIGNAL BOOST
  This user previously clicked auth-middleware citations 3x
  Boost auth-middleware chunks slightly
  15 → final 8
    │
    ▼
CONTEXT ASSEMBLY
  Fetch ±1 neighboring chunks for each result
  Build prompt: system instructions + 8 cited sources + conversation history
    │
    ▼
LLM GENERATION (Claude Sonnet, streaming)
  "The authentication middleware [Source 1] uses JWT tokens validated
   against the config in [Source 2]..."
    │
    ▼
POST-GENERATION
  Extract [Source N] → map to chunk metadata
  Save message + citations
  Record implicit feedback (retrieval_served: +0.1)
```

---

## 6. Indexing Pipeline (Upload → Searchable)

```
File Upload (PDF / DOCX / TXT / MD)
    │
    ▼
PARSE — Parser registry routes by extension
  .pdf  → PyMuPDF (text) + Cloud Vision (scanned OCR)
  .docx → python-docx (paragraphs + tables)
  .txt  → UTF-8 decode with encoding detection
  .md   → Strip syntax, preserve structure
  Output: [{page: 1, text: "..."}, ...]
    │
    ▼
DETECT STRUCTURE — Scan first 5 pages
  Count heading patterns, paragraph lengths
  Classify: STRUCTURED / MIXED / FLAT
    │
    ▼
CHUNK — Route to best strategy
  STRUCTURED → Split at detected headings
  MIXED      → Recursive paragraph split + heading context
  FLAT       → Semantic chunking (sentence-level similarity)
  Target: 512 tokens per chunk, 50-token overlap
    │
    ▼
ENRICH — Per chunk (async, batched)
  Generate 2 hypothetical questions via Claude
  Attach heading hierarchy metadata
  Attach document summary prefix
    │
    ▼
EMBED — Voyage voyage-3 (batches of 128)
  Embed contextual chunk text (with prefix)
  Embed hypothetical questions (separate vector)
    │
    ▼
INDEX — Insert into PostgreSQL
  chunks table: content + 2 embeddings + structural metadata
  Auto-indexed: HNSW (dense) + GIN (BM25)
  Update documents.status = "indexed"
```

---

## 7. Performance Targets

| Stage | Target | Condition |
|-------|--------|-----------|
| Query understanding (no rewrite) | <100ms | Simple, self-contained query |
| Query understanding (rewrite) | <500ms | Has conversation history |
| Broad retrieval (3 parallel) | <200ms | pgvector HNSW + GIN |
| Re-ranking (Cohere) | <350ms | 100 documents |
| Re-ranking (LLM fallback) | <2000ms | Complex/comparison only |
| User signal boost | <50ms | Materialized view lookup |
| LLM first token | <1500ms | Streaming SSE |
| **Total (simple)** | **<1.5s** | |
| **Total (complex)** | **<3.0s** | |

---

## 8. Evaluation

### 8.1 Auto-Generated Eval Sets

Since corpus varies, generate test Q&A pairs from the actual uploaded documents:

```python
async def generate_eval_set(document_ids, n=50):
    """Sample chunks, ask Claude to generate Q&A pairs, use chunk_id as ground truth."""
    chunks = await db.fetch_all(
        "SELECT * FROM chunks WHERE document_id = ANY(:ids) ORDER BY random() LIMIT :n",
        {"ids": document_ids, "n": n * 2}
    )
    eval_pairs = []
    for chunk in chunks[:n]:
        pair = await generate_qa_from_chunk(chunk)  # Claude generates question + answer
        pair["source_chunk_id"] = chunk["id"]
        eval_pairs.append(pair)
    return eval_pairs
```

### 8.2 Metrics

| Metric | What It Measures | Target |
|--------|-----------------|--------|
| Recall@8 | Correct chunk in top 8? | >85% |
| MRR | 1/rank of first correct chunk | >0.70 |
| NDCG@8 | Weighted ranking quality | >0.65 |
| Citation accuracy | [Source N] points to relevant chunk? | >90% |
| Faithfulness | Answer supported by context? | >95% |
| Latency P50 / P95 | Time to first token | <1.5s / <3.0s |
| User satisfaction | Thumbs-up rate | >70% |

### 8.3 A/B Testing

Deterministic bucket assignment by user_id. Compare configurations:

```python
EXPERIMENTS = {
    "baseline":    {"signals": ["dense", "sparse"],              "reranker": "cohere", "k": 8},
    "with_hyde":   {"signals": ["dense", "sparse", "question"],  "reranker": "cohere", "k": 8},
    "llm_rerank":  {"signals": ["dense", "sparse", "question"],  "reranker": "llm",    "k": 8},
    "larger_k":    {"signals": ["dense", "sparse", "question"],  "reranker": "cohere", "k": 12},
}
```
