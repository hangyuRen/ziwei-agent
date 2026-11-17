"""对正在运行的服务做一次真实模型问答烟测，结束后清理临时用户。"""
import asyncio
import json
from uuid import UUID, uuid4

import httpx

from ziwei.config import Settings
from ziwei.db import Repository


async def main():
    name = f'live_verify_{uuid4().hex[:12]}'
    repo = await Repository.connect(Settings().database_url)
    try:
        async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', timeout=30) as client:
            response = await client.post('/api/auth/register', json={
                'username': name, 'password': 'temporary-test-password-123',
                'confirm_password': 'temporary-test-password-123'})
            response.raise_for_status()
            response = await client.post('/api/auth/login', json={
                'account': name, 'password': 'temporary-test-password-123'})
            response.raise_for_status()
            headers = {'Authorization': f"Bearer {response.json()['access_token']}"}
            response = await client.post('/api/sessions', headers=headers, json={'chart_key': None})
            response.raise_for_status()
            sid = response.json()['id']
            request_id = str(uuid4())
            response = await client.post(f'/api/sessions/{sid}/messages', headers=headers,
                json={'client_request_id': request_id, 'message': '倪师如何解释化忌？'})
            response.raise_for_status()
            for _ in range(120):
                response = await client.get(f'/api/sessions/{sid}/requests/{request_id}', headers=headers)
                response.raise_for_status()
                status = response.json()
                if status['status'] in ('complete', 'failed'):
                    break
                await asyncio.sleep(1)
            else:
                raise TimeoutError('真实问答未在 120 秒内完成')
            rows = await repo.pool.fetch("""SELECT content FROM chat_message
                WHERE session_id=$1 AND request_id=$2 AND role='tool' ORDER BY seq""",
                UUID(sid), UUID(request_id))
            results = [json.loads(row['content']) if isinstance(row['content'], str) else row['content']
                       for row in rows]
            quotes = [q for result in results for q in result.get('result', {}).get('quotes', [])]
            if status['status'] != 'complete' or not status['answer'] or len(quotes) < 5:
                raise AssertionError({'status': status['status'], 'tool_results': results})
            print('PASS: real chat completed; retrieved sources:', len(quotes))
    finally:
        await repo.pool.execute('DELETE FROM auth_user WHERE username=$1', name)
        await repo.pool.close()


if __name__ == '__main__':
    asyncio.run(main())
