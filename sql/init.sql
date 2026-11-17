\set ON_ERROR_STOP on
BEGIN;
\ir schema.sql
\ir tianji_embedding.sql
\ir migrations/001_session_birth_context.sql
\ir migrations/002_optional_embeddings.sql
COMMIT;
