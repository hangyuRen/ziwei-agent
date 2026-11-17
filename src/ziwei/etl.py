import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

from .db import Repository
from .models import ChartRow, SECTIONS, TianjiRow, digest


def lines(path: Path):
    if path.suffix == ".zst":
        proc = subprocess.Popen(["zstd", "-dc", "--long=27", str(path)], stdout=subprocess.PIPE, text=True, encoding="utf-8")
        finished = False
        try:
            yield from proc.stdout
            finished = True
        finally:
            proc.stdout.close()
            if not finished:
                proc.terminate()
            if proc.wait() != 0 and finished:
                raise RuntimeError(f"zstd failed: {path}")
    else:
        with path.open(encoding="utf-8") as file:
            yield from file


def file_sha(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


async def chart_batch(repo, batch):
    async with repo.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""CREATE TEMP TABLE chart_stage(
                chart_key varchar(100),birth_year smallint,birth_month smallint,birth_day smallint,
                birth_hour smallint,gender varchar(10),content text,raw_meta text) ON COMMIT DROP""")
            await conn.copy_records_to_table("chart_stage", records=[
                (r.k,r.y,r.m,r.d,r.h,r.g,json.dumps(r.c,ensure_ascii=False),
                 json.dumps({'ms':r.ms,'t':r.t},ensure_ascii=False)) for r in batch])
            await conn.execute("""INSERT INTO chart(chart_key,birth_year,birth_month,birth_day,birth_hour,gender,content,raw_meta)
            SELECT chart_key,birth_year,birth_month,birth_day,birth_hour,gender,content::jsonb,raw_meta::jsonb
            FROM chart_stage ON CONFLICT(chart_key) DO UPDATE SET content=excluded.content,
            raw_meta=excluded.raw_meta,updated_at=now()""")
            rows = [(r.k,s,digest(r.c[s])) for r in batch for s in SECTIONS]
            await conn.execute("CREATE TEMP TABLE section_stage(chart_key varchar(100),section_type varchar(32),content_hash char(64)) ON COMMIT DROP")
            await conn.copy_records_to_table("section_stage", records=rows)
            bad = await conn.fetchval("""SELECT count(*) FROM section_stage s JOIN chart c USING(chart_key)
            WHERE encode(sha256(convert_to(c.content->>s.section_type,'UTF8')),'hex')<>s.content_hash
               OR c.content->>s.section_type IS NULL""")
            if bad:
                raise RuntimeError(f"section consistency failed: {bad}")


async def import_file(repo, path: Path, kind: str, batch_size: int = 100):
    sha = file_sha(path)
    if kind == "tianji":
        from .tianji_ingest import import_corpus
        count = await import_corpus(repo, path)
        await repo.pool.execute("INSERT INTO import_run(source_path,source_sha256,source_kind,row_count) VALUES($1,$2,$3,$4) ON CONFLICT(source_sha256) DO UPDATE SET row_count=excluded.row_count", str(path),sha,kind,count)
        return count
    old = await repo.pool.fetchval("SELECT row_count FROM import_run WHERE source_sha256=$1", sha)
    if old is not None:
        return old
    count, batch = 0, []
    for line_number, line in enumerate(lines(path), 1):
        try:
            obj = json.loads(line)
            row = ChartRow.model_validate(obj) if kind == 'chart' else TianjiRow.model_validate(obj)
        except Exception as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
        batch.append(row)
        if len(batch) >= batch_size:
            await flush(repo, kind, batch)
            count += len(batch)
            batch.clear()
    if batch:
        await flush(repo, kind, batch)
        count += len(batch)
    await repo.pool.execute("INSERT INTO import_run(source_path,source_sha256,source_kind,row_count) VALUES($1,$2,$3,$4) ON CONFLICT(source_sha256) DO NOTHING", str(path), sha, kind, count)
    print(f"{path.name}: {count}", flush=True)
    return count


async def flush(repo, kind, batch):
    if kind == 'chart':
        await chart_batch(repo, batch)
    else:
        raise ValueError("Tianji imports require the complete ordered corpus; use import_corpus")


async def run(args):
    import os
    repo = await Repository.connect(os.environ['DATABASE_URL'])
    try:
        await repo.schema()
        paths = sorted(p for p in Path(args.path).glob('year-*.jsonl.zst') if 2000 <= int(p.name[5:9]) <= 2026) if args.kind == 'chart' and Path(args.path).is_dir() else [Path(args.path)]
        for path in paths:
            await import_file(repo, path, args.kind, args.batch_size)
    finally:
        await repo.pool.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=['chart', 'tianji'])
    parser.add_argument('path')
    parser.add_argument('--batch-size', type=int, default=100)
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
