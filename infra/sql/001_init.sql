-- RAG Search Engine — Initial Schema
-- Run against a PostgreSQL 15+ instance with pgvector enabled.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firebase_uid TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Folders
CREATE TABLE IF NOT EXISTS folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#D4A853',
    icon TEXT DEFAULT '📁',
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, name)
);

-- Documents
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size BIGINT,
    mime_type TEXT,
    num_pages INTEGER,
    num_chunks INTEGER DEFAULT 0,
    status TEXT DEFAULT 'uploaded',
    error_message TEXT,
    summary TEXT,
    key_topics TEXT[] DEFAULT '{}',
    document_type TEXT DEFAULT 'general',
    tags TEXT[] DEFAULT '{}',
    folder_id UUID REFERENCES folders(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS documents_user_idx ON documents(user_id);
CREATE INDEX IF NOT EXISTS documents_folder_idx ON documents(user_id, folder_id);

-- Chunks (pgvector, 1024-dim Voyage voyage-3)
CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    page_number INTEGER,
    token_count INTEGER,
    section TEXT,
    section_heading TEXT,
    part TEXT,
    parent_chunk_id TEXT,
    embedding vector(1024),
    question_embedding vector(1024),
    hypothetical_questions TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- HNSW index — dense similarity search
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- HNSW index — question-to-question matching (HyDE)
CREATE INDEX IF NOT EXISTS chunks_question_embedding_idx ON chunks
    USING hnsw (question_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- GIN index — BM25 full-text search
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin(tsv);

-- Composite index — user-scoped retrieval
CREATE INDEX IF NOT EXISTS chunks_user_doc_idx ON chunks(user_id, document_id);

-- User Feedback
CREATE TABLE IF NOT EXISTS user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    query_text TEXT NOT NULL,
    query_embedding vector(1024),
    chunk_id UUID REFERENCES chunks(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    signal_type TEXT NOT NULL,
    signal_weight FLOAT NOT NULL,
    conversation_id UUID,
    message_id UUID,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS feedback_user_query_idx ON user_feedback(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS feedback_chunk_idx ON user_feedback(chunk_id);
CREATE INDEX IF NOT EXISTS feedback_query_embedding_idx ON user_feedback
    USING hnsw (query_embedding vector_cosine_ops);

-- Materialized views for fast preference lookups (refreshed every 15 min)
CREATE MATERIALIZED VIEW IF NOT EXISTS user_chunk_preferences AS
SELECT user_id, chunk_id, document_id,
       COUNT(*) AS interaction_count,
       SUM(signal_weight) AS preference_score,
       MAX(created_at) AS last_interaction
FROM user_feedback
WHERE created_at > now() - INTERVAL '90 days'
GROUP BY user_id, chunk_id, document_id;

CREATE UNIQUE INDEX IF NOT EXISTS ucp_pk ON user_chunk_preferences(user_id, chunk_id);
CREATE INDEX IF NOT EXISTS ucp_user_doc_idx ON user_chunk_preferences(user_id, document_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS user_document_preferences AS
SELECT user_id, document_id,
       SUM(preference_score) AS doc_preference_score,
       COUNT(DISTINCT chunk_id) AS engaged_chunks
FROM user_chunk_preferences
GROUP BY user_id, document_id;

CREATE UNIQUE INDEX IF NOT EXISTS udp_pk ON user_document_preferences(user_id, document_id);

-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title TEXT DEFAULT 'New Chat',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_conv_idx ON messages(conversation_id, created_at);

-- Shared conversation threads (public, read-only snapshots)
CREATE TABLE IF NOT EXISTS shared_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
    share_token TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    snapshot JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMPTZ,
    view_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS shared_threads_token_idx ON shared_threads(share_token) WHERE is_active = true;

-- Permissions (document or folder access grants)
CREATE TABLE IF NOT EXISTS permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    folder_id UUID REFERENCES folders(id) ON DELETE CASCADE,
    grantor_id UUID REFERENCES users(id) ON DELETE CASCADE,
    grantee_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'editor', 'admin')),
    created_at TIMESTAMPTZ DEFAULT now(),
    CHECK (
        (document_id IS NOT NULL AND folder_id IS NULL) OR
        (document_id IS NULL AND folder_id IS NOT NULL)
    ),
    UNIQUE(document_id, grantee_id),
    UNIQUE(folder_id, grantee_id)
);

CREATE INDEX IF NOT EXISTS permissions_grantee_idx ON permissions(grantee_id);
CREATE INDEX IF NOT EXISTS permissions_document_idx ON permissions(document_id);
CREATE INDEX IF NOT EXISTS permissions_folder_idx ON permissions(folder_id);
