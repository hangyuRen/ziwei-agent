"""Real two-turn streaming check through Nginx, with disposable account cleanup."""
import asyncio
import json
import os
import time
from collections import Counter
from uuid import uuid4

import asyncpg
import httpx


async def main():
    name='streamcheck_'+uuid4().hex[:12];password=uuid4().hex
    db=await asyncpg.connect(os.environ['DATABASE_URL'])
    try:
        async with httpx.AsyncClient(base_url='http://127.0.0.1',timeout=240) as client:
            for _ in range(20):
                try:
                    ready=await client.get('/api/health')
                    if ready.status_code==200: break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.5)
            r=await client.post('/api/auth/register',json={'username':name,'password':password,'confirm_password':password});r.raise_for_status()
            r=await client.post('/api/auth/login',json={'account':name,'password':password});r.raise_for_status()
            headers={'Authorization':'Bearer '+r.json()['access_token']}
            r=await client.post('/api/sessions',headers=headers,json={'chart_key':'2002-01-25-4-male','chart_name':'流式测试'});r.raise_for_status();sid=r.json()['id']
            for turn,question in enumerate(['结合命盘，用150字分析我的性格。','接着用100字总结刚才分析中的行动建议。'],1):
                rid=str(uuid4());started=time.monotonic()
                r=await client.post(f'/api/sessions/{sid}/messages',headers=headers,json={'client_request_id':rid,'message':question});r.raise_for_status()
                counts=Counter();first={};last_id=0;event='';done=False;final={}
                async with client.stream('GET',f'/api/sessions/{sid}/events?request_id={rid}',headers=headers) as response:
                    response.raise_for_status()
                    assert response.headers['content-type'].startswith('text/event-stream')
                    async for line in response.aiter_lines():
                        if line.startswith('id: '): last_id=int(line[4:])
                        elif line.startswith('event: '): event=line[7:]
                        elif line.startswith('data: '):
                            data=json.loads(line[6:]);counts[event]+=1
                            if event not in first:
                                first[event]=round(time.monotonic()-started,2)
                                print('turn',turn,'first',event,'at',first[event],'s',flush=True)
                            if event=='error': raise AssertionError(data['error'])
                            if event=='message_end': final=data;done=True
                assert done and counts['answer_delta']>0,counts
                assert final['answer']
                if final['reasoning']:
                    assert counts['reasoning_delta']>0
                assert first.get('reasoning_delta',0)<=first['reasoning_end']<=first['answer_delta']<=first['message_end']
                messages=(await client.get(f'/api/sessions/{sid}/messages',headers=headers)).json()['items']
                assert len(messages)==turn*2 and messages[-1]['content']['reasoning']==final['reasoning']
                nav=(await client.get(f'/api/sessions/{sid}/timeline',headers=headers)).json()['items']
                assert len(nav)==turn and all(x['role']=='user' for x in nav)
                replay=await client.get(f'/api/sessions/{sid}/events?request_id={rid}&after_seq={last_id-1}',headers=headers)
                assert 'event: message_end' in replay.text and 'event: reasoning_delta' not in replay.text
                print('PASS turn',turn,dict(counts),'answer chars',len(final['answer']),'reasoning chars',len(final['reasoning']),flush=True)
    finally:
        await db.execute('DELETE FROM auth_user WHERE username=$1',name)
        await db.execute('DELETE FROM auth_login_attempt WHERE account_key=$1',name)
        await db.close()
        print('Disposable account cleaned',flush=True)


if __name__=='__main__':
    asyncio.run(main())
