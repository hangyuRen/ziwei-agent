import asyncio
import os
from ziwei.db import Repository

async def main():
    repo = await Repository.connect(os.environ['DATABASE_URL'])
    try:
        await repo.schema()
        rows = await repo.pool.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('auth_user','chat_session','chat_message','session_summary') ORDER BY table_name")
        print('Migrated:', ', '.join(row['table_name'] for row in rows))
    finally:
        await repo.pool.close()

asyncio.run(main())
