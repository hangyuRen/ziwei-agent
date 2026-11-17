-- psql script, run from repository root. No PostgreSQL superuser PROGRAM privilege.
\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE chart_load (LIKE chart INCLUDING DEFAULTS) ON COMMIT DROP;
\copy chart_load (chart_key,birth_year,birth_month,birth_day,birth_hour,gender,content,raw_meta) FROM PROGRAM 'uv run --quiet --no-sync python scripts/data_stream.py chart' WITH (FORMAT csv, NULL '\N')
INSERT INTO chart(chart_key,birth_year,birth_month,birth_day,birth_hour,gender,content,raw_meta)
SELECT chart_key,birth_year,birth_month,birth_day,birth_hour,gender,content,raw_meta FROM chart_load
ON CONFLICT(chart_key) DO UPDATE SET content=excluded.content,raw_meta=excluded.raw_meta,updated_at=now();
SELECT count(*) AS imported_charts FROM chart_load;
COMMIT;
