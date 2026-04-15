-- Align user feedback query embeddings with Vertex 768-d vectors.
-- IMPORTANT:
-- 1) Existing query embeddings are cleared.
-- 2) The app should regenerate feedback/query embeddings as users interact.

BEGIN;

DROP INDEX IF EXISTS feedback_query_embedding_idx;

UPDATE user_feedback
SET query_embedding = NULL;

ALTER TABLE user_feedback
    ALTER COLUMN query_embedding TYPE vector(768);

CREATE INDEX feedback_query_embedding_idx ON user_feedback
    USING ivfflat (query_embedding vector_cosine_ops) WITH (lists = 100);

COMMIT;
