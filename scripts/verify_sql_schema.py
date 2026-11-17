"""Exercise fresh/legacy schemas inside a disposable, rolled-back transaction.

Uses DATABASE_URL; never initializes or drops tables in the public schema.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import date
import json
import os
from uuid import uuid4

import asyncpg

from ziwei.db import Repository


TABLES = {
    'chart','import_run','user_memory','auth_user','auth_login_attempt',
    'chat_session','chat_message','session_summary','saved_chart','tianji_embedding',
}


class SingleConnectionPool:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


async def main():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    namespace = 'sqlcheck_'+uuid4().hex[:16]
    transaction = conn.transaction()
    await transaction.start()
    try:
        await conn.execute(f'CREATE SCHEMA "{namespace}"')
        await conn.execute(f'SET LOCAL search_path TO "{namespace}", public')
        repo = Repository(SingleConnectionPool(conn))
        await repo.schema()
        await repo.schema()  # Repeated initialization must be safe.
        actual = {r['tablename'] for r in await conn.fetch(
            'SELECT tablename FROM pg_tables WHERE schemaname=$1', namespace)}
        assert actual==TABLES, actual ^ TABLES
        views = {r['viewname'] for r in await conn.fetch(
            'SELECT viewname FROM pg_views WHERE schemaname=$1', namespace)}
        assert views=={'chart_section'}
        outside = await conn.fetchval('''SELECT count(*) FROM pg_constraint c
            JOIN pg_class source ON source.oid=c.conrelid
            JOIN pg_class target ON target.oid=c.confrelid
            JOIN pg_namespace sn ON sn.oid=source.relnamespace
            JOIN pg_namespace tn ON tn.oid=target.relnamespace
            WHERE c.contype='f' AND sn.nspname=$1 AND tn.nspname<>$1''', namespace)
        assert outside==0  # Fixtures cannot reference live account/chart tables.

        owner = await conn.fetchval('''INSERT INTO auth_user(username,password_hash)
            VALUES('schema-check','test-only') RETURNING id''')
        key = '2000-01-01-0-male'
        await conn.execute('''INSERT INTO chart(chart_key,birth_year,birth_month,birth_day,birth_hour,gender,content)
            VALUES($1,2000,1,1,0,'male','{}'::jsonb)''', key)
        for name,updated in [('original','2026-01-01'),('modified-later','2026-01-03')]:
            await conn.execute('''INSERT INTO saved_chart(user_id,chart_key,name,input_birth,updated_at)
                VALUES($1,$2,$3,$4::jsonb,$5::date)''',owner,key,name,
                json.dumps({'name':name,'clock_hour':0,'minute':5}),
                date.fromisoformat(updated))
        # Emulate an existing database from before birth-context snapshots existed.
        await conn.execute('ALTER TABLE chat_session DROP COLUMN chart_input_birth')
        original,changed = uuid4(),uuid4()
        for sid,name in [(original,'original'),(changed,'modified-later')]:
            await conn.execute('''INSERT INTO chat_session(id,user_id,chart_key,chart_name,created_at)
                VALUES($1,$2,$3,$4,'2026-01-02'::timestamptz)''',sid,owner,key,name)
        await repo.schema()
        raw = await conn.fetchval('SELECT chart_input_birth FROM chat_session WHERE id=$1', original)
        assert json.loads(raw)['minute']==5
        assert await conn.fetchval('SELECT chart_input_birth FROM chat_session WHERE id=$1',changed) is None
        # The oldest schema also lacked chart_name; it must upgrade without failure.
        await conn.execute('ALTER TABLE chat_session DROP COLUMN chart_name')
        await repo.schema()
        columns = {r['column_name'] for r in await conn.fetch('''SELECT column_name
            FROM information_schema.columns WHERE table_schema=$1 AND table_name='chat_session' ''',namespace)}
        assert {'chart_name','chart_input_birth'}.issubset(columns)
    finally:
        await transaction.rollback()
        try:
            assert not await conn.fetchval('SELECT 1 FROM pg_namespace WHERE nspname=$1',namespace)
        finally:
            await conn.close()
    print('PASS: 10 current tables, 1 view, repeat initialization, legacy column upgrades, safe birth-context backfill; isolated test schema rolled back')


if __name__=='__main__':
    asyncio.run(main())
