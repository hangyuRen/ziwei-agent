-- Application schema: current tables and views only.
-- Apply through init.sql or Repository.schema(); see sql/README.md.

-- Natal interpretations and their read-only section projection.
CREATE TABLE IF NOT EXISTS chart (
  chart_key VARCHAR(100) PRIMARY KEY,
  birth_year SMALLINT NOT NULL,
  birth_month SMALLINT NOT NULL,
  birth_day SMALLINT NOT NULL,
  birth_hour SMALLINT NOT NULL,
  gender VARCHAR(10) NOT NULL CHECK (gender IN ('male', 'female')),
  content JSONB NOT NULL,
  raw_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE OR REPLACE VIEW chart_section AS
SELECT c.chart_key, s.section_type,
       c.content->>s.section_type AS content,
       encode(sha256(convert_to(c.content->>s.section_type, 'UTF8')), 'hex') AS content_hash
FROM chart c
CROSS JOIN LATERAL unnest(ARRAY[
  'overview','personality','love','career','wealth','health','family',
  'children','move','friends','home','spirit','parents'
]) AS s(section_type);
-- Import bookkeeping for the optional local-file importer.
CREATE TABLE IF NOT EXISTS import_run (
  id BIGSERIAL PRIMARY KEY,
  source_path TEXT NOT NULL,
  source_sha256 CHAR(64) NOT NULL UNIQUE,
  source_kind VARCHAR(20) NOT NULL,
  row_count INTEGER NOT NULL,
  completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Explicit per-user memories exposed by /api/memory.
CREATE TABLE IF NOT EXISTS user_memory (
  owner_id VARCHAR(100) NOT NULL,
  memory_key VARCHAR(100) NOT NULL,
  value TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(owner_id, memory_key)
);

-- Active multi-user identity and chat storage; legacy sessions archived outside PG.
CREATE TABLE IF NOT EXISTS auth_user (
  id BIGSERIAL PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  email VARCHAR(255) UNIQUE,
  password_hash TEXT NOT NULL,
  token_version INTEGER NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS auth_login_attempt (
  id BIGSERIAL PRIMARY KEY,
  account_key VARCHAR(255) NOT NULL,
  client_ip INET NOT NULL,
  succeeded BOOLEAN NOT NULL,
  attempted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS auth_login_recent_idx ON auth_login_attempt(account_key, client_ip, attempted_at DESC);
CREATE TABLE IF NOT EXISTS chat_session (
  id UUID PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
  chart_key VARCHAR(100) REFERENCES chart(chart_key),
  chart_name VARCHAR(80),
  chart_input_birth JSONB,
  title VARCHAR(160) NOT NULL DEFAULT '新聊天',
  last_seq BIGINT NOT NULL DEFAULT 0,
  last_interaction_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS chat_session_owner_recent_idx
  ON chat_session(user_id, last_interaction_at DESC, id DESC) WHERE deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS chat_message (
  id UUID PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES chat_session(id) ON DELETE CASCADE,
  seq BIGINT NOT NULL,
  role VARCHAR(16) NOT NULL CHECK (role IN ('user','assistant','tool')),
  content JSONB NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'complete'
    CHECK (status IN ('pending','complete','failed')),
  tool_call_id VARCHAR(128),
  request_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(session_id, seq)
);
CREATE UNIQUE INDEX IF NOT EXISTS chat_message_user_request_idx
  ON chat_message(session_id, request_id) WHERE role='user' AND request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS chat_message_session_seq_idx ON chat_message(session_id, seq DESC);
CREATE INDEX IF NOT EXISTS chat_message_question_idx ON chat_message(session_id, seq DESC) WHERE role='user';
CREATE INDEX IF NOT EXISTS chat_message_request_idx ON chat_message(session_id, request_id, seq);
CREATE TABLE IF NOT EXISTS session_summary (
  session_id UUID PRIMARY KEY REFERENCES chat_session(id) ON DELETE CASCADE,
  summary JSONB NOT NULL,
  covered_seq BIGINT NOT NULL DEFAULT 0,
  revision BIGINT NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Named chart history; conversation snapshots remain independent of this table.
CREATE TABLE IF NOT EXISTS saved_chart (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
  chart_key VARCHAR(100) NOT NULL REFERENCES chart(chart_key),
  name VARCHAR(80) NOT NULL,
  input_birth JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, name, chart_key)
);
CREATE INDEX IF NOT EXISTS saved_chart_owner_recent_idx
  ON saved_chart(user_id, updated_at DESC, id DESC);
