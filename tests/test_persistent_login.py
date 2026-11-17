from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException, Request, Response

from ziwei.auth import AUTH_COOKIE, LoginInput, check_cookie_origin, get_current_user, issue_token
from ziwei.config import Settings


def request_for(settings, cookie='', method='GET', origin=None, scheme='http', version=0):
    class Pool:
        async def fetchrow(self,*args):
            return {'id':1,'username':'test','email':None,'token_version':version,'is_active':True}
    app=SimpleNamespace(state=SimpleNamespace(settings=settings,repo=SimpleNamespace(pool=Pool())))
    headers=[(b'host',b'test')]
    if cookie: headers.append((b'cookie',f'{AUTH_COOKIE}={cookie}'.encode()))
    if origin is not None: headers.append((b'origin',origin.encode()))
    return Request({'type':'http','method':method,'path':'/api/auth/me','scheme':scheme,
                    'server':('test',80),'query_string':b'','headers':headers,'app':app})


@pytest.mark.asyncio
async def test_cookie_auth_survives_a_new_request_and_enforces_revocation_and_expiry():
    settings=Settings(jwt_secret='x'*40)
    token=issue_token({'id':1,'token_version':0},settings)
    for _ in range(2):
        user=await get_current_user(request_for(settings,token),'')
        assert user['id']==1
    with pytest.raises(HTTPException) as revoked:
        await get_current_user(request_for(settings,token,version=1),'')
    assert revoked.value.status_code==401
    claims=jwt.decode(token,options={'verify_signature':False});claims['exp']=datetime.now(timezone.utc)-timedelta(minutes=1)
    expired=jwt.encode(claims,settings.jwt_secret,algorithm='HS256')
    with pytest.raises(HTTPException) as expiry:
        await get_current_user(request_for(settings,expired),'')
    assert expiry.value.status_code==401


@pytest.mark.asyncio
async def test_cookie_write_rejects_foreign_or_null_origin():
    settings=Settings(jwt_secret='x'*40)
    token=issue_token({'id':1,'token_version':0},settings)
    for origin in ['https://foreign.test','null']:
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request_for(settings,token,method='POST',origin=origin),'')
        assert exc.value.status_code==403
    assert (await get_current_user(request_for(settings,token,method='POST',origin='http://test'),''))['id']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('scheme,secure',[('http',False),('https',True)])
async def test_login_cookie_is_persistent_httponly_and_https_secure(monkeypatch,scheme,secure):
    from ziwei import api
    async def fake_login(*args):
        return {'access_token':'test-token','expires_in':43200,'user':{'id':1}}
    monkeypatch.setattr(api,'login',fake_login)
    monkeypatch.setattr(api.app.state,'repo',object(),raising=False)
    response=Response()
    await api.login_user(LoginInput(account='test',password='test'),request_for(Settings(),method='POST',scheme=scheme),response)
    cookie=response.headers['set-cookie']
    assert 'Max-Age=43200' in cookie and 'expires=' in cookie and 'HttpOnly' in cookie
    assert 'Path=/api' in cookie and 'SameSite=lax' in cookie
    assert ('Secure' in cookie)==secure
    assert response.headers['cache-control']=='no-store'


@pytest.mark.asyncio
async def test_logout_clears_an_expired_or_revoked_cookie(monkeypatch):
    from ziwei import api
    async def invalid_user(*args):
        raise HTTPException(401,'expired')
    monkeypatch.setattr(api,'get_current_user',invalid_user)
    response=Response()
    assert await api.logout_user(request_for(Settings(),method='POST'),response)=={'ok':True}
    assert 'Max-Age=0' in response.headers['set-cookie']
