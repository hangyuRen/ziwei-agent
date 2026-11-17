"""Re-embed changed chunk text in the single Tianji retrieval table."""
import asyncio
import json
from .config import Settings
from .db import Repository
from .zhipu import Zhipu
from .tianji_chunks import sha


def embedding_text(row):
    return row['tianji_chunk']


async def run(batch_size=32):
    settings = Settings()
    repo = await Repository.connect(settings.database_url)
    zhipu = Zhipu(settings)
    try:
        if settings.zhipu_embedding_dimensions != 1024:
            raise ValueError('Tianji embeddings must have 1024 dimensions')
        rows = await repo.pool.fetch('SELECT id,tianji_chunk,content_hash,model,embedding IS NULL AS missing FROM tianji_embedding ORDER BY id')
        changed = [row for row in rows if row['missing'] or row['model'] != settings.zhipu_embedding_model or row['content_hash'] != sha(row['tianji_chunk'])]
        for offset in range(0, len(changed), min(max(batch_size, 1), 64)):
            batch = changed[offset:offset + min(max(batch_size, 1), 64)]
            vectors = await zhipu.embed([embedding_text(row) for row in batch])
            await repo.pool.executemany('UPDATE tianji_embedding SET embedding=$2::vector(1024),model=$3,content_hash=$4,updated_at=now() WHERE id=$1',
                [(row['id'], json.dumps(vector), settings.zhipu_embedding_model, sha(row['tianji_chunk'])) for row, vector in zip(batch, vectors)])
        return len(rows)
    finally:
        await zhipu.close()
        await repo.pool.close()


if __name__ == '__main__':
    asyncio.run(run())
