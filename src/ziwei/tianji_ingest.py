"""Import an entire ordered JSONL corpus, keeping one active PG retrieval table."""
import json
from .config import Settings
from .zhipu import Zhipu
from .tianji_chunks import build_chunks, sha

async def import_corpus(repo, path):
    settings = Settings()
    if settings.zhipu_embedding_dimensions != 1024:
        raise ValueError('Expected 1024 embedding dimensions')
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not records:
        raise ValueError('Cannot replace corpus with empty input')
    stored = await repo.pool.fetch('SELECT chunk_id,content_hash,model,embedding::text,sources FROM tianji_embedding')
    existing = {row['chunk_id']:dict(row) for row in stored}
    def identity(row):
        return json.dumps([row.get(key) or '' for key in ('book','h2','h3','quote','bvid','part','t_hms')],ensure_ascii=False)
    original_ids = {}
    for row in stored:
        sources = json.loads(row['sources']) if isinstance(row['sources'],str) else row['sources']
        for source in sources:
            if source.get('original_id'):
                original_ids[identity(source)] = source['original_id']
    records = [row | {'original_id': row.get('original_id') or original_ids.get(identity(row)) or (int(sha('source:'+identity(row))[:12],16)+1000000000)} for row in records]
    chunks, sections = build_chunks(records)
    zhipu = Zhipu(settings)
    try:
        pending = []
        for row in chunks:
            old = existing.get(row['chunk_id'])
            if old and old['content_hash']==row['content_hash'] and old['model']==settings.zhipu_embedding_model and old['embedding'] is not None:
                row['embedding'] = old['embedding']
            else:
                pending.append(row)
        for offset in range(0,len(pending),32):
            batch = pending[offset:offset+32]
            for row, vector in zip(batch,await zhipu.embed([row['tianji_chunk'] for row in batch])):
                row['embedding'] = json.dumps(vector)
        keys = ['id','chunk_id','section_id','book','h2','h3','tianji_chunk','body','chunk_index','chunk_total','body_start','body_end','sources','bvid','part','section','t_hms','note','model','content_hash','embedding']
        sql = 'INSERT INTO tianji_embedding ('+','.join(keys)+') VALUES('+','.join('$'+str(i)+('::jsonb' if key=='sources' else '::vector(1024)' if key=='embedding' else '') for i,key in enumerate(keys,1))+') ON CONFLICT(id) DO UPDATE SET '+','.join(f'{key}=excluded.{key}' for key in keys if key!='id')
        values=[]
        for row in chunks:
            row = row | {'model':settings.zhipu_embedding_model,'sources':json.dumps(row['sources'],ensure_ascii=False)}
            values.append(tuple(row[key] for key in keys))
        async with repo.pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(sql,values)
                await conn.execute('DELETE FROM tianji_embedding WHERE NOT(id=ANY($1::bigint[]))',[row['id'] for row in chunks])
        from .search import Search
        search = Search(settings)
        try:
            await search.rebuild(repo)
            response = await search.client.post('/tianji-chunks-v1/_delete_by_query?refresh=true',json={'query':{'bool':{'must_not':[{'ids':{'values':[str(row['id']) for row in chunks]}}]}}})
            response.raise_for_status()
        finally:
            await search.close()
        return len(records)
    finally:
        await zhipu.close()
