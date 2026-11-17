"""Verify named chart persistence and ownership using disposable accounts."""
import asyncio
import os
from uuid import uuid4
import asyncpg
import httpx


async def main():
    users=[]
    conn=await asyncpg.connect(os.environ['DATABASE_URL'])
    try:
        async with httpx.AsyncClient(base_url='http://127.0.0.1', timeout=30) as c:
            headers=[]
            for _ in range(2):
                name='chartcheck_'+uuid4().hex[:12]
                users.append(name)
                password=uuid4().hex
                r=await c.post('/api/auth/register',json={'username':name,'password':password,'confirm_password':password})
                r.raise_for_status()
                r=await c.post('/api/auth/login',json={'account':name,'password':password});r.raise_for_status()
                headers.append({'Authorization':'Bearer '+r.json()['access_token']})
                c.cookies.clear()  # Keep anonymous and explicit Bearer checks independent.
            birth={'name':'测试命盘','calendar':'lunar','year':2001,'month':12,'day':13,
                   'clock_hour':8,'minute':5,'gender':'male'}
            r=await c.post('/api/saved-charts',json=birth,headers=headers[0]);r.raise_for_status();saved=r.json()
            assert saved['chart_key']=='2002-01-25-4-male',saved
            assert saved['name']=='测试命盘' and saved['input_birth']['minute']==5
            r=await c.post('/api/saved-charts',json=birth,headers=headers[0]);r.raise_for_status()
            assert r.json()['saved_chart_id']==saved['saved_chart_id']
            r=await c.get('/api/saved-charts',headers=headers[0]);r.raise_for_status()
            assert r.json()['total']==1 and r.json()['items'][0]['name']=='测试命盘'
            assert (await c.get('/api/saved-charts',headers=headers[1])).json()['total']==0
            assert (await c.get('/api/saved-charts')).status_code==401
            assert (await c.post('/api/saved-charts',json=birth|{'name':'   '},headers=headers[0])).status_code==422
            assert (await c.post('/api/charts/resolve',json=birth|{'minute':60})).status_code==422
            r=await c.post('/api/sessions',json={'chart_key':saved['chart_key'],'chart_name':'测试命盘'},headers=headers[0]);r.raise_for_status()
            sid=r.json()['id'];assert r.json()['chart_name']=='测试命盘'
            assert (await c.get('/api/sessions/'+sid,headers=headers[0])).json()['chart_name']=='测试命盘'
            chart_path='/api/saved-charts/'+str(saved['saved_chart_id'])
            for method,payload in [('PATCH',{'name':'越权修改'}),('DELETE',None)]:
                denied=await c.request(method,chart_path,json=payload,headers=headers[1])
                assert denied.status_code==404,(method,denied.status_code,denied.text)
                assert (await c.request(method,chart_path,json=payload)).status_code==401
            assert (await c.patch(chart_path,json={'name':'   '},headers=headers[0])).status_code==422
            assert (await c.patch(chart_path,json={'name':'长'*81},headers=headers[0])).status_code==422
            r=await c.patch(chart_path,json={'name':'  新命盘名称  '},headers=headers[0]);r.raise_for_status()
            assert r.json()['name']=='新命盘名称' and r.json()['input_birth']['name']=='新命盘名称'
            other=await c.post('/api/saved-charts',json=birth,headers=headers[0]);other.raise_for_status()
            other_path='/api/saved-charts/'+str(other.json()['saved_chart_id'])
            assert (await c.patch(other_path,json={'name':'新命盘名称'},headers=headers[0])).status_code==409
            assert (await c.get('/api/saved-charts',headers=headers[0])).json()['total']==2
            (await c.delete(other_path,headers=headers[0])).raise_for_status()
            assert (await c.delete(other_path,headers=headers[0])).status_code==404
            assert (await c.get('/api/sessions/'+sid,headers=headers[0])).status_code==200
            (await c.delete('/api/saved-charts',headers=headers[1])).raise_for_status()
            assert (await c.get('/api/saved-charts',headers=headers[0])).json()['total']==1
            (await c.delete('/api/saved-charts',headers=headers[0])).raise_for_status()
            assert (await c.get('/api/saved-charts',headers=headers[0])).json()['total']==0
            assert (await c.get('/api/sessions/'+sid,headers=headers[0])).status_code==200
            print('PASS: named charts, lunar conversion, minutes, deduplication, account isolation, session names, rename, duplicate-name conflict, single deletion, clear history')
    finally:
        await conn.execute('DELETE FROM auth_user WHERE username=ANY($1::text[])', users)
        await conn.execute('DELETE FROM auth_login_attempt WHERE account_key=ANY($1::text[])', users)
        await conn.close()
        print('Disposable accounts cleaned')


if __name__=='__main__':
    asyncio.run(main())
