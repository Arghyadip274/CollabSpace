-- Enable pgvector extension for semantic search (Phase 6)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create embeddings table for document chunks (Phase 6)
-- This is separate from Prisma schema since prisma-client-py doesn't support vector type natively
CREATE TABLE IF NOT EXISTS document_embeddings (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text  TEXT NOT NULL,
    embedding   vector(768),    -- Gemini text-embedding-004 outputs 768 dims
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS document_embeddings_vector_idx
    ON document_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
