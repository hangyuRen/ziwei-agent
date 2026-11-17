-- Usage from repository root: psql "$DATABASE_URL" -X -f sql/bootstrap.sql
-- Requires uv sync, local psql/zstd and Internet access; data is never bundled.
\set ON_ERROR_STOP on
\ir init.sql
\ir import_charts.sql
\ir import_tianji.sql
