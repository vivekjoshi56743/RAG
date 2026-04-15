# RAG Search Engine — Production Engineering Plan

**Owner:** Vivek
**Infrastructure:** GCP (Owner Access)
**Goal:** Production-quality, deployed, handles 10K+ page corpora

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND                                 │
│          Next.js 14 (App Router) on Cloud Run                   │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│   │ Doc Mgmt │  │ Search   │  │ Chat UI  │  │ PDF Viewer   │   │
│   └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
└────────────────────────┬────────────────────────────────────────┘
                         │ REST + WebSocket (streaming)
┌────────────────────────▼────────────────────────────────────────┐
│                     BACKEND API                                  │
│              FastAPI on Cloud Run                                 │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│   │ Auth     │  │ Upload   │  │ Search   │  │ Chat/RAG     │   │
│   │ Middleware│  │ Router   │  │ Router   │  │ Router       │   │
│   └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
└──────┬──────────────┬──────────────┬──────────────┬─────────────┘
       │              │              │              │
  ┌────▼────┐   ┌─────▼─────┐  ┌────▼────┐   ┌────▼──────┐
  │Firebase │   │  Cloud    │  │ Cloud   │   │ Anthropic │
  │Auth     │   │  Storage  │  │ SQL     │   │ API       │
  └─────────┘   │  (PDFs)   │  │(Postgres│   │ (Claude)  │
                └─────┬─────┘  │+pgvector│   └───────────┘
                      │        └────┬────┘
                ┌─────▼─────────────▼─────┐
                │   ASYNC WORKER PIPELINE  │
                │   Cloud Run Jobs         │
                │                          │
                │  PDF Parse → OCR →       │
                │  Chunk → Embed → Index   │
                └──────────────────────────┘
```

---

## 2. Tech Stack Decisions (with rationale)

### Backend: **FastAPI (Python)**
- Why: Native async, first-class support for ML/embedding libraries, streaming responses via SSE, huge ecosystem for PDF/NLP tooling.
- Alternative considered: Node.js — rejected because Python has better PDF parsing and embedding libraries.

### Database: **Cloud SQL (PostgreSQL 15) + pgvector**
- Why: pgvector is mature, managed by GCP, no extra infra to maintain. Handles millions of vectors with HNSW indexes. You already have GCP owner access.
- Why not Pinecone/Qdrant: Extra vendor, extra cost, extra auth. pgvector keeps everything in one database — documents metadata, chunks, vectors, conversations, users — all queryable with standard SQL + vector ops.
- Scale consideration: pgvector with HNSW index handles 1M+ vectors comfortably. For 10K pages ≈ ~50K chunks ≈ ~50K vectors — well within limits.

### Embeddings: **Cohere Embed (latest)** *(single-provider strategy)*
- Why: Keeps embeddings and reranking on one provider, reducing auth/config complexity and operational risk.
- Why this model family: High-quality general-purpose retrieval embeddings with asymmetric query/document modes and production-grade API reliability.
- Vector shape: 1024-dim embeddings align well with pgvector + HNSW for this scale.
- Cost: Competitive for both indexing and query-time embeddings at expected volume.
- Policy: No secondary embedding provider by default.

### Chunking: **Adaptive multi-strategy** *(auto-detects document structure)*
- Detection pass scans first 5 pages → classifies as STRUCTURED / MIXED / FLAT.
- Structured docs (manuals, specs): split at detected headings, preserve hierarchy.
- Mixed docs (papers, reports): recursive paragraph split with heading awareness.
- Flat docs (novels, essays): semantic chunking (split where sentence similarity drops).
- Default chunk size: 512 tokens. Every chunk enriched with 2 hypothetical questions for retrieval.

### Re-Ranking: **Cohere Rerank (latest)** + **Claude LLM reranker for complex queries**
- Why Cohere: Fast, high-quality reranking and consistent with the single-provider retrieval stack.
- Why LLM fallback: For comparison/multi-hop queries, Claude scores relevance more accurately (~0.70 NDCG@10) at the cost of ~2s latency.

### User Re-Ranking: **Custom feedback-weighted scoring**
- Collects explicit signals (thumbs up/down, citation clicks) and implicit signals (reformulations, dwell time).
- Materialized views aggregate preference scores per user × chunk and user × document.
- Applied as Stage 4 of a 4-stage retrieval funnel. Cold-start safe (skips for users with <10 signals).

> **Full pipeline details:** See companion document **"RAG Pipeline Deep Dive v2"** for adaptive chunking implementation, retrieval/reranking flow, user-signal collection, and evaluation framework. Provider policy for this plan is Cohere (embeddings + rerank) and Anthropic (LLM).

### Frontend: **Next.js 14 (App Router)**
- Why: SSR for fast loads, API routes if needed, React ecosystem, easy deployment to Cloud Run.

### Auth: **Firebase Auth**
- Why: Free tier covers most usage, Google sign-in out of the box, integrates with GCP IAM. JWT tokens verified server-side.

### PDF Processing: **PyMuPDF (fitz) + Google Cloud Vision (OCR)**
- Why: PyMuPDF is the fastest Python PDF parser. Cloud Vision handles scanned PDFs with near-perfect OCR.

### Object Storage: **Cloud Storage (GCS)**
- Why: Store original PDFs. Signed URLs for the document viewer. Cheap, scalable, already on GCP.

### Chat/LLM: **Anthropic API (Claude Sonnet)**
- Why: Strong instruction following, good at citation, cost-effective for chat.

---

## 3. Database Schema

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firebase_uid TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Documents
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,          -- GCS path
    file_size BIGINT,
    mime_type TEXT,
    num_pages INTEGER,
    num_chunks INTEGER DEFAULT 0,
    status TEXT DEFAULT 'uploaded',   -- uploaded | processing | indexed | error
    error_message TEXT,
    summary TEXT,
    tags TEXT[] DEFAULT '{}',
    folder TEXT DEFAULT '/',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Chunks (with pgvector) — updated for Cohere Embed (1024 dims) + structural metadata
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    page_number INTEGER,
    token_count INTEGER,
    -- Structural metadata (from structure-aware chunker)
    section TEXT,                      -- e.g., "§201.56"
    section_heading TEXT,              -- e.g., "Requirements on content and format..."
    part TEXT,                         -- e.g., "Part 201 — Labeling"
    parent_chunk_id TEXT,              -- link to parent for context retrieval
    -- Embeddings (Cohere Embed, 1024 dimensions)
    embedding vector(1024),            -- Document embedding (contextual prefix)
    question_embedding vector(1024),   -- Embedding of hypothetical questions
    hypothetical_questions TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- HNSW index for fast approximate nearest neighbor search
CREATE INDEX chunks_embedding_idx ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- HNSW index for hypothetical question matching
CREATE INDEX chunks_question_embedding_idx ON chunks
    USING hnsw (question_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- BM25 full-text search index (hybrid search)
ALTER TABLE chunks ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX chunks_tsv_idx ON chunks USING gin(tsv);

-- Composite index for user scoping
CREATE INDEX chunks_user_doc_idx ON chunks(user_id, document_id);

-- User Feedback (powers the user re-ranking model)
CREATE TABLE user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    query_text TEXT NOT NULL,
    query_embedding vector(1024),
    chunk_id UUID REFERENCES chunks(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    signal_type TEXT NOT NULL,         -- thumbs_up, thumbs_down, citation_click, reformulation, etc.
    signal_weight FLOAT NOT NULL,
    conversation_id UUID,
    message_id UUID,
    metadata JSONB DEFAULT '{}',       -- dwell_time_ms, position_in_results, etc.
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX feedback_user_query_idx ON user_feedback(user_id, created_at DESC);
CREATE INDEX feedback_chunk_idx ON user_feedback(chunk_id);
CREATE INDEX feedback_query_embedding_idx ON user_feedback
    USING hnsw (query_embedding vector_cosine_ops);

-- Materialized views for fast user preference lookups
CREATE MATERIALIZED VIEW user_chunk_preferences AS
SELECT user_id, chunk_id, document_id,
       COUNT(*) AS interaction_count,
       SUM(signal_weight) AS preference_score,
       MAX(created_at) AS last_interaction
FROM user_feedback
WHERE created_at > now() - INTERVAL '90 days'
GROUP BY user_id, chunk_id, document_id;

CREATE INDEX ucp_user_doc_idx ON user_chunk_preferences(user_id, document_id);

CREATE MATERIALIZED VIEW user_document_preferences AS
SELECT user_id, document_id,
       SUM(preference_score) AS doc_preference_score,
       COUNT(DISTINCT chunk_id) AS engaged_chunks
FROM user_chunk_preferences
GROUP BY user_id, document_id;

-- Conversations
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title TEXT DEFAULT 'New Chat',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                -- user | assistant
    content TEXT NOT NULL,
    citations JSONB DEFAULT '[]',     -- [{doc_id, doc_name, page, snippet}]
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX messages_conv_idx ON messages(conversation_id, created_at);
```

---

## 4. Corpus Strategy: Agnostic by Design

The system is corpus-agnostic — users upload whatever they need. The adaptive chunker, general-purpose embeddings (Cohere Embed), and hybrid retrieval all work across document types without configuration.

### Demo Corpus Recommendations (for showcasing at scale)

To demonstrate the system handles 10K+ pages, pre-load one of these:

| Corpus | Size | Why It's Good for Demo | Source |
|--------|------|----------------------|--------|
| **Python + React + Node.js docs** | ~8,000 pages | Technical, cross-doc comparison ("how does error handling differ in Python vs Node?"), dev audience loves it | Built-in doc exporters |
| **ArXiv CS papers (2024)** | ~10K papers | Academic, diverse topics, tests multi-document reasoning | arxiv.org bulk download |
| **US Code of Federal Regulations** | ~175K pages | Massive scale, legal precision, impressive demo | ecfr.gov/developers |
| **Wikipedia subset (any domain)** | Configurable | Diverse, well-known ground truth, easy to evaluate | Wikimedia dumps |
| **Project Gutenberg books** | ~60K books | Narrative, tests flat/semantic chunking, public domain | gutenberg.org |

**Recommendation:** Start with **Python + React + Node.js documentation** (~8K pages). It's the most relatable for a technical audience, lets you demo cross-framework comparison queries, and tests all three chunking strategies (structured for API docs, mixed for guides, flat for tutorials).

---

## 5. Implementation Phases

### Phase 0: Environment Setup (Day 1)
```
Tasks:
├── Create GCP project, enable APIs (Cloud SQL, Cloud Run, Cloud Storage, Cloud Vision)
├── Set up Cloud SQL PostgreSQL 15 instance with pgvector extension
├── Create GCS bucket for document storage
├── Set up Firebase Auth project
├── Create GitHub repo with monorepo structure:
│   ├── /backend    (FastAPI)
│   ├── /frontend   (Next.js)
│   ├── /worker     (processing pipeline)
│   ├── /infra      (Terraform or deployment scripts)
│   └── /scripts    (data loading, migrations)
├── Set up local dev environment (Docker Compose with Postgres+pgvector, MinIO for GCS)
└── Run database migrations, verify pgvector works
```

**Exit criteria:** `SELECT '[1,2,3]'::vector <=> '[4,5,6]'::vector;` returns a distance on your Cloud SQL instance.

---

### Phase 1: Document Ingestion Pipeline (Days 2–4)

This is the backbone. Get this right and everything else is straightforward.

```
Tasks:
├── Backend API
│   ├── POST /api/documents/upload — accepts file, stores in GCS, creates DB record, triggers pipeline
│   ├── GET  /api/documents — list user's documents with status
│   ├── GET  /api/documents/:id — single document details
│   └── DELETE /api/documents/:id — delete doc + chunks + GCS file
│
├── Processing Pipeline (async worker)
│   ├── Step 1: PDF Text Extraction
│   │   ├── PyMuPDF for text-based PDFs (fast, accurate)
│   │   ├── Cloud Vision OCR for scanned pages (detect via text density heuristic)
│   │   └── Output: list of (page_number, text) tuples
│   │
│   ├── Step 2: Chunking
│   │   ├── Strategy: RecursiveCharacterTextSplitter (LangChain-style)
│   │   ├── Chunk size: 512 tokens (~2000 chars) with 50-token overlap
│   │   ├── Respect paragraph/section boundaries where possible
│   │   ├── Each chunk tagged with: document_id, page_number, chunk_index
│   │   └── For CFR: use section headers as natural split points
│   │
│   ├── Step 3: Embedding Generation
│   │   ├── Batch embed via Cohere Embed API (batched async calls)
│   │   ├── Rate limiting + retry logic
│   │   └── Store embedding vectors in chunks table
│   │
│   ├── Step 4: Summary Generation
│   │   ├── Send first ~3000 tokens to Claude
│   │   ├── Generate 2-3 sentence summary
│   │   └── Store in documents.summary
│   │
│   └── Status Updates
│       ├── Update documents.status at each stage
│       └── WebSocket or polling endpoint for frontend progress
│
└── Bulk Loader Script
    ├── Download CFR Title 21 (or chosen corpus)
    ├── Parse XML/PDF into clean text per section
    └── Feed through pipeline in batches
```

**Key decisions for scale (10K+ pages):**
- Process documents asynchronously. Upload returns immediately; pipeline runs in background.
- Use Cloud Run Jobs for batch processing (auto-scales, no timeout issues).
- Embed in async batches via Cohere. For 50K chunks, process in worker batches with retries and backoff.
- Chunk size of 512 tokens is the sweet spot: small enough for precise retrieval, large enough for context.

**Exit criteria:** Upload a 100-page PDF, see it go from "uploaded" → "processing" → "indexed", verify chunks + embeddings exist in DB.

---

### Phase 2: Search (Days 5–6)

```
Tasks:
├── Hybrid Search Endpoint
│   ├── GET /api/search?q=...&limit=20
│   ├── Step 1: Dense retrieval (pgvector cosine similarity)
│   │   └── SELECT *, 1 - (embedding <=> query_embedding) AS semantic_score
│   │       FROM chunks WHERE user_id = $1
│   │       ORDER BY embedding <=> query_embedding LIMIT 40;
│   │
│   ├── Step 2: Sparse retrieval (PostgreSQL full-text search)
│   │   └── SELECT *, ts_rank(tsv, plainto_tsquery('english', $query)) AS bm25_score
│   │       FROM chunks WHERE user_id = $1 AND tsv @@ plainto_tsquery('english', $query)
│   │       ORDER BY bm25_score DESC LIMIT 40;
│   │
│   ├── Step 3: Reciprocal Rank Fusion (RRF)
│   │   ├── RRF_score = Σ 1/(k + rank_i) for each retrieval method
│   │   ├── k = 60 (standard constant)
│   │   ├── Merge and re-rank results
│   │   └── Return top 20 with scores
│   │
│   └── Step 4: Return results with metadata
│       └── {chunk_id, content, doc_name, page, score, snippet_highlight}
│
├── Query Embedding
│   └── Embed the user's query with the same Cohere model (single call, low latency)
│
└── Search Filters
    ├── Filter by document_id(s)
    ├── Filter by tags
    └── Filter by folder
```

**Why hybrid search matters at scale:**
Dense (vector) search catches semantic similarity ("payment terms" matches "financial obligations").
Sparse (BM25) search catches exact terms ("Section 201.56" matches "Section 201.56").
RRF combines both without needing to tune weights. This is what production RAG systems use.

**Exit criteria:** Search "what are the labeling requirements for prescription drugs" and get relevant CFR sections ranked correctly.

---

### Phase 3: Chat + RAG (Days 7–9)

```
Tasks:
├── Chat Endpoints
│   ├── POST /api/conversations — create new conversation
│   ├── GET  /api/conversations — list user's conversations
│   ├── POST /api/conversations/:id/messages — send message, get streamed response
│   └── DELETE /api/conversations/:id — delete conversation
│
├── RAG Pipeline (per user message)
│   ├── Step 1: Query Analysis
│   │   ├── Detect if query needs retrieval or is conversational ("thanks", "ok")
│   │   └── Optional: query rewriting for better retrieval (use Claude to expand abbreviations, resolve pronouns)
│   │
│   ├── Step 2: Retrieval
│   │   ├── Run hybrid search (Phase 2) with query
│   │   ├── Take top 8 chunks
│   │   ├── Optional: re-rank with a cross-encoder or Claude itself
│   │   └── Deduplicate near-identical chunks
│   │
│   ├── Step 3: Prompt Construction
│   │   ├── System prompt with instructions for citation format
│   │   ├── Retrieved chunks formatted as numbered sources
│   │   ├── Conversation history (last 10 messages)
│   │   └── User's current question
│   │
│   ├── Step 4: Streaming Response
│   │   ├── Call Anthropic API with stream=True
│   │   ├── Forward SSE chunks to frontend via WebSocket
│   │   └── On completion: save full message + citations to DB
│   │
│   └── Step 5: Citation Extraction
│       ├── Parse [Source N] references from Claude's response
│       ├── Map back to chunk metadata (doc_name, page, snippet)
│       └── Store structured citations in messages.citations JSONB
│
└── Multi-Document Reasoning
    ├── Retrieval naturally pulls from multiple docs
    ├── System prompt explicitly instructs: "When answering, reference all relevant documents"
    └── Test: "Compare labeling requirements in Title 21 Part 201 vs Part 801"
```

**Exit criteria:** Ask a multi-document question, get a streaming response with accurate inline citations.

---

### Phase 4: Frontend (Days 10–13)

```
Tasks:
├── Auth Pages
│   ├── /login — Google sign-in + email/password
│   ├── /signup — registration
│   └── Auth context provider, route guards
│
├── Document Management (/documents)
│   ├── Drag-and-drop upload zone with progress bars
│   ├── Document list with status badges (uploading → processing → indexed)
│   ├── Document detail panel (summary, stats, tags, delete)
│   ├── Folder tree sidebar
│   └── Tag management
│
├── Search (/search)
│   ├── Search bar with debounced input (300ms)
│   ├── Results list: snippet preview, doc name, page, relevance score
│   ├── Click result → opens document viewer at that page
│   └── Filter chips (by document, by tag)
│
├── Chat (/chat)
│   ├── Conversation list sidebar
│   ├── Message bubbles (user/assistant)
│   ├── Streaming text rendering (word by word)
│   ├── Citation badges below each assistant message
│   ├── Click citation → opens document viewer
│   ├── "New Chat" button
│   └── Chat input with Shift+Enter for newlines
│
├── Document Viewer (modal or side panel)
│   ├── Render PDF using react-pdf (PDF.js wrapper)
│   ├── Navigate to specific page from citation click
│   ├── Text highlight of the cited passage
│   └── Page navigation controls
│
└── Shared
    ├── Responsive layout (sidebar collapses on mobile)
    ├── Loading skeletons
    ├── Error boundaries
    └── Toast notifications
```

---

### Phase 5: Deployment (Days 14–15)

```
Tasks:
├── Backend Deployment
│   ├── Dockerize FastAPI app
│   ├── Deploy to Cloud Run (min 1 instance for cold start avoidance)
│   ├── Connect to Cloud SQL via Unix socket (Cloud SQL Auth Proxy)
│   ├── Set environment variables (API keys, DB URL, GCS bucket)
│   └── Set up Cloud Run Jobs for async document processing
│
├── Frontend Deployment
│   ├── Dockerize Next.js app
│   ├── Deploy to Cloud Run
│   └── Environment variables (API base URL, Firebase config)
│
├── Networking
│   ├── Cloud Load Balancer with custom domain (optional)
│   ├── SSL/TLS via managed certificates
│   ├── CORS configuration on backend
│   └── Cloud Armor for basic DDoS protection (free tier)
│
├── CI/CD
│   ├── GitHub Actions or Cloud Build
│   ├── On push to main → build Docker image → deploy to Cloud Run
│   └── Run migrations as part of deploy
│
└── Monitoring
    ├── Cloud Logging for application logs
    ├── Cloud Monitoring for latency, error rates
    ├── Uptime checks on /health endpoint
    └── Alert on error rate > 1%
```

**Deployment architecture:**
```
Internet → Cloud Load Balancer (HTTPS)
                ├── /api/* → Backend Cloud Run (FastAPI)
                │               └── Cloud SQL (pgvector)
                │               └── Cloud Storage (PDFs)
                │               └── Cohere API (embeddings + rerank)
                │               └── Anthropic API (chat)
                └── /*     → Frontend Cloud Run (Next.js)

Firebase Auth (client-side) → JWT verified by backend middleware
```

---

### Phase 6: Hardening & Stretch Goals (Days 16–20)

```
Tasks:
├── Performance
│   ├── Add Redis (Memorystore) for caching frequent queries
│   ├── Cache embeddings for repeated queries
│   ├── Connection pooling (asyncpg)
│   └── Load test with k6 or locust
│
├── Stretch Features
│   ├── Support Word (.docx), TXT, Markdown uploads (use python-docx, etc.)
│   ├── Share chat thread via public URL
│   ├── Folder organization for documents
│   ├── Per-document access controls
│   └── Export chat to PDF
│
└── Polish
    ├── Empty states, error states, edge cases
    ├── Mobile responsiveness
    ├── Keyboard shortcuts
    └── Analytics (who's using what, popular queries)
```

---

## 6. Cost Estimate (Monthly, at moderate usage ~500 queries/day)

| Service                  | Estimated Cost | Notes                                      |
|--------------------------|---------------|---------------------------------------------|
| Cloud SQL (db-f1-micro)  | ~$10          | Smallest instance, pgvector handles 50K vectors fine |
| Cloud Run (backend)      | ~$5–15        | Pay per request, min 1 instance             |
| Cloud Run (frontend)     | ~$5–10        | Static-ish, low compute                     |
| Cloud Storage            | ~$1           | PDF storage, pennies per GB                 |
| Cohere Embed             | ~$3–8         | Initial indexing + query embeddings (single provider) |
| Cohere Rerank            | ~$5–15        | $0.002/search × ~500 queries/day            |
| Anthropic API (chat)     | ~$15–40       | Claude Sonnet for RAG answers + query rewriting |
| Anthropic API (summaries)| ~$2–5         | One-time per document upload                |
| Firebase Auth            | Free          | Free up to 50K MAU                          |
| **Total**                | **~$48–106**  | Scales linearly with query volume           |

**Note:** The LLM-as-reranker (Stage 3 fallback for complex queries) adds ~$0.01/search when triggered. At 10% complex query rate: ~$1.50/month extra.

---

## 7. Repo Structure

```
rag-search-engine/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry
│   │   ├── config.py            # Environment config
│   │   ├── database.py          # SQLAlchemy + asyncpg setup
│   │   ├── auth.py              # Firebase JWT verification
│   │   ├── models/              # SQLAlchemy models
│   │   │   ├── user.py
│   │   │   ├── document.py
│   │   │   ├── chunk.py
│   │   │   ├── conversation.py
│   │   │   └── message.py
│   │   ├── routers/
│   │   │   ├── documents.py     # Upload, list, delete
│   │   │   ├── search.py        # Hybrid search endpoint
│   │   │   ├── chat.py          # RAG chat with streaming
│   │   │   ├── feedback.py      # User signal collection endpoint
│   │   │   ├── folders.py       # Folder CRUD
│   │   │   ├── permissions.py   # Access control management
│   │   │   ├── sharing.py       # Share chat thread via URL
│   │   │   └── health.py
│   │   ├── services/
│   │   │   ├── parsers/         # Multi-format parser registry
│   │   │   │   ├── __init__.py  # Parser registry + get_parser()
│   │   │   │   ├── pdf_parser.py
│   │   │   │   ├── docx_parser.py
│   │   │   │   ├── txt_parser.py
│   │   │   │   └── markdown_parser.py
│   │   │   ├── chunker.py       # Structure-aware chunking (512 tokens, hierarchy-preserving)
│   │   │   ├── embedder.py      # Cohere Embed (latest, async, batched, contextual prefixing)
│   │   │   ├── query_processor.py  # Query rewriting, decomposition, embedding
│   │   │   ├── retriever.py     # Stage 2: 3-signal hybrid retrieval + RRF
│   │   │   ├── reranker.py      # Stage 3: Cohere Rerank (latest) + LLM fallback
│   │   │   ├── user_reranker.py # Stage 4: User-signal preference scoring
│   │   │   ├── rag.py           # Full 4-stage RAG pipeline orchestration
│   │   │   ├── summarizer.py    # Auto-generated doc summaries via Claude
│   │   │   └── storage.py       # GCS upload/download
│   │   ├── pipeline/
│   │   │   └── process_document.py  # Async: parse → chunk → embed → index → summarize
│   │   └── tasks/
│   │       └── refresh_preferences.py  # Scheduled: refresh materialized views
│   ├── migrations/              # Alembic migrations
│   ├── Dockerfile
│   ├── requirements.txt
│   └── tests/
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx         # Landing / redirect
│   │   │   ├── login/
│   │   │   ├── chat/
│   │   │   ├── search/
│   │   │   └── documents/
│   │   ├── components/
│   │   │   ├── ChatMessage.tsx
│   │   │   ├── CitationBadge.tsx
│   │   │   ├── DocumentCard.tsx
│   │   │   ├── UploadZone.tsx
│   │   │   ├── SearchResult.tsx
│   │   │   ├── PDFViewer.tsx
│   │   │   └── Sidebar.tsx
│   │   ├── lib/
│   │   │   ├── api.ts           # Backend API client
│   │   │   ├── auth.ts          # Firebase auth hooks
│   │   │   └── types.ts
│   │   └── styles/
│   ├── Dockerfile
│   ├── package.json
│   └── tailwind.config.ts
│
├── infra/
│   ├── deploy.sh                # One-click deploy script
│   ├── cloudbuild.yaml          # CI/CD config
│   └── sql/
│       └── 001_init.sql         # Initial schema
│
├── scripts/
│   ├── load_cfr.py              # Bulk load CFR data
│   └── seed_demo.py             # Seed demo data
│
├── docker-compose.yml           # Local dev environment
├── Makefile                     # Common commands
└── README.md
```

---

## 8. Day-by-Day Timeline

| Day | Phase | Deliverable |
|-----|-------|-------------|
| 1 | Setup | GCP project, DB, GCS, Firebase, repo scaffold, local dev running |
| 2 | Ingestion | PDF upload endpoint, GCS storage, PyMuPDF text extraction |
| 3 | Ingestion | Chunking logic, Cohere embedding, pgvector storage |
| 4 | Ingestion | Async pipeline (Cloud Run Job), status tracking, bulk CFR loader |
| 5 | Search | Hybrid search endpoint (dense + sparse + RRF) |
| 6 | Search | Search API polish, filters, snippet highlighting |
| 7 | Chat | RAG pipeline: retrieval → prompt → Claude API |
| 8 | Chat | Streaming responses, citation extraction, conversation storage |
| 9 | Chat | Multi-turn context, query rewriting, edge case handling |
| 10 | Frontend | Auth pages, layout shell, document upload UI |
| 11 | Frontend | Search page, results rendering |
| 12 | Frontend | Chat UI with streaming, citation badges |
| 13 | Frontend | PDF viewer, document management polish |
| 14 | Deploy | Dockerize, deploy backend + frontend to Cloud Run, connect Cloud SQL |
| 15 | Deploy | Domain, SSL, CI/CD pipeline, smoke test end-to-end |
| 16–20 | Harden | Stretch goals, load testing, polish, documentation |

---

## 9. Stretch Goals — Full Implementation Details

These aren't afterthoughts — they're what separate a demo from a product people actually use. Each one below includes database changes, backend endpoints, frontend work, and the gotchas you'll hit.

---

### 9.1 Multi-Format File Support (Word, TXT, Markdown)

**The core idea:** Build a parser registry so the ingestion pipeline doesn't care what format the input is. Every parser outputs the same shape — a list of `{page: int, text: str}` — and everything downstream (chunking, embedding, indexing) stays identical.

#### Parser Registry Pattern

```python
# backend/app/services/parsers/__init__.py

from .pdf_parser import PDFParser
from .docx_parser import DocxParser
from .txt_parser import TxtParser
from .markdown_parser import MarkdownParser

PARSER_REGISTRY = {
    ".pdf":  PDFParser,
    ".docx": DocxParser,
    ".txt":  TxtParser,
    ".md":   MarkdownParser,
}

def get_parser(filename: str):
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    parser_cls = PARSER_REGISTRY.get(ext)
    if not parser_cls:
        raise UnsupportedFileType(f"No parser for {ext}")
    return parser_cls()
```

#### Word Parser (python-docx)

```python
# backend/app/services/parsers/docx_parser.py
from docx import Document
import io

class DocxParser:
    def extract(self, file_bytes: bytes) -> list[dict]:
        doc = Document(io.BytesIO(file_bytes))
        pages = []
        current_text = ""
        char_count = 0

        for para in doc.paragraphs:
            current_text += para.text + "\n"
            char_count += len(para.text)
            # Word doesn't have real "pages" — estimate at ~3000 chars
            if char_count >= 3000:
                pages.append({"page": len(pages) + 1, "text": current_text})
                current_text = ""
                char_count = 0

        if current_text.strip():
            pages.append({"page": len(pages) + 1, "text": current_text})

        # Extract tables as structured text
        for table in doc.tables:
            rows = []
            for row in table.rows:
                rows.append(" | ".join(cell.text.strip() for cell in row.cells))
            table_text = "\n".join(rows)
            if table_text.strip():
                pages.append({"page": len(pages) + 1, "text": f"[Table]\n{table_text}"})

        return pages
```

#### TXT Parser (with encoding detection)

```python
class TxtParser:
    def extract(self, file_bytes: bytes) -> list[dict]:
        # Try UTF-8, fall back to latin-1 (never fails)
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")

        # Split into ~3000-char "pages" at paragraph boundaries
        pages = []
        current = ""
        for para in text.split("\n\n"):
            current += para + "\n\n"
            if len(current) >= 3000:
                pages.append({"page": len(pages) + 1, "text": current.strip()})
                current = ""
        if current.strip():
            pages.append({"page": len(pages) + 1, "text": current.strip()})
        return pages
```

#### Markdown Parser (strip syntax, preserve structure)

```python
import re

class MarkdownParser:
    def extract(self, file_bytes: bytes) -> list[dict]:
        text = file_bytes.decode("utf-8")

        # Strip markdown syntax but preserve semantic structure
        text = re.sub(r'```[\s\S]*?```', '[code block]', text)     # Fenced code
        text = re.sub(r'!\[.*?\]\(.*?\)', '[image]', text)         # Images
        text = re.sub(r'\[(.+?)\]\(.*?\)', r'\1', text)            # Links → text
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)               # Bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)                   # Italic
        text = re.sub(r'`(.+?)`', r'\1', text)                     # Inline code

        # Split by H1/H2 headers as natural section boundaries
        sections = re.split(r'\n(?=#{1,2}\s)', text)
        pages = []
        for section in sections:
            clean = re.sub(r'^#{1,6}\s+', '', section, flags=re.MULTILINE).strip()
            if clean:
                pages.append({"page": len(pages) + 1, "text": clean})
        return pages if pages else [{"page": 1, "text": text}]
```

#### Pipeline Integration — One Line Change

```python
# backend/app/pipeline/process_document.py

# BEFORE (PDF-only):
pages = pdf_parser.extract(file_bytes)

# AFTER (multi-format):
parser = get_parser(document.name)
pages = parser.extract(file_bytes)
# Everything downstream is unchanged — chunking, embedding, indexing all work
```

#### Frontend Changes
- Upload zone `accept` attribute: `.pdf,.docx,.txt,.md`
- File type icons: 📕 PDF, 📘 Word, 📄 TXT, 📝 Markdown
- Document viewer: PDF uses react-pdf; Word/TXT/Markdown render as formatted HTML in a panel

#### Database Changes
None. The `documents.mime_type` field already handles this. Chunks don't know or care about source format.

#### Gotchas
- Word files with embedded images: `python-docx` can't OCR images inside .docx. Flag these as "partial extraction" in the UI.
- Encoding detection for TXT: `chardet` library is more robust than the try/except approach for international text. Add it as a fallback.
- Markdown with heavy LaTeX: Strip LaTeX blocks or convert with a basic regex, don't try to render them.

---

### 9.2 Auto-Generated Document Summaries on Upload

**The core idea:** After text extraction and before/during chunking, send the first ~4000 tokens to Claude and generate a structured summary. Store it on the document record. Display it on the document card and in search results.

#### Backend Implementation

```python
# backend/app/services/summarizer.py
import anthropic

async def generate_summary(text: str, doc_name: str) -> dict:
    """Generate a structured summary with key topics."""
    # Take first ~4000 tokens worth of text (roughly 16K chars)
    excerpt = text[:16000]

    client = anthropic.AsyncAnthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""Analyze this document and return a JSON object with:
- "summary": 2-3 sentence overview of the document
- "key_topics": array of 3-5 main topics/themes (short phrases)
- "document_type": one of ["legal", "technical", "academic", "business", "general"]

Document: "{doc_name}"

{excerpt}

Respond ONLY with valid JSON, no markdown fences."""
        }]
    )

    import json
    try:
        result = json.loads(response.content[0].text)
    except json.JSONDecodeError:
        result = {
            "summary": response.content[0].text[:300],
            "key_topics": [],
            "document_type": "general"
        }

    return result
```

#### Pipeline Integration

```python
# In process_document.py, after text extraction, before embedding:

# Step 2.5: Generate summary
full_text = "\n".join(page["text"] for page in pages)
summary_data = await generate_summary(full_text, document.name)

await db.execute(
    """UPDATE documents
       SET summary = :summary,
           key_topics = :topics,
           document_type = :doc_type
       WHERE id = :id""",
    {
        "summary": summary_data["summary"],
        "topics": summary_data["key_topics"],
        "doc_type": summary_data["document_type"],
        "id": document.id,
    }
)
```

#### Database Changes

```sql
ALTER TABLE documents ADD COLUMN key_topics TEXT[] DEFAULT '{}';
ALTER TABLE documents ADD COLUMN document_type TEXT DEFAULT 'general';
-- summary column already exists in the original schema
```

#### Frontend Display

The document card in the library shows:
- Summary text (2-3 sentences, collapsed by default)
- Topic pills (clickable — filters search to that topic)
- Document type badge (color-coded icon)

Summary also appears in search results as context beneath the document name, helping users evaluate relevance before clicking.

#### Cost & Performance
- One Claude Sonnet call per document upload (~$0.003-0.01 per document)
- Runs async, doesn't block the upload — user sees "Generating summary..." status
- For bulk loading 1000+ documents: batch these, rate-limit to 50 concurrent calls

---

### 9.3 Share a Chat Thread via URL

**The core idea:** Generate a public, read-only snapshot of a conversation. The shared URL doesn't require login. The snapshot is frozen at share time — subsequent messages in the original conversation don't appear.

#### Database Changes

```sql
CREATE TABLE shared_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
    share_token TEXT UNIQUE NOT NULL,       -- short URL-safe token
    title TEXT NOT NULL,
    snapshot JSONB NOT NULL,                -- frozen copy of messages + citations
    is_active BOOLEAN DEFAULT true,         -- owner can revoke
    expires_at TIMESTAMPTZ,                 -- optional expiration
    view_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX shared_threads_token_idx ON shared_threads(share_token) WHERE is_active = true;
```

#### Backend Endpoints

```python
# backend/app/routers/sharing.py

@router.post("/api/conversations/{conv_id}/share")
async def share_conversation(conv_id: UUID, user: User = Depends(get_current_user)):
    """Create a shareable snapshot of a conversation."""
    # Verify ownership
    conv = await db.fetch_one(
        "SELECT * FROM conversations WHERE id = :id AND user_id = :uid",
        {"id": conv_id, "uid": user.id}
    )
    if not conv:
        raise HTTPException(404)

    # Fetch all messages
    messages = await db.fetch_all(
        "SELECT role, content, citations, created_at FROM messages WHERE conversation_id = :id ORDER BY created_at",
        {"id": conv_id}
    )

    # Generate short token (URL-safe, 10 chars)
    import secrets
    token = secrets.token_urlsafe(8)[:10]

    # Create frozen snapshot
    snapshot = {
        "messages": [dict(m) for m in messages],
        "document_names": list(set(
            c["doc_name"]
            for m in messages
            for c in (m["citations"] or [])
        )),
        "created_at": datetime.utcnow().isoformat(),
    }

    await db.execute(
        """INSERT INTO shared_threads (conversation_id, owner_id, share_token, title, snapshot)
           VALUES (:conv_id, :uid, :token, :title, :snapshot)""",
        {"conv_id": conv_id, "uid": user.id, "token": token, "title": conv["title"], "snapshot": json.dumps(snapshot)}
    )

    return {"share_url": f"https://yourdomain.com/shared/{token}", "token": token}


@router.get("/api/shared/{token}")
async def get_shared_thread(token: str):
    """Public endpoint — no auth required."""
    thread = await db.fetch_one(
        """UPDATE shared_threads SET view_count = view_count + 1
           WHERE share_token = :token AND is_active = true
           RETURNING title, snapshot, view_count, created_at""",
        {"token": token}
    )
    if not thread:
        raise HTTPException(404, "Thread not found or has been revoked")

    return {
        "title": thread["title"],
        "messages": json.loads(thread["snapshot"])["messages"],
        "document_names": json.loads(thread["snapshot"])["document_names"],
        "view_count": thread["view_count"],
        "shared_at": thread["created_at"],
    }


@router.delete("/api/conversations/{conv_id}/share/{token}")
async def revoke_share(conv_id: UUID, token: str, user: User = Depends(get_current_user)):
    """Owner can revoke a shared link."""
    await db.execute(
        "UPDATE shared_threads SET is_active = false WHERE share_token = :token AND owner_id = :uid",
        {"token": token, "uid": user.id}
    )
    return {"revoked": True}
```

#### Frontend

**Share button in chat header:**
- Click "Share" → API call → modal shows the URL with a copy button
- Toggle to set expiration (24h, 7d, 30d, never)
- List of active shares with view counts and revoke buttons

**Shared thread page (`/shared/[token]`):**
- Public page, no auth required, clean read-only layout
- Shows conversation title, messages with citations, "Shared from RAG Engine" branding
- No chat input (read-only)
- Banner: "This is a shared conversation snapshot. Create your own at [link]"

#### Security Considerations
- Shared snapshots are **frozen copies** — they don't expose the live conversation or any documents
- No document content is included, only document names and page references in citations
- The snippet text in citations is the only document content visible (same as what the LLM already surfaced)
- Owner can revoke anytime
- Optional expiration prevents forgotten public links

---

### 9.4 Folder Organization for Documents

**The core idea:** A simple, one-level-deep folder system (like Gmail labels, not a nested filesystem). Users create folders, drag documents into them, and filter everything by folder. Keeps it simple while covering 95% of organization needs.

#### Why One Level, Not Nested?
Nested folders create complexity: recursive queries, path resolution, move semantics, breadcrumbs. One level (essentially "collections" or "labels") covers the real use case — grouping related documents — without the engineering overhead. A document can belong to one folder. There's always an implicit "All Documents" view.

#### Database Changes

```sql
CREATE TABLE folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#D4A853',      -- accent color for the folder
    icon TEXT DEFAULT '📁',            -- emoji icon
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, name)
);

-- Add folder reference to documents (already has a 'folder' TEXT column — replace with proper FK)
ALTER TABLE documents ADD COLUMN folder_id UUID REFERENCES folders(id) ON DELETE SET NULL;
CREATE INDEX documents_folder_idx ON documents(user_id, folder_id);
```

#### Backend Endpoints

```python
# backend/app/routers/folders.py

@router.post("/api/folders")
async def create_folder(body: CreateFolderRequest, user: User = Depends(get_current_user)):
    folder = await db.fetch_one(
        """INSERT INTO folders (user_id, name, color, icon)
           VALUES (:uid, :name, :color, :icon) RETURNING *""",
        {"uid": user.id, "name": body.name, "color": body.color, "icon": body.icon}
    )
    return folder

@router.get("/api/folders")
async def list_folders(user: User = Depends(get_current_user)):
    folders = await db.fetch_all(
        """SELECT f.*, COUNT(d.id) as doc_count
           FROM folders f LEFT JOIN documents d ON d.folder_id = f.id
           WHERE f.user_id = :uid
           GROUP BY f.id ORDER BY f.sort_order""",
        {"uid": user.id}
    )
    return folders

@router.put("/api/documents/{doc_id}/move")
async def move_to_folder(doc_id: UUID, body: MoveRequest, user: User = Depends(get_current_user)):
    """Move a document into a folder (or null to unfolder)."""
    await db.execute(
        "UPDATE documents SET folder_id = :fid WHERE id = :did AND user_id = :uid",
        {"fid": body.folder_id, "did": doc_id, "uid": user.id}
    )
    return {"moved": True}

@router.put("/api/documents/bulk-move")
async def bulk_move(body: BulkMoveRequest, user: User = Depends(get_current_user)):
    """Move multiple documents at once."""
    await db.execute(
        "UPDATE documents SET folder_id = :fid WHERE id = ANY(:ids) AND user_id = :uid",
        {"fid": body.folder_id, "ids": body.document_ids, "uid": user.id}
    )
    return {"moved": len(body.document_ids)}
```

#### Frontend

**Sidebar folder tree:**
```
📚 All Documents (47)
─────────────────────
📁 FDA Regulations (23)
📁 Contract Reviews (12)
📁 Research Papers (8)
📁 Unfiled (4)
─────────────────────
+ New Folder
```

- Click folder → filters document list and scopes search/chat to that folder
- Drag document card onto folder in sidebar to move
- Right-click folder → rename, change color, delete (moves docs to unfiled)
- "New Folder" button with name + color picker

**Search/Chat integration:**
- Folder filter chip in search: "Search in: FDA Regulations ✕"
- Chat can be scoped to a folder: "Ask about documents in [folder]"
- The retrieval query adds `WHERE folder_id = :fid` when a folder is selected

---

### 9.5 Access Controls per Document or Collection

**The core idea:** A permission system that lets users share specific documents or entire folders with other users, with role-based access (viewer, editor, admin). This is the most complex stretch goal — it touches auth, every query, and the entire frontend.

#### Permission Model

Three levels of access:
- **viewer** — can search and chat against the document, see it in their library, but can't edit/delete
- **editor** — can re-tag, move to folders, update metadata, but can't delete or change permissions
- **admin** — full control including delete and permission management

Every document has an **owner** (the uploader). The owner is implicitly admin. Additional users get access via explicit grants on either a document or a folder (folder grants cascade to all documents in that folder).

#### Database Changes

```sql
CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- One of these will be set, not both
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    folder_id UUID REFERENCES folders(id) ON DELETE CASCADE,

    grantor_id UUID REFERENCES users(id) ON DELETE CASCADE,   -- who granted
    grantee_id UUID REFERENCES users(id) ON DELETE CASCADE,   -- who received

    role TEXT NOT NULL CHECK (role IN ('viewer', 'editor', 'admin')),
    created_at TIMESTAMPTZ DEFAULT now(),

    -- Exactly one target
    CHECK (
        (document_id IS NOT NULL AND folder_id IS NULL) OR
        (document_id IS NULL AND folder_id IS NOT NULL)
    ),
    -- No duplicate grants
    UNIQUE(document_id, grantee_id),
    UNIQUE(folder_id, grantee_id)
);

CREATE INDEX permissions_grantee_idx ON permissions(grantee_id);
CREATE INDEX permissions_document_idx ON permissions(document_id);
CREATE INDEX permissions_folder_idx ON permissions(folder_id);
```

#### The Access Check — A Reusable Query Fragment

Every query that touches documents or chunks needs to respect permissions. Build this as a database function:

```sql
CREATE OR REPLACE FUNCTION user_can_access_document(
    p_user_id UUID,
    p_document_id UUID,
    p_min_role TEXT DEFAULT 'viewer'
) RETURNS BOOLEAN AS $$
DECLARE
    role_rank JSONB := '{"viewer": 1, "editor": 2, "admin": 3}'::jsonb;
    required_rank INT;
    actual_rank INT;
BEGIN
    required_rank := (role_rank ->> p_min_role)::int;

    -- Check 1: Is the user the owner?
    IF EXISTS (SELECT 1 FROM documents WHERE id = p_document_id AND user_id = p_user_id) THEN
        RETURN true;
    END IF;

    -- Check 2: Direct document permission
    SELECT (role_rank ->> p.role)::int INTO actual_rank
    FROM permissions p
    WHERE p.document_id = p_document_id AND p.grantee_id = p_user_id;
    IF actual_rank >= required_rank THEN RETURN true; END IF;

    -- Check 3: Folder-level permission (cascades to documents in that folder)
    SELECT (role_rank ->> p.role)::int INTO actual_rank
    FROM permissions p
    JOIN documents d ON d.folder_id = p.folder_id
    WHERE d.id = p_document_id AND p.grantee_id = p_user_id;
    IF actual_rank >= required_rank THEN RETURN true; END IF;

    RETURN false;
END;
$$ LANGUAGE plpgsql STABLE;
```

#### Modified Queries — Before vs After

```sql
-- BEFORE: List user's documents
SELECT * FROM documents WHERE user_id = :uid;

-- AFTER: List documents user owns OR has access to
SELECT DISTINCT d.*, 
    CASE WHEN d.user_id = :uid THEN 'owner'
         ELSE COALESCE(p_doc.role, p_folder.role)
    END AS user_role
FROM documents d
LEFT JOIN permissions p_doc ON p_doc.document_id = d.id AND p_doc.grantee_id = :uid
LEFT JOIN permissions p_folder ON p_folder.folder_id = d.folder_id AND p_folder.grantee_id = :uid
WHERE d.user_id = :uid
   OR p_doc.grantee_id = :uid
   OR p_folder.grantee_id = :uid;
```

```sql
-- BEFORE: Search chunks
SELECT * FROM chunks WHERE user_id = :uid ORDER BY embedding <=> :query LIMIT 20;

-- AFTER: Search chunks across owned + shared documents
SELECT c.* FROM chunks c
JOIN documents d ON c.document_id = d.id
LEFT JOIN permissions p_doc ON p_doc.document_id = d.id AND p_doc.grantee_id = :uid
LEFT JOIN permissions p_folder ON p_folder.folder_id = d.folder_id AND p_folder.grantee_id = :uid
WHERE (d.user_id = :uid OR p_doc.grantee_id = :uid OR p_folder.grantee_id = :uid)
ORDER BY c.embedding <=> :query
LIMIT 20;
```

#### Backend Endpoints

```python
# backend/app/routers/permissions.py

@router.post("/api/documents/{doc_id}/share")
async def share_document(doc_id: UUID, body: ShareRequest, user: User = Depends(get_current_user)):
    """Grant access to a document. Only owner/admin can do this."""
    # Verify caller has admin access
    if not await user_can_access(user.id, document_id=doc_id, min_role="admin"):
        raise HTTPException(403)

    # Look up grantee by email
    grantee = await db.fetch_one("SELECT id FROM users WHERE email = :email", {"email": body.email})
    if not grantee:
        raise HTTPException(404, "User not found. They need to sign up first.")

    await db.execute(
        """INSERT INTO permissions (document_id, grantor_id, grantee_id, role)
           VALUES (:did, :grantor, :grantee, :role)
           ON CONFLICT (document_id, grantee_id) DO UPDATE SET role = :role""",
        {"did": doc_id, "grantor": user.id, "grantee": grantee["id"], "role": body.role}
    )
    return {"shared": True}

@router.post("/api/folders/{folder_id}/share")
async def share_folder(folder_id: UUID, body: ShareRequest, user: User = Depends(get_current_user)):
    """Grant access to all documents in a folder."""
    # Similar to above but targets folder_id
    ...

@router.get("/api/documents/{doc_id}/permissions")
async def list_permissions(doc_id: UUID, user: User = Depends(get_current_user)):
    """List who has access to a document."""
    ...

@router.delete("/api/documents/{doc_id}/permissions/{perm_id}")
async def revoke_permission(doc_id: UUID, perm_id: UUID, user: User = Depends(get_current_user)):
    """Revoke someone's access."""
    ...
```

#### Frontend

**Share modal (triggered from document card or folder):**
```
┌─────────────────────────────────────┐
│ Share "FDA Title 21"                │
│                                     │
│ ┌─────────────────────┐ ┌────────┐  │
│ │ Enter email...      │ │ Viewer▾│  │
│ └─────────────────────┘ └────────┘  │
│                          [Share]    │
│                                     │
│ People with access:                 │
│ 👤 vivek@co.com        Owner       │
│ 👤 alice@co.com        Editor  [✕] │
│ 👤 bob@co.com          Viewer  [✕] │
│                                     │
│ 🔗 Copy link  │  ⚙ Anyone with    │
│               │    link can view   │
└─────────────────────────────────────┘
```

**Shared-with-me section in sidebar:**
```
📚 My Documents (47)
👥 Shared with Me (8)
   └── 3 from alice@co.com
   └── 5 from team-folder
```

**Visual indicators:**
- Shared documents show a 👥 badge on the card
- Role shown as subtle text: "Shared · Viewer"
- Actions disabled based on role (e.g., viewer can't see delete button)

#### Security Considerations
- **Every API endpoint** checks permissions before returning data. No client-side-only enforcement.
- Chunk search respects permissions — you can't retrieve chunks from documents you don't have access to, even via RAG chat.
- Folder sharing cascades: adding a doc to a shared folder automatically makes it visible to folder grantees.
- Removing a doc from a shared folder removes the inherited access (unless there's a direct doc-level grant).
- Rate-limit the share endpoint to prevent enumeration attacks.

---

### 9.6 Updated Timeline with Stretch Goals

| Day | Phase | Deliverable |
|-----|-------|-------------|
| 1 | Setup | GCP project, DB, GCS, Firebase, repo scaffold, local dev |
| 2–3 | Ingestion | Multi-format parser registry + PDF/DOCX/TXT/MD parsers |
| 4 | Ingestion | Chunking, embedding, async pipeline, auto-summaries |
| 5 | Ingestion | Bulk CFR loader, status tracking, summary display |
| 6 | Search | Hybrid search (dense + sparse + RRF) |
| 7 | Search | Filters by folder/tag, snippet highlighting |
| 8 | Chat | RAG pipeline: retrieval → prompt → Claude streaming |
| 9 | Chat | Citations, multi-turn, query rewriting |
| 10 | Folders | Folder CRUD, move documents, sidebar tree, scoped search |
| 11 | Sharing | Share chat thread via URL, public read-only page |
| 12 | Access | Permission model, share documents/folders, access checks |
| 13 | Frontend | Auth, document upload UI, document management |
| 14 | Frontend | Search UI, chat UI with streaming + citations |
| 15 | Frontend | PDF viewer, folder UI, share modals, permission UI |
| 16 | Deploy | Dockerize, Cloud Run, Cloud SQL, SSL, domain |
| 17 | Deploy | CI/CD, monitoring, health checks |
| 18–20 | Polish | Load testing, edge cases, mobile, documentation |

---

## 10. Immediate Next Steps

1. **Create the GCP project** and enable Cloud SQL, Cloud Run, Cloud Storage, Cloud Vision APIs.
2. **Provision Cloud SQL** — PostgreSQL 15, enable pgvector extension.
3. **Get API keys** — Cohere (embeddings + re-ranking) and Anthropic (chat + summaries).
4. **Set up the repo** with the monorepo structure from Section 7.
5. **Start with Phase 1** — the adaptive ingestion pipeline (parser registry + structure-aware chunking + embedding) is the foundation everything else depends on.
6. **Prepare demo corpus** — download Python + React + Node.js docs (~8K pages) to test the pipeline at scale.

When you're ready, I can start building any of these phases — actual production Python code, Dockerfiles, deployment scripts, database migrations, the frontend — whatever you want to tackle first.
