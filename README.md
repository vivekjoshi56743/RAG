# RAG Search Engine

Production-quality document search and chat system. Handles 10K–200K+ page corpora across any document type.

## Architecture

```text
Frontend (Next.js 14)  →  Backend API (FastAPI)  →  Cloud SQL (PostgreSQL + pgvector)
                                                  →  Cloud Storage (PDFs)
                                                  →  Cohere (embeddings + re-ranking)
                                                  →  Anthropic Claude (chat + summaries)
```

## Quick Start (Local Dev)

```bash
cp .env.example .env
# Set COHERE_API_KEY and ANTHROPIC_API_KEY in .env

make dev               # Starts Postgres + MinIO + backend + frontend
make verify-pgvector   # Confirms pgvector is working
make seed              # Seeds demo user and folders
```

Then open <http://localhost:3000>.

### Local Docker Services

`docker-compose.yml` brings up these images/services:

- `pgvector/pgvector:pg16` → PostgreSQL + `pgvector` extension (`localhost:5432`)
- `minio/minio` → S3-compatible object storage (`localhost:9000`, console `localhost:9001`)
- `backend` (built from `backend/Dockerfile`) → FastAPI API (`localhost:8080`)
- `frontend` (built from `frontend/Dockerfile`) → Next.js app (`localhost:3000`)

### Local Wiring (How Data Flows)

1. Browser calls frontend on `localhost:3000`
2. Frontend calls backend via `NEXT_PUBLIC_API_URL` (`http://localhost:8080`)
3. Backend uses Postgres (`DATABASE_URL`) for metadata and vectors
4. Backend uses object storage (`GCS_BUCKET`; MinIO locally, GCS in cloud deployments)
5. AI providers are called from backend services:
   - Cohere: embeddings + reranking
   - Anthropic: summaries/query rewrite/chat

### Important Current Status

The repository currently contains many scaffolded API/UI routes marked `TODO`.  
So the local stack runs, health checks work, and infrastructure is ready, but full end-to-end document upload/search/chat behavior still needs route implementation.

## Repo Structure

```text
backend/     FastAPI app (Python)
frontend/    Next.js 14 app (TypeScript)
infra/       SQL schema, deploy scripts, CI/CD config
scripts/     Bulk data loaders, dev utilities
```

## Key Design Decisions

See [`RAG-Pipeline-Deep-Dive.md`](./RAG-Pipeline-Deep-Dive.md) and [`RAG-Engineering-Plan.md`](./RAG-Engineering-Plan.md) for full technical rationale.

- **Embeddings**: Cohere Embed (latest, query/document modes)
- **Chunking**: Adaptive — structure-aware / recursive / semantic based on document type
- **Retrieval**: 4-stage funnel — dense + sparse + question → RRF → Cohere rerank (latest) → user signals
- **Database**: PostgreSQL 15 + pgvector (HNSW indexes) + GIN (BM25 full-text)
- **Auth**: Firebase Auth (Google sign-in, JWT verified server-side)
- **Deploy**: Cloud Run (backend + frontend), Cloud SQL, Cloud Storage, Cloud Run Jobs (pipeline)

## Environment Variables

See `.env.example` for all required variables.
