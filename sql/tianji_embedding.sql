-- Current corpus storage. Kept standalone for ingestion/staging tooling.
-- The legacy tianji table is no longer part of the schema.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS tianji_embedding (
  id BIGINT PRIMARY KEY,
  chunk_id TEXT NOT NULL UNIQUE,
  section_id TEXT NOT NULL,
  book TEXT NOT NULL,
  h2 TEXT NOT NULL,
  h3 TEXT NOT NULL DEFAULT '',
  tianji_chunk TEXT NOT NULL,
  body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 500),
  chunk_index INTEGER NOT NULL CHECK (chunk_index >= 1),
  chunk_total INTEGER NOT NULL CHECK (chunk_total >= chunk_index),
  body_start INTEGER NOT NULL,
  body_end INTEGER NOT NULL,
  sources JSONB NOT NULL,
  bvid TEXT, part INTEGER, section INTEGER, t_hms TEXT, note TEXT,
  model TEXT NOT NULL DEFAULT '',
  content_hash CHAR(64) NOT NULL,
  embedding vector(1024),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(section_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS tianji_chunk_heading_idx ON tianji_embedding(book,h2,h3);
CREATE INDEX IF NOT EXISTS tianji_chunk_vector_idx ON tianji_embedding USING hnsw(embedding vector_cosine_ops);
