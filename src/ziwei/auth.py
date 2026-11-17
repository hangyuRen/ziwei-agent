"""多用户身份校验。浏览器使用持久 HttpOnly Cookie，兼容 API 的 JWT Bearer。"""
import ipaddress
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from .config import Settings

_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_DUMMY_HASH = _HASHER.hash('dummy-password-never-valid')
_USERNAME = re.compile(r'^[a-zA-Z0-9_]{3,64}$')
_EMAIL = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
AUTH_COOKIE = 'ziwei_session'


def check_cookie_origin(request: Request):
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        origin = request.headers.get('origin')
        expected = f'{request.url.scheme}://{request.url.netloc}'
        if origin is not None and origin != expected:
            raise HTTPException(403, '请从本站页面提交请求')


class RegisterInput(BaseModel):
    username: str
    email: str | None = None
    password: str = Field(min_length=10, max_length=128)
    confirm_password: str

    @model_validator(mode='after')
    def validate_fields(self):
        self.username = self.username.strip().lower()
        if not _USERNAME.fullmatch(self.username):
            raise ValueError('用户名须为 3–64 位英文字母、数字或下划线')
        if self.email:
            self.email = self.email.strip().lower()
            if len(self.email) > 255 or not _EMAIL.fullmatch(self.email):
                raise ValueError('邮箱格式无效')
        if self.password != self.confirm_password:
            raise ValueError('两次密码不一致')
        return self


class LoginInput(BaseModel):
    account: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)


def public_user(row):
    return {'id': row['id'], 'username': row['username'], 'email': row['email']}


def issue_token(user, settings: Settings):
    if len(settings.jwt_secret) < 32:
        raise RuntimeError('JWT_SECRET must contain at least 32 characters')
    now = datetime.now(timezone.utc)
    claims = {'sub': str(user['id']), 'iss': settings.jwt_issuer,
              'aud': settings.jwt_audience, 'iat': now,
              'exp': now + timedelta(hours=12), 'jti': str(uuid4()),
              'ver': user['token_version']}
    return jwt.encode(claims, settings.jwt_secret, algorithm='HS256')


async def register(repo, body: RegisterInput):
    import asyncpg
    password_hash = _HASHER.hash(body.password)
    try:
        row = await repo.pool.fetchrow('''INSERT INTO auth_user(username,email,password_hash)
          VALUES($1,$2,$3) RETURNING id,username,email''', body.username, body.email, password_hash)
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, '用户名或邮箱已被使用')
    return public_user(row)


async def login(repo, body: LoginInput, client_ip: str, settings: Settings):
    account = body.account.strip().lower()
    try:
        client_ip = str(ipaddress.ip_address(client_ip))
    except ValueError:
        client_ip = '0.0.0.0'
    attempts = await repo.pool.fetchval('''SELECT count(*) FROM auth_login_attempt
          WHERE account_key=$1 AND client_ip=$2::inet AND succeeded=false
            AND attempted_at>now()-interval '15 minutes' ''', account, client_ip)
    if attempts >= 5:
        raise HTTPException(429, '登录尝试过多，请稍后再试')
    row = await repo.pool.fetchrow('''SELECT id,username,email,password_hash,token_version,is_active
      FROM auth_user WHERE username=$1 OR email=$1''', account)
    candidate_hash = row['password_hash'] if row else _DUMMY_HASH
    try:
        password_ok = _HASHER.verify(candidate_hash, body.password)
    except (VerifyMismatchError, VerificationError):
        password_ok = False
    succeeded = bool(row and row['is_active'] and password_ok)
    await repo.pool.execute('''INSERT INTO auth_login_attempt(account_key,client_ip,succeeded)
      VALUES($1,$2::inet,$3)''', account, client_ip, succeeded)
    if not succeeded:
        raise HTTPException(401, '用户名或密码错误')
    if _HASHER.check_needs_rehash(row['password_hash']):
        await repo.pool.execute('UPDATE auth_user SET password_hash=$2 WHERE id=$1', row['id'], _HASHER.hash(body.password))
    return {'access_token': issue_token(row, settings), 'token_type': 'bearer',
            'expires_in': 12 * 3600, 'user': public_user(row)}


async def get_current_user(request: Request, authorization: str = Header(default='')):
    settings: Settings = request.app.state.settings
    if authorization.startswith('Bearer '):
        token = authorization[7:]
    else:
        token = request.cookies.get(AUTH_COOKIE)
        check_cookie_origin(request)
    if not token:
        raise HTTPException(401, '请先登录')
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'],
                            issuer=settings.jwt_issuer, audience=settings.jwt_audience,
                            leeway=30, options={'require': ['sub','iss','aud','iat','exp','jti','ver']})
        user_id = int(claims['sub'])
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, '登录已失效，请重新登录')
    if user_id <= 0:
        raise HTTPException(401, '登录已失效，请重新登录')
    row = await request.app.state.repo.pool.fetchrow('''SELECT id,username,email,token_version,is_active
      FROM auth_user WHERE id=$1''', user_id)
    if not row or not row['is_active'] or row['token_version'] != claims['ver']:
        raise HTTPException(401, '登录已失效，请重新登录')
    return dict(row)


async def logout(repo, user_id: int):
    await repo.pool.execute('UPDATE auth_user SET token_version=token_version+1 WHERE id=$1', user_id)
