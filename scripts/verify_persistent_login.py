"""Verify cookie persistence, expiry, revocation and SSE through Nginx."""
import asyncio
import copy
from http.cookiejar import CookieJar
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import httpx
import jwt

from ziwei.auth import AUTH_COOKIE


async def main():
    name='cookiecheck_'+uuid4().hex[:12];password=uuid4().hex
    db=await asyncpg.connect(os.environ['DATABASE_URL'])
    try:
        async with httpx.AsyncClient(base_url='http://127.0.0.1',timeout=120) as client:
            for _ in range(20):
                try:
                    if (await client.get('/api/health')).status_code==200: break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(.5)
            r=await client.post('/api/auth/register',json={'username':name,'password':password,'confirm_password':password});r.raise_for_status()
            r=await client.post('/api/auth/login',json={'account':name,'password':password});r.raise_for_status()
            cookie=r.headers['set-cookie']
            assert 'HttpOnly' in cookie and 'Max-Age=43200' in cookie and 'expires=' in cookie
            token=client.cookies.get(AUTH_COOKIE)
            jar=CookieJar()
            for item in client.cookies.jar:
                jar.set_cookie(copy.copy(item))
            assert all(not item.discard and item.expires is not None for item in jar)
            uid=(await client.get('/api/auth/me')).json()['id']
        # A new client has no Authorization header, JS memory or password.
        async with httpx.AsyncClient(base_url='http://127.0.0.1',cookies=jar,timeout=120) as reopened:
            assert (await reopened.get('/api/auth/me')).json()['id']==uid
            (await reopened.get('/api/sessions')).raise_for_status()
            (await reopened.get('/api/saved-charts')).raise_for_status()
            blocked=await reopened.post('/api/auth/logout',headers={'Origin':'https://foreign.test'})
            assert blocked.status_code==403
            assert (await reopened.get('/api/auth/me')).status_code==200
            r=await reopened.post('/api/sessions',json={'chart_key':None},headers={'Origin':'http://127.0.0.1'});r.raise_for_status();sid=r.json()['id']
            rid=str(uuid4())
            r=await reopened.post(f'/api/sessions/{sid}/messages',json={'client_request_id':rid,'message':'你好，用一句话打个招呼。'});r.raise_for_status()
            response=await reopened.get(f'/api/sessions/{sid}/events?request_id={rid}')
            response.raise_for_status();assert 'event: message_end' in response.text and 'event: answer_delta' in response.text
            claims=jwt.decode(token,options={'verify_signature':False})
            claims['exp']=datetime.now(timezone.utc)-timedelta(minutes=2)
            expired=jwt.encode(claims,os.environ['JWT_SECRET'],algorithm='HS256')
            async with httpx.AsyncClient(base_url='http://127.0.0.1',cookies={AUTH_COOKIE:expired}) as invalid:
                assert (await invalid.get('/api/auth/me')).status_code==401
            r=await reopened.post('/api/auth/logout');r.raise_for_status()
            assert 'Max-Age=0' in r.headers['set-cookie']
            assert (await reopened.get('/api/auth/me')).status_code==401
        async with httpx.AsyncClient(base_url='http://127.0.0.1',cookies={AUTH_COOKIE:token}) as stale:
            assert (await stale.get('/api/auth/me')).status_code==401
        print('PASS: persistent Cookie, new client restoration, history, cookie-only SSE, CSRF origin, expiry, logout and revocation',flush=True)
    finally:
        await db.execute('DELETE FROM auth_user WHERE username=$1',name)
        await db.execute('DELETE FROM auth_login_attempt WHERE account_key=$1',name)
        await db.close()
        print('Disposable account cleaned',flush=True)


if __name__=='__main__':
    asyncio.run(main())
