"""Temporary end-to-end checks against the configured remote PostgreSQL."""
import asyncio
import os
from dataclasses import replace
from uuid import uuid4

import httpx

from ziwei import api
from ziwei.config import Settings


class FakeLLM:
    async def chat(self, messages, tools=None, json_mode=False):
        if json_mode and '话题分类' in messages[0]['content']:
            return {'content': '{"category":"domain"}'}
        return {'content': '测试回答'}
    async def stream_answer(self, messages):
        yield "reasoning_delta", "核对测试资料"
        yield "answer_delta", "测试回答"
    async def close(self):
        pass


class FakeSearch:
    async def search(self, query, llm, repo, limit=5, filters=None):
        return []


async def main():
    api.settings = replace(Settings(), llm_api_key='local-test-placeholder', llm_model='fake-model')
    names = [f'verify_{uuid4().hex[:12]}' for _ in range(2)]
    chart_key = '2000-01-01-0-male'
    try:
        async with api.lifespan(api.app):
            api.app.state.runtime.llm = FakeLLM()
            api.app.state.runtime.search = FakeSearch()
            transport = httpx.ASGITransport(app=api.app)
            async with httpx.AsyncClient(transport=transport, base_url='http://test') as c:
                r = await c.get('/api/charts/' + chart_key)
                assert r.status_code == 200, r.text
                assert (await c.get('/api/sessions')).status_code == 401
                tokens = []
                for name in names:
                    r = await c.post('/api/auth/register', json={'username': name, 'password': 'test-password-123', 'confirm_password': 'test-password-123'})
                    assert r.status_code == 201, r.text
                    r = await c.post('/api/auth/login', json={'account': name, 'password': 'test-password-123'})
                    assert r.status_code == 200, r.text
                    tokens.append(r.json()['access_token'])
                h1, h2 = ({'Authorization': 'Bearer ' + t} for t in tokens)
                r = await c.post('/api/sessions', headers=h1, json={'chart_key': chart_key})
                assert r.status_code == 201, r.text
                sid = r.json()['id']
                assert (await c.get(f'/api/sessions/{sid}', headers=h2)).status_code == 404
                assert (await c.get(f'/api/sessions/{sid}/messages', headers=h2)).status_code == 404
                rid = str(uuid4())
                body = {'client_request_id': rid, 'message': '你好'}
                r = await c.post(f'/api/sessions/{sid}/messages', headers=h1, json=body)
                assert r.status_code == 202, r.text
                assert (await c.post(f'/api/sessions/{sid}/messages', headers=h1, json=body)).status_code == 202
                for _ in range(30):
                    status = (await c.get(f'/api/sessions/{sid}/requests/{rid}', headers=h1)).json()
                    if status['status'] == 'complete':
                        break
                    await asyncio.sleep(0.1)
                if status['answer'] != '测试回答':
                    user_id = (await c.get('/api/auth/me', headers=h1)).json()['id']
                    raise AssertionError((status, await api.app.state.store.request_messages(user_id, sid, rid)))
                hist = (await c.get(f'/api/sessions/{sid}/messages', headers=h1)).json()
                assert [x['role'] for x in hist['items']] == ['user', 'assistant'], hist
                assert (await c.get(f'/api/sessions/{sid}/questions', headers=h1)).json()['items'][0]['preview'] == '你好'
                events = (await c.get(f'/api/sessions/{sid}/events?request_id={rid}', headers=h1)).text
                assert 'event: message_end' in events and '测试回答' in events
                assert (await c.get(f'/api/sessions/{sid}/events?request_id={rid}', headers=h2)).status_code == 404
                other = await c.post('/api/sessions', headers=h1, json={'chart_key': chart_key})
                assert other.status_code == 201
                other_sid = other.json()['id']
                assert (await c.get(f'/api/sessions/{other_sid}/messages', headers=h1)).json()['items'] == []
                assert (await c.patch(f'/api/sessions/{sid}', headers=h1, json={'title': '测试会话'})).json()['title'] == '测试会话'
                for i in range(6):
                    request_id = uuid4()
                    await api.app.state.store.append((await c.get('/api/auth/me', headers=h1)).json()['id'], sid,
                        'user', {'v': 1, 'kind': 'text', 'text': f'问题{i}'}, request_id)
                    await api.app.state.store.append((await c.get('/api/auth/me', headers=h1)).json()['id'], sid,
                        'assistant', {'v': 1, 'kind': 'final', 'text': f'回答{i}'}, request_id)
                page = (await c.get(f'/api/sessions/{sid}/messages', headers=h1)).json()
                assert len(page['items']) == 10 and page['has_more']
                older = (await c.get(f"/api/sessions/{sid}/messages?before_seq={page['next_before_seq']}", headers=h1)).json()
                assert len(older['items']) == 4 and not older['has_more']
                assert older['items'][-1]['seq'] < page['items'][0]['seq']
                nav = (await c.get(f'/api/sessions/{sid}/questions', headers=h1)).json()['items']
                assert len(nav) == 7
                assert (await c.get(f"/api/sessions/{sid}/messages/around?seq={nav[0]['seq']}", headers=h1)).status_code == 200
                user_id = (await c.get('/api/auth/me', headers=h1)).json()['id']
                assert await api.app.state.store.cas_summary(user_id, sid, 0, 0, 2, {'schema_version': 1})
                assert not await api.app.state.store.cas_summary(user_id, sid, 0, 0, 4, {'schema_version': 1})
                assert (await c.delete(f'/api/sessions/{other_sid}', headers=h1)).status_code == 200
                assert (await c.get(f'/api/sessions/{other_sid}', headers=h1)).status_code == 404
                session = await api.app.state.store.owned(user_id, sid)
                try:
                    await api.app.state.runtime.tool('get_chart_section', {'chart_key': '2001-01-01-0-male', 'section_type': 'career'}, session)
                    assert False, 'cross-chart tool was allowed'
                except PermissionError:
                    pass
                await c.post('/api/auth/logout', headers=h1)
                assert (await c.get('/api/auth/me', headers=h1)).status_code == 401
                print('PASS: public chart, auth, isolation, idempotency, pagination, summary CAS, tool guard, SSE replay, logout')
    finally:
        if os.getenv('DATABASE_URL'):
            from ziwei.db import Repository
            repo = await Repository.connect(os.environ['DATABASE_URL'])
            try:
                await repo.pool.execute('DELETE FROM auth_user WHERE username=ANY($1::text[])', names)
                await repo.pool.execute('DELETE FROM auth_login_attempt WHERE account_key=ANY($1::text[])', names)
            finally:
                await repo.pool.close()


asyncio.run(main())
