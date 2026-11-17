\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE tianji_load (LIKE tianji_embedding INCLUDING DEFAULTS) ON COMMIT DROP;
\copy tianji_load (id,chunk_id,section_id,book,h2,h3,tianji_chunk,body,chunk_index,chunk_total,body_start,body_end,sources,bvid,part,section,t_hms,note,content_hash) FROM PROGRAM 'uv run --quiet --no-sync python scripts/data_stream.py tianji' WITH (FORMAT csv, NULL '\N')
INSERT INTO tianji_embedding AS current
SELECT * FROM tianji_load
ON CONFLICT(id) DO UPDATE SET
  chunk_id=excluded.chunk_id,section_id=excluded.section_id,book=excluded.book,
  h2=excluded.h2,h3=excluded.h3,tianji_chunk=excluded.tianji_chunk,body=excluded.body,
  chunk_index=excluded.chunk_index,chunk_total=excluded.chunk_total,
  body_start=excluded.body_start,body_end=excluded.body_end,sources=excluded.sources,
  bvid=excluded.bvid,part=excluded.part,section=excluded.section,t_hms=excluded.t_hms,note=excluded.note,
  embedding=CASE WHEN current.content_hash=excluded.content_hash THEN current.embedding ELSE NULL END,
  model=CASE WHEN current.content_hash=excluded.content_hash THEN current.model ELSE '' END,
  content_hash=excluded.content_hash,updated_at=now();
SELECT count(*) AS imported_tianji_chunks FROM tianji_load;
COMMIT;
