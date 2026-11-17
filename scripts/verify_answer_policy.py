"""Exercise real answer routing and rerank filtering through Nginx."""
import asyncio
import json
import os
from uuid import UUID, uuid4

import asyncpg
import httpx


async def main():
    name='policycheck_'+uuid4().hex[:12];password=uuid4().hex
    db=await asyncpg.connect(os.environ['DATABASE_URL'])
    try:
        async with httpx.AsyncClient(base_url='http://127.0.0.1',timeout=240) as client:
            for _ in range(20):
                try:
                    if (await client.get('/api/health')).status_code==200: break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(.5)
            r=await client.post('/api/auth/register',json={'username':name,'password':password,'confirm_password':password});r.raise_for_status()
            r=await client.post('/api/auth/login',json={'account':name,'password':password});r.raise_for_status()
            headers={'Authorization':'Bearer '+r.json()['access_token']}
            r=await client.post('/api/sessions',headers=headers,json={'chart_key':'2002-01-25-4-male','chart_name':'策略测试'});r.raise_for_status();sid=r.json()['id']
            for category,question in [('domain','我的事业高峰是在什么时候？请简洁回答。'),('unrelated','RAG的原理是什么？'),('casual','你是谁？'),('casual','今天天气怎么样？')]:
                rid=str(uuid4())
                r=await client.post(f'/api/sessions/{sid}/messages',headers=headers,json={'client_request_id':rid,'message':question});r.raise_for_status()
                events=[];final=None;event=''
                async with client.stream('GET',f'/api/sessions/{sid}/events?request_id={rid}',headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith('event: '): event=line[7:]
                        elif line.startswith('data: '):
                            data=json.loads(line[6:]);events.append(event)
                            if event=='error': raise AssertionError(data['error'])
                            if event=='message_end': final=data
                assert final and final['answer']
                if category!='domain': assert 'tool_start' not in events,events
                if category=='unrelated': assert '解读范围' in final['answer'] and 'answer_delta' not in events
                if category=='domain':
                    assert not any(label in final['answer'] for label in ['天纪原话','我的解读（非原话）','边界说明'])
                    rows=await db.fetch("SELECT content FROM chat_message WHERE session_id=$1 AND request_id=$2 AND role='tool'",UUID(sid),UUID(rid))
                    scores=[]
                    for row in rows:
                        content=json.loads(row['content']) if isinstance(row['content'],str) else row['content']
                        for quote in content.get('result',{}).get('quotes',[]):
                            assert quote['rerank_score']>.5
                            scores.append(quote['rerank_score'])
                    print('Qualified rerank scores:',scores,flush=True)
                print('PASS',category,'question:',question,'answer:',final['answer'][:700],flush=True)
            print('All policy cases passed',flush=True)
    finally:
        await db.execute('DELETE FROM auth_user WHERE username=$1',name)
        await db.execute('DELETE FROM auth_login_attempt WHERE account_key=$1',name)
        await db.close()
        print('Disposable account cleaned',flush=True)


if __name__=='__main__':
    asyncio.run(main())
