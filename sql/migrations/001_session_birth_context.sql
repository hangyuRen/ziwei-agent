-- Keep a session-owned snapshot independent of the saved-chart lifecycle.
-- Fresh databases already have these columns in schema.sql; older ones need ALTER.
ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS chart_name VARCHAR(80);
ALTER TABLE chat_session ADD COLUMN IF NOT EXISTS chart_input_birth JSONB;

-- Recover legacy context only when an owned, identically named saved chart
-- still exists and has not been modified since that conversation was created.
-- The saved_chart UNIQUE(user_id,name,chart_key) constraint makes this unambiguous.
UPDATE chat_session AS c
SET chart_input_birth=s.input_birth
FROM saved_chart AS s
WHERE c.chart_input_birth IS NULL
  AND c.user_id=s.user_id AND c.chart_key=s.chart_key AND c.chart_name=s.name
  AND s.updated_at<=c.created_at;
