import json
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg

from .models import Birth


class Repository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def connect(cls, url: str):
        if not url:
            raise RuntimeError("DATABASE_URL is required")
        return cls(await asyncpg.create_pool(url, min_size=1, max_size=10, command_timeout=60))

    async def schema(self):
        root = Path.cwd() if (Path.cwd() / 'sql' / 'schema.sql').exists() else Path(__file__).parents[2]
        sql_root = root / 'sql'
        scripts = [sql_root / 'schema.sql', sql_root / 'tianji_embedding.sql',
                   *sorted((sql_root / 'migrations').glob('*.sql'))]
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for script in scripts:
                    await conn.execute(script.read_text())

    @asynccontextmanager
    async def session_lock(self, sid: str):
        lock_id = int(UUID(sid)) & ((1 << 63) - 1)
        async with self.pool.acquire() as conn:
            await conn.execute('SELECT pg_advisory_lock($1::bigint)', lock_id)
            try:
                yield
            finally:
                await conn.execute('SELECT pg_advisory_unlock($1::bigint)', lock_id)

    async def chart(self, key: str):
        row = await self.pool.fetchrow("SELECT chart_key,birth_year,birth_month,birth_day,birth_hour,gender,content FROM chart WHERE chart_key=$1", key)
        return dict(row) | {'content': json.loads(row['content'])} if row else None

    async def section(self, key: str, section: str):
        return await self.pool.fetchval("SELECT content FROM chart_section WHERE chart_key=$1 AND section_type=$2", key, section)

    async def vector_search(self, vector: list[float], model: str, limit: int = 5,
                            filters: dict | None = None):
        filters = filters or {}
        args = [json.dumps(vector), model]
        clauses = ['e.model=$2', 'e.embedding IS NOT NULL']
        for key in ('book','h2','h3','section_id'):
            if key in filters:
                args.append(filters[key])
                clauses.append(f'e.{key}=${len(args)}')
        source_filter = {key:filters[key] for key in ('bvid','part','section') if key in filters}
        if source_filter:
            args.append(json.dumps([source_filter]))
            clauses.append(f'e.sources @> ${len(args)}::jsonb')
        args.append(min(max(limit,1),50))
        rows = await self.pool.fetch("""SELECT e.id,e.book,e.h2,e.h3,e.tianji_chunk AS quote,
            e.section,e.t_hms,e.note,e.bvid,e.part,e.chunk_id,e.section_id,
            e.chunk_index,e.chunk_total,e.body_start,e.body_end,e.sources
            FROM tianji_embedding e WHERE """ + ' AND '.join(clauses) +
            f' ORDER BY e.embedding <=> $1::vector(1024) LIMIT ${len(args)}', *args)
        return [dict(row) | {'sources':json.loads(row['sources']) if isinstance(row['sources'],str) else row['sources']} for row in rows]

    async def memories(self, owner: str):
        rows = await self.pool.fetch('SELECT memory_key,value,version FROM user_memory WHERE owner_id=$1 ORDER BY memory_key', owner)
        return [dict(row) for row in rows]

    async def put_memory(self, owner: str, key: str, value: str):
        row = await self.pool.fetchrow('''INSERT INTO user_memory(owner_id,memory_key,value)
        VALUES($1,$2,$3) ON CONFLICT(owner_id,memory_key)
        DO UPDATE SET value=excluded.value,version=user_memory.version+1,updated_at=now()
        RETURNING memory_key,value,version''', owner, key, value)
        return dict(row)

    async def delete_memory(self, owner: str, key: str):
        return (await self.pool.execute('DELETE FROM user_memory WHERE owner_id=$1 AND memory_key=$2', owner, key)).endswith(' 1')
