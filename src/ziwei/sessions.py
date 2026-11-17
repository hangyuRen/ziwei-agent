"""多用户会话、消息顺序与历史分页的 PostgreSQL 操作。"""
import base64
import json
from datetime import datetime
from uuid import UUID, uuid4

import regex
from fastapi import HTTPException


def as_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, TypeError):
        raise HTTPException(404, '会话不存在')


def as_json(value):
    return json.loads(value) if isinstance(value, str) else value


def session_public(row):
    return {key: row[key] for key in ('id','title','chart_key','chart_name','last_seq','last_interaction_at','created_at')} | {
        'input_birth': as_json(row.get('chart_input_birth'))}


def message_public(row):
    return {'id': row['id'], 'seq': row['seq'], 'role': row['role'],
            'content': as_json(row['content']), 'status': row['status'],
            'request_id': row['request_id'], 'created_at': row['created_at']}


def message_internal(row):
    return message_public(row) | {'tool_call_id': row['tool_call_id']}


class SessionStore:
    def __init__(self, repo):
        self.repo = repo

    async def create(self, user_id: int, chart_key: str | None = None, chart_name: str | None = None,
                     input_birth: dict | None = None):
        if chart_key and not await self.repo.pool.fetchval('SELECT 1 FROM chart WHERE chart_key=$1', chart_key):
            raise HTTPException(404, '找不到完全匹配的命盘')
        sid = uuid4()
        async with self.repo.pool.acquire() as conn:
            async with conn.transaction():
                if input_birth is None and chart_key and chart_name:
                    saved = await conn.fetchrow('''SELECT input_birth FROM saved_chart
                        WHERE user_id=$1 AND chart_key=$2 AND name=$3''', user_id, chart_key, chart_name)
                    if saved:
                        input_birth = as_json(saved['input_birth'])
                row = await conn.fetchrow('''INSERT INTO chat_session(id,user_id,chart_key,chart_name,chart_input_birth)
                  VALUES($1,$2,$3,$4,$5::jsonb) RETURNING *''', sid, user_id, chart_key, chart_name,
                  json.dumps(input_birth) if input_birth is not None else None)
                await conn.execute('''INSERT INTO session_summary(session_id,summary)
                  VALUES($1,'{}'::jsonb)''', sid)
        return session_public(row)

    async def owned(self, user_id: int, sid: str, conn=None):
        db = conn or self.repo.pool
        row = await db.fetchrow('''SELECT * FROM chat_session
          WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL''', as_uuid(sid), user_id)
        if not row:
            raise HTTPException(404, '会话不存在')
        return dict(row)

    async def list(self, user_id: int, limit: int = 20, cursor: str | None = None):
        if not 1 <= limit <= 50:
            raise HTTPException(422, 'limit 须为 1–50')
        time, uid = None, None
        if cursor:
            try:
                value = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
                time, uid = datetime.fromisoformat(value['t']), UUID(value['id'])
            except Exception:
                raise HTTPException(422, '无效分页游标')
        rows = await self.repo.pool.fetch('''SELECT * FROM chat_session
          WHERE user_id=$1 AND deleted_at IS NULL
            AND ($2::timestamptz IS NULL OR (last_interaction_at,id)<($2::timestamptz,$3::uuid))
          ORDER BY last_interaction_at DESC,id DESC LIMIT $4''', user_id, time, uid, limit + 1)
        has_more = len(rows) > limit
        items = [session_public(r) for r in rows[:limit]]
        next_cursor = None
        if has_more:
            last = rows[limit - 1]
            data = json.dumps({'t': last['last_interaction_at'].isoformat(), 'id': str(last['id'])})
            next_cursor = base64.urlsafe_b64encode(data.encode()).decode().rstrip('=')
        return {'items': items, 'next_cursor': next_cursor, 'has_more': has_more}

    async def rename(self, user_id: int, sid: str, title: str):
        row = await self.repo.pool.fetchrow('''UPDATE chat_session SET title=$3
          WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL RETURNING *''', as_uuid(sid), user_id, title)
        if not row:
            raise HTTPException(404, '会话不存在')
        return session_public(row)

    async def delete(self, user_id: int, sid: str):
        row = await self.repo.pool.fetchval('''UPDATE chat_session SET deleted_at=now()
          WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL RETURNING id''', as_uuid(sid), user_id)
        if not row:
            raise HTTPException(404, '会话不存在')
        return {'deleted': True}

    async def append(self, user_id: int, sid: str, role: str, content: dict,
                     request_id: UUID | None = None, status: str = 'complete',
                     tool_call_id: str | None = None):
        async with self.repo.pool.acquire() as conn:
            async with conn.transaction():
                session = await conn.fetchrow('''SELECT * FROM chat_session WHERE id=$1
                  AND user_id=$2 AND deleted_at IS NULL FOR UPDATE''', as_uuid(sid), user_id)
                if not session:
                    raise HTTPException(404, '会话不存在')
                if role == 'user' and request_id:
                    prior = await conn.fetchrow('''SELECT * FROM chat_message WHERE session_id=$1
                      AND role='user' AND request_id=$2''', as_uuid(sid), request_id)
                    if prior:
                        return message_public(prior), False
                    pending = await conn.fetchval('''SELECT 1 FROM chat_message WHERE session_id=$1
                      AND role='user' AND status='pending' LIMIT 1''', as_uuid(sid))
                    if pending:
                        raise HTTPException(409, '该会话正在生成回答，请稍后重试')
                seq = session['last_seq'] + 1
                row = await conn.fetchrow('''INSERT INTO chat_message
                  (id,session_id,seq,role,content,status,tool_call_id,request_id)
                  VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,$8) RETURNING *''',
                  uuid4(), as_uuid(sid), seq, role, json.dumps(content, ensure_ascii=False),
                  status, tool_call_id, request_id)
                if role == 'user' or role == 'assistant' and content.get('kind') == 'final':
                    await conn.execute('''UPDATE chat_session SET last_seq=$2,
                      last_interaction_at=now() WHERE id=$1''', as_uuid(sid), seq)
                else:
                    await conn.execute('UPDATE chat_session SET last_seq=$2 WHERE id=$1', as_uuid(sid), seq)
                return message_public(row), True

    async def request_status(self, user_id: int, sid: str, request_id: UUID):
        await self.owned(user_id, sid)
        user = await self.repo.pool.fetchrow('''SELECT * FROM chat_message WHERE session_id=$1
          AND request_id=$2 AND role='user' ''', as_uuid(sid), request_id)
        if not user:
            raise HTTPException(404, '请求不存在')
        final = await self.repo.pool.fetchrow('''SELECT * FROM chat_message WHERE session_id=$1
          AND request_id=$2 AND role='assistant' AND content->>'kind'='final'
          ORDER BY seq DESC LIMIT 1''', as_uuid(sid), request_id)
        error = await self.repo.pool.fetchrow('''SELECT seq,content->>'message' AS message FROM chat_message
          WHERE session_id=$1 AND request_id=$2 AND role='assistant'
          AND content->>'kind'='error' ORDER BY seq DESC LIMIT 1''', as_uuid(sid), request_id)
        return {'request_id': request_id, 'status': user['status'],
                'user_seq': user['seq'], 'answer': as_json(final['content'])['text'] if final else None,
                'answer_seq': final['seq'] if final else None,
                'error': error['message'] if error and user['status'] == 'failed' else None,
                'error_seq': error['seq'] if error and user['status'] == 'failed' else None}

    async def session_sources(self, user_id: int, sid: str, ids):
        await self.owned(user_id, sid)
        if not ids:
            return []
        rows = await self.repo.pool.fetch('''SELECT r.raw || jsonb_build_object('id',coalesce(r.raw->'original_id',r.raw->'id')) AS quote FROM chat_message m
          CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(m.content->'result'->'quotes')='array'
              THEN m.content->'result'->'quotes' ELSE '[]'::jsonb END) AS q(quote)
          CROSS JOIN LATERAL jsonb_array_elements(jsonb_build_array(q.quote) || coalesce(q.quote->'sources','[]'::jsonb)) AS r(raw)
          WHERE m.session_id=$1 AND m.role='tool' AND coalesce(r.raw->>'original_id',r.raw->>'id')=ANY($2::text[])''',
          as_uuid(sid), [str(item) for item in ids])
        return [as_json(row['quote']) for row in rows]

    async def session_sources_by_locations(self, user_id: int, sid: str, locations):
        await self.owned(user_id, sid)
        if not locations:
            return []
        parts = sorted({str(part) for part, _ in locations})
        times = sorted({time for _, time in locations})
        rows = await self.repo.pool.fetch('''SELECT r.raw || jsonb_build_object('id',coalesce(r.raw->'original_id',r.raw->'id')) AS quote FROM chat_message m
          CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(m.content->'result'->'quotes')='array'
              THEN m.content->'result'->'quotes' ELSE '[]'::jsonb END) AS q(quote)
          CROSS JOIN LATERAL jsonb_array_elements(jsonb_build_array(q.quote) || coalesce(q.quote->'sources','[]'::jsonb)) AS r(raw)
          WHERE m.session_id=$1 AND m.role='tool'
            AND r.raw->>'part'=ANY($2::text[])
            AND r.raw->>'t_hms'=ANY($3::text[])''',
          as_uuid(sid), parts, times)
        return [source for row in rows if (source := as_json(row['quote']))
                and (int(source['part']), source['t_hms']) in locations]

    async def with_source_refs(self, user_id: int, sid: str, items):
        missing = {int(source_id) for item in items if item['role'] == 'assistant'
                   for source_id in item['content'].get('source_ids', [])
                   if not item['content'].get('source_refs')}
        refs = {int(row['id']): row for row in await self.session_sources(user_id, sid, missing)} if missing else {}
        for item in items:
            content = item['content']
            if item['role'] == 'assistant' and not content.get('source_refs'):
                content['source_refs'] = [{key: refs[int(source_id)].get(key)
                    for key in ('id', 'bvid', 'part', 't_hms')}
                    for source_id in content.get('source_ids', []) if int(source_id) in refs]
        return items

    async def set_request_status(self, sid: str, request_id: UUID, status: str):
        await self.repo.pool.execute('''UPDATE chat_message SET status=$3 WHERE session_id=$1
          AND request_id=$2 AND role='user' ''', as_uuid(sid), request_id, status)

    async def retry_failed(self, user_id: int, sid: str, request_id: UUID):
        async with self.repo.pool.acquire() as conn:
            async with conn.transaction():
                session = await conn.fetchrow('''SELECT 1 FROM chat_session WHERE id=$1 AND user_id=$2
                  AND deleted_at IS NULL FOR UPDATE''', as_uuid(sid), user_id)
                if not session:
                    raise HTTPException(404, '会话不存在')
                pending = await conn.fetchval('''SELECT 1 FROM chat_message WHERE session_id=$1
                  AND role='user' AND status='pending' LIMIT 1''', as_uuid(sid))
                if pending:
                    raise HTTPException(409, '该会话正在生成回答，请稍后重试')
                row = await conn.fetchrow('''UPDATE chat_message SET status='pending'
                  WHERE session_id=$1 AND request_id=$2 AND role='user' AND status='failed'
                  RETURNING *''', as_uuid(sid), request_id)
        if not row:
            raise HTTPException(409, '只有失败的请求可以重试')
        return message_public(row)

    async def visible(self, user_id: int, sid: str, before_seq: int | None = None, limit: int = 10):
        await self.owned(user_id, sid)
        if not 1 <= limit <= 50:
            raise HTTPException(422, 'limit 须为 1–50')
        rows = await self.repo.pool.fetch('''SELECT * FROM chat_message WHERE session_id=$1
          AND ($2::bigint IS NULL OR seq<$2)
          AND (role='user' OR (role='assistant' AND content->>'kind'='final'))
          ORDER BY seq DESC LIMIT $3''', as_uuid(sid), before_seq, limit + 1)
        has_more = len(rows) > limit
        items = [message_public(r) for r in reversed(rows[:limit])]
        return {'items': await self.with_source_refs(user_id, sid, items), 'next_before_seq': items[0]['seq'] if has_more else None,
                'has_more': has_more}

    async def around(self, user_id: int, sid: str, seq: int, before: int = 5, after: int = 5):
        await self.owned(user_id, sid)
        if not 0 <= before <= 20 or not 0 <= after <= 20:
            raise HTTPException(422, '窗口过大')
        target = await self.repo.pool.fetchrow('''SELECT * FROM chat_message WHERE session_id=$1
          AND seq=$2 AND (role='user' OR (role='assistant' AND content->>'kind'='final'))''',
          as_uuid(sid), seq)
        if not target:
            raise HTTPException(404, '消息不存在')
        visibility = "(role='user' OR (role='assistant' AND content->>'kind'='final'))"
        older = await self.repo.pool.fetch(f'''SELECT * FROM chat_message WHERE session_id=$1
          AND seq<$2 AND {visibility} ORDER BY seq DESC LIMIT $3''', as_uuid(sid), seq, before)
        newer = await self.repo.pool.fetch(f'''SELECT * FROM chat_message WHERE session_id=$1
          AND seq>$2 AND {visibility} ORDER BY seq ASC LIMIT $3''', as_uuid(sid), seq, after)
        items = [message_public(r) for r in [*reversed(older), target, *newer]]
        return {'items': await self.with_source_refs(user_id, sid, items), 'target_seq': seq}

    async def questions(self, user_id: int, sid: str, limit: int = 100, cursor: int = 0):
        await self.owned(user_id, sid)
        if not 1 <= limit <= 100 or cursor < 0:
            raise HTTPException(422, '无效分页参数')
        rows = await self.repo.pool.fetch('''SELECT seq,content FROM chat_message WHERE session_id=$1
          AND role='user' AND seq>$2 ORDER BY seq ASC LIMIT $3''', as_uuid(sid), cursor, limit + 1)
        has_more = len(rows) > limit
        items = []
        for row in rows[:limit]:
            text = as_json(row['content']).get('text') or '附件提问'
            chars = regex.findall(r'\X', text)
            items.append({'seq': row['seq'], 'preview': ''.join(chars[:10]) + ('…' if len(chars) > 10 else '')})
        return {'items': items, 'next_cursor': items[-1]['seq'] if has_more else None,
                'has_more': has_more}

    async def timeline(self, user_id: int, sid: str, limit: int = 100, cursor: int = 0):
        await self.owned(user_id, sid)
        if not 1 <= limit <= 100 or cursor < 0:
            raise HTTPException(422, '无效分页参数')
        rows = await self.repo.pool.fetch('''SELECT seq,role,content FROM chat_message
          WHERE session_id=$1 AND seq>$2
            AND role='user'
          ORDER BY seq ASC LIMIT $3''', as_uuid(sid), cursor, limit + 1)
        has_more = len(rows) > limit
        items = []
        for row in rows[:limit]:
            content = as_json(row['content'])
            text = ' '.join((content.get('text') or '').split())
            chars = regex.findall(r'\X', text)
            items.append({'seq': row['seq'], 'role': row['role'],
                          'preview': ''.join(chars[:18]) + ('…' if len(chars) > 18 else '')})
        return {'items': items, 'next_cursor': items[-1]['seq'] if has_more else None,
                'has_more': has_more}

    async def context_tail(self, user_id: int, sid: str, after_seq: int):
        await self.owned(user_id, sid)
        rows = await self.repo.pool.fetch('''SELECT * FROM chat_message WHERE session_id=$1
          AND seq>$2 AND content->>'kind' IS DISTINCT FROM 'stream'
          ORDER BY seq ASC''', as_uuid(sid), after_seq)
        return [message_internal(r) for r in rows]

    async def summary(self, user_id: int, sid: str):
        await self.owned(user_id, sid)
        row = await self.repo.pool.fetchrow('SELECT * FROM session_summary WHERE session_id=$1', as_uuid(sid))
        return {'summary': as_json(row['summary']), 'covered_seq': row['covered_seq'],
                'revision': row['revision']} if row else {'summary': {}, 'covered_seq': 0, 'revision': 0}

    async def cas_summary(self, user_id: int, sid: str, revision: int, covered_seq: int,
                          cut_seq: int, summary: dict):
        await self.owned(user_id, sid)
        result = await self.repo.pool.execute('''UPDATE session_summary SET summary=$5::jsonb,
          covered_seq=$4,revision=revision+1,updated_at=now() WHERE session_id=$1
          AND revision=$2 AND covered_seq=$3 AND $4>$3''', as_uuid(sid), revision,
          covered_seq, cut_seq, json.dumps(summary, ensure_ascii=False))
        return result.endswith(' 1')

    async def request_messages(self, user_id: int, sid: str, request_id: UUID, after_seq: int = 0):
        await self.owned(user_id, sid)
        rows = await self.repo.pool.fetch('''SELECT * FROM chat_message WHERE session_id=$1
          AND request_id=$2 AND seq>$3 ORDER BY seq ASC''', as_uuid(sid), request_id, after_seq)
        return [message_internal(r) for r in rows]
