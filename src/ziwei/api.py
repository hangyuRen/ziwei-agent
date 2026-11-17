"""Public chart lookup and authenticated, chart-bound conversation API."""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from asyncpg import UniqueViolationError
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import AUTH_COOKIE, LoginInput, RegisterInput, check_cookie_origin, get_current_user, login, logout, public_user, register
from .chat_runtime import ChatRuntime
from .config import Settings
from .db import Repository
from .llm import LLM
from .models import BirthLookup, SavedBirthLookup
from lunar_python import LunarYear
from .search import Search
from .sessions import SessionStore
from .zhipu import Zhipu

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if len(settings.jwt_secret) < 32:
        raise RuntimeError('JWT_SECRET must contain at least 32 characters')
    app.state.settings = settings
    app.state.repo = await Repository.connect(settings.database_url)
    app.state.store = SessionStore(app.state.repo)
    app.state.zhipu = Zhipu(settings)
    app.state.search = Search(settings, app.state.zhipu)
    app.state.llm = LLM(settings)
    app.state.runtime = ChatRuntime(app.state.repo, app.state.search, app.state.llm, settings)
    app.state.tasks = {}
    try:
        await app.state.search.load_catalog(app.state.repo)
        yield
    finally:
        for task in app.state.tasks.values():
            task.cancel()
        if app.state.tasks:
            await asyncio.gather(*app.state.tasks.values(), return_exceptions=True)
        await app.state.search.close()
        await app.state.zhipu.close()
        await app.state.llm.close()
        await app.state.repo.pool.close()


app = FastAPI(title='紫微命盘智能解读', lifespan=lifespan)
static_root = Path.cwd() / 'static'
if not static_root.is_dir():
    static_root = Path(__file__).resolve().parents[2] / 'static'
app.mount('/static', StaticFiles(directory=static_root), name='static')


class CreateSession(BaseModel):
    chart_key: str | None = Field(default=None, max_length=100)
    chart_name: str | None = Field(default=None, max_length=80)
    input_birth: BirthLookup | None = None


class RenameSession(BaseModel):
    title: str = Field(min_length=1, max_length=160)


class RenameSavedChart(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class MessageInput(BaseModel):
    client_request_id: UUID
    message: str = Field(min_length=1, max_length=4000)
    retry: bool = False


class MemoryInput(BaseModel):
    value: str = Field(min_length=1, max_length=2000)


def start_task(user_id: int, sid: str, request_id: UUID):
    key = (sid, str(request_id))
    existing = app.state.tasks.get(key)
    if existing and not existing.done():
        return
    task = asyncio.create_task(app.state.runtime.run_request(user_id, sid, request_id))
    app.state.tasks[key] = task

    def finished(done):
        app.state.tasks.pop(key, None)
        if not done.cancelled():
            try:
                done.result()
            except Exception:
                pass  # the failure is persisted as a request event
    task.add_done_callback(finished)


@app.get('/api/health')
async def health():
    await app.state.repo.pool.fetchval('SELECT 1')
    return {'status': 'ok'}


@app.post('/api/auth/register', status_code=201)
async def register_user(body: RegisterInput):
    return await register(app.state.repo, body)


@app.post('/api/auth/login')
async def login_user(body: LoginInput, request: Request, response: Response):
    check_cookie_origin(request)
    ip = request.client.host if request.client else '0.0.0.0'
    result = await login(app.state.repo, body, ip, settings)
    response.set_cookie(AUTH_COOKIE, result['access_token'], max_age=result['expires_in'],
        expires=datetime.now(timezone.utc) + timedelta(seconds=result['expires_in']),
        path='/api', httponly=True, samesite='lax', secure=request.url.scheme == 'https')
    response.headers['Cache-Control'] = 'no-store'
    return result


@app.get('/api/auth/me')
async def me(response: Response, user=Depends(get_current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return public_user(user)


@app.post('/api/auth/logout')
async def logout_user(request: Request, response: Response):
    check_cookie_origin(request)
    try:
        user = await get_current_user(request, request.headers.get('authorization', ''))
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
    else:
        await logout(app.state.repo, user['id'])
    response.delete_cookie(AUTH_COOKIE, path='/api', httponly=True, samesite='lax',
                           secure=request.url.scheme == 'https')
    response.headers['Cache-Control'] = 'no-store'
    return {'ok': True}


from .astrology import generate_chart, correct_time, search_locations, location


from .locations import picker, describe_location, legacy_location, search as search_domestic_locations


@app.get('/api/location-picker')
async def location_picker(region: str = 'domestic', province: str = '', city: str = '', q: str = ''):
    if region != 'domestic':
        raise HTTPException(422,'出生地选择仅支持国内地区')
    try:
        return picker(province, city, q)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/locations/{city_id}')
async def get_location(city_id: str):
    try:
        return describe_location(city_id) if city_id.startswith(('CN:', 'TW:')) else legacy_location(city_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/locations')
async def locations(q: str = '', region: str = 'domestic', country: str = ''):
    if region != 'domestic':
        raise HTTPException(422,'出生地选择仅支持国内地区')
    return {'items': search_domestic_locations(q, country)}


def chart_public(chart):
    return {'chart_key': chart['chart_key'], 'birth': {'year': chart['birth_year'],
        'month': chart['birth_month'], 'day': chart['birth_day'],
        'hour': chart['birth_hour'], 'gender': chart['gender']}, 'sections': chart['content'], 'natal_chart': generate_chart(BirthLookup(year=chart['birth_year'], month=chart['birth_month'], day=chart['birth_day'], hour=chart['birth_hour'], gender=chart['gender']).to_birth())}


@app.get('/api/calendar/lunar-years/{year}')
async def lunar_year(year: int):
    if not 1999 <= year <= 2026:
        raise HTTPException(422, '农历年份仅支持 1999–2026')
    info = LunarYear.fromYear(year)
    return {'year': year, 'leap_month': info.getLeapMonth() or None,
            'months': {str(item.getMonth()): item.getDayCount() for item in info.getMonthsInYear()}}


@app.post('/api/charts/resolve')
async def resolve(lookup: BirthLookup):
    try:
        birth = lookup.to_birth()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    chart = await app.state.repo.chart(birth.chart_key)
    if not chart:
        raise HTTPException(404, '找不到完全匹配的命盘')
    result = chart_public(chart) | {'input_birth': lookup.model_dump(), 'name': lookup.name}
    if lookup.clock_hour is not None:
        raw = lookup.model_copy(update={'location_id': None}).to_birth()
        result['clock_time'] = datetime(raw.year, raw.month, raw.day, lookup.clock_hour, lookup.minute).isoformat(timespec='minutes')
    if lookup.location_id:
        raw = lookup.model_copy(update={'location_id': None}).to_birth()
        result['time_correction'] = correct_time(raw.year, raw.month, raw.day, lookup.clock_hour, lookup.minute, lookup.location_id, lookup.time_fold)
    return result


@app.post('/api/saved-charts', status_code=201)
async def save_chart(body: SavedBirthLookup, user=Depends(get_current_user)):
    result = await resolve(body)
    row = await app.state.repo.pool.fetchrow('''INSERT INTO saved_chart
        (user_id,chart_key,name,input_birth) VALUES($1,$2,$3,$4::jsonb)
        ON CONFLICT(user_id,name,chart_key) DO UPDATE
        SET input_birth=EXCLUDED.input_birth,updated_at=now() RETURNING id''',
        user['id'], result['chart_key'], body.name, json.dumps(body.model_dump()))
    return result | {'saved_chart_id': row['id']}


@app.get('/api/saved-charts')
async def saved_charts(offset: int = Query(default=0, ge=0),
                       limit: int = Query(default=20, ge=1, le=100), user=Depends(get_current_user)):
    rows = await app.state.repo.pool.fetch('''SELECT id,chart_key,name,input_birth,updated_at
        FROM saved_chart WHERE user_id=$1 ORDER BY updated_at DESC,id DESC LIMIT $2 OFFSET $3''',
        user['id'], limit+1, offset)
    from .sessions import as_json
    total = await app.state.repo.pool.fetchval('SELECT count(*) FROM saved_chart WHERE user_id=$1', user['id'])
    return {'items': [dict(r) | {'input_birth': as_json(r['input_birth'])} for r in rows[:limit]],
            'has_more': len(rows)>limit, 'total': total}


@app.delete('/api/saved-charts')
async def clear_saved_charts(user=Depends(get_current_user)):
    await app.state.repo.pool.execute('DELETE FROM saved_chart WHERE user_id=$1', user['id'])
    return {'deleted': True}


@app.patch('/api/saved-charts/{chart_id}')
async def rename_saved_chart(chart_id: int, body: RenameSavedChart, user=Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, '命盘名称不能为空')
    try:
        row = await app.state.repo.pool.fetchrow('''UPDATE saved_chart
            SET name=$3::text,input_birth=jsonb_set(input_birth,'{name}',to_jsonb($3::text)),updated_at=now()
            WHERE id=$1 AND user_id=$2 RETURNING id,name,input_birth''', chart_id, user['id'], name)
    except UniqueViolationError as exc:
        raise HTTPException(409, '相同生辰的命盘已使用该名称，请换一个名称') from exc
    if not row:
        raise HTTPException(404, '命盘记录不存在')
    from .sessions import as_json
    return dict(row) | {'input_birth': as_json(row['input_birth'])}


@app.delete('/api/saved-charts/{chart_id}')
async def delete_saved_chart(chart_id: int, user=Depends(get_current_user)):
    deleted = await app.state.repo.pool.fetchval('''DELETE FROM saved_chart
        WHERE id=$1 AND user_id=$2 RETURNING id''', chart_id, user['id'])
    if deleted is None:
        raise HTTPException(404, '命盘记录不存在')
    return {'deleted': True}


@app.get('/api/charts/{chart_key}')
async def get_chart(chart_key: str):
    chart = await app.state.repo.chart(chart_key)
    if not chart:
        raise HTTPException(404, '找不到完全匹配的命盘')
    return chart_public(chart)


@app.get('/api/charts/{chart_key}/transformations')
async def chart_transformations(chart_key: str, year: int = Query(ge=1800, le=2200)):
    chart = await app.state.repo.chart(chart_key)
    if not chart:
        raise HTTPException(404, '找不到完全匹配的命盘')
    birth = BirthLookup(year=chart['birth_year'], month=chart['birth_month'],
                        day=chart['birth_day'], hour=chart['birth_hour'], gender=chart['gender']).to_birth()
    return generate_chart(birth, transformation_year=year)['transformations']


@app.post('/api/sessions', status_code=201)
async def create_session(body: CreateSession, user=Depends(get_current_user)):
    snapshot = None
    if body.input_birth is not None:
        try:
            if body.input_birth.to_birth().chart_key != body.chart_key:
                raise ValueError('出生信息与所绑定命盘不匹配')
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        snapshot = body.input_birth.model_dump()
    return await app.state.store.create(user['id'], body.chart_key, body.chart_name, snapshot)


@app.get('/api/sessions')
async def list_sessions(limit: int = 20, cursor: str | None = None, user=Depends(get_current_user)):
    return await app.state.store.list(user['id'], limit, cursor)


@app.get('/api/sessions/{sid}')
async def get_session(sid: str, user=Depends(get_current_user)):
    from .sessions import session_public
    return session_public(await app.state.store.owned(user['id'], sid))


@app.patch('/api/sessions/{sid}')
async def rename_session(sid: str, body: RenameSession, user=Depends(get_current_user)):
    title = body.title.strip()
    if not title:
        raise HTTPException(422, '标题不能为空')
    return await app.state.store.rename(user['id'], sid, title)


@app.delete('/api/sessions/{sid}')
async def delete_session(sid: str, user=Depends(get_current_user)):
    return await app.state.store.delete(user['id'], sid)


@app.get('/api/sessions/{sid}/messages')
async def messages(sid: str, before_seq: int | None = Query(default=None, ge=1),
                   limit: int = 10, user=Depends(get_current_user)):
    return await app.state.store.visible(user['id'], sid, before_seq, limit)


@app.get('/api/sessions/{sid}/messages/around')
async def messages_around(sid: str, seq: int = Query(ge=1), user=Depends(get_current_user)):
    return await app.state.store.around(user['id'], sid, seq)


@app.get('/api/sessions/{sid}/questions')
async def questions(sid: str, cursor: int = 0, limit: int = 100, user=Depends(get_current_user)):
    return await app.state.store.questions(user['id'], sid, limit, cursor)


@app.get('/api/sessions/{sid}/timeline')
async def timeline(sid: str, cursor: int = 0, limit: int = 100, user=Depends(get_current_user)):
    return await app.state.store.timeline(user['id'], sid, limit, cursor)


@app.post('/api/sessions/{sid}/messages', status_code=202)
async def send_message(sid: str, body: MessageInput, user=Depends(get_current_user)):
    await app.state.store.owned(user['id'], sid)
    message = body.message.strip()
    if not message:
        raise HTTPException(422, '消息不能为空')
    if not settings.llm_api_key or not settings.llm_model:
        raise HTTPException(503, 'DeepSeek API Key 尚未配置，暂无法提问')
    if body.retry:
        await app.state.store.retry_failed(user['id'], sid, body.client_request_id)
        start_task(user['id'], sid, body.client_request_id)
    else:
        _, created = await app.state.store.append(user['id'], sid, 'user',
            {'v': 1, 'kind': 'text', 'text': message},
            body.client_request_id, status='pending')
        if created:
            start_task(user['id'], sid, body.client_request_id)
    return await app.state.store.request_status(user['id'], sid, body.client_request_id)


@app.get('/api/sessions/{sid}/requests/{request_id}')
async def request_status(sid: str, request_id: UUID, user=Depends(get_current_user)):
    return await app.state.store.request_status(user['id'], sid, request_id)


@app.get('/api/sessions/{sid}/events')
async def events(sid: str, request_id: UUID, request: Request,
                 after_seq: int = Query(default=0, ge=0),
                 last_event_id: str | None = Header(default=None),
                 user=Depends(get_current_user)):
    await app.state.store.request_status(user['id'], sid, request_id)
    if last_event_id:
        try:
            after_seq = max(after_seq, int(last_event_id))
        except ValueError:
            raise HTTPException(422, '无效 Last-Event-ID')

    async def stream():
        cursor = after_seq
        for _ in range(600):
            if await request.is_disconnected():
                return
            rows = await app.state.store.request_messages(user['id'], sid, request_id, cursor)
            for row in rows:
                kind = row['content'].get('kind')
                if row['role'] == 'user':
                    event, payload = 'user_message', {'seq': row['seq'], 'text': row['content']['text']}
                elif kind == 'tool_calls':
                    event, payload = 'tool_start', {'seq': row['seq'], 'tools': [c['function']['name'] for c in row['content']['tool_calls']]}
                elif row['role'] == 'tool':
                    result = row['content']['result']
                    event, payload = 'tool_result', {'seq': row['seq'], 'ok': 'error' not in result,
                        'sources': [{k: q.get(k) for k in ('id','h2','quote','bvid','part','t_hms')}
                                    for q in result.get('quotes', [])]}
                elif kind == 'final':
                    event, payload = 'message_end', {'seq': row['seq'], 'answer': row['content']['text'],
                        'source_refs': row['content'].get('source_refs', []),
                        'reasoning': row['content'].get('reasoning', ''),
                        'title': (await app.state.store.owned(user['id'], sid))['title']}
                elif kind == 'stream':
                    event, payload = row['content']['event'], {'text': row['content']['text']}
                elif kind == 'error':
                    if (await app.state.store.request_status(user['id'], sid, request_id))['status'] != 'failed':
                        cursor = row['seq']
                        continue
                    event, payload = 'error', {'seq': row['seq'], 'error': row['content']['message']}
                else:
                    continue
                cursor = row['seq']
                payload.update({'session_id': sid, 'request_id': str(request_id), 'event_id': cursor})
                yield f"id: {cursor}\nevent: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            status = await app.state.store.request_status(user['id'], sid, request_id)
            if status['status'] == 'complete' and status['answer_seq'] and cursor >= status['answer_seq']:
                return
            if status['status'] == 'failed' and status['error_seq'] and cursor >= status['error_seq']:
                return
            await asyncio.sleep(0.3)
        yield ': reconnect to continue\n\n'
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.get('/api/memory')
async def memories(user=Depends(get_current_user)):
    return {'items': await app.state.repo.memories(str(user['id']))}


@app.put('/api/memory/{memory_key}')
async def save_memory(memory_key: str, body: MemoryInput, user=Depends(get_current_user)):
    if not memory_key or len(memory_key) > 100:
        raise HTTPException(422, 'invalid memory key')
    return await app.state.repo.put_memory(str(user['id']), memory_key, body.value)


@app.delete('/api/memory/{memory_key}')
async def delete_memory(memory_key: str, user=Depends(get_current_user)):
    return {'deleted': await app.state.repo.delete_memory(str(user['id']), memory_key)}


@app.get('/', response_class=HTMLResponse)
async def index():
    return (static_root / 'index.html').read_text(encoding='utf-8')
