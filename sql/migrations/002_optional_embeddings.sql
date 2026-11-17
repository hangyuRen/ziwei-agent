-- Raw corpus imports must not require a paid embedding API call.
-- No existing vectors or model identifiers are modified.
ALTER TABLE tianji_embedding ALTER COLUMN embedding DROP NOT NULL;
ALTER TABLE tianji_embedding ALTER COLUMN model SET DEFAULT '';
