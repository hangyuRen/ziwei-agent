import json
from types import SimpleNamespace

import pytest

from ziwei.models import Birth, BirthLookup, ChartRow, SECTIONS
from ziwei.runtime import route
from ziwei.search import Search, rrf_fuse
from ziwei.chat_runtime import ChatRuntime, normalize_tail


def test_chart_key_and_required_sections():
    row = ChartRow.model_validate({'k': '2000-01-01-0-male', 'y': 2000, 'm': 1, 'd': 1, 'h': 0, 'g': 'male', 'c': {s: s for s in SECTIONS}})
    assert row.k == Birth(year=2000, month=1, day=1, hour=0, gender='male').chart_key
    assert Birth(year=2000, month=1, day=1, hour=12, gender='male').chart_key == row.k
    with pytest.raises(ValueError):
        ChartRow.model_validate(row.model_dump() | {'k': '2000-01-02-0-male'})
    with pytest.raises(ValueError):
        ChartRow.model_validate(row.model_dump() | {'c': {'overview': 'x'}})


def test_lunar_lookup_converts_before_chart_key():
    lookup = BirthLookup(calendar='lunar', year=2001, month=12, day=13,
                         hour=8, gender='male')
    assert lookup.to_birth().chart_key == '2002-01-25-8-male'
    leap = BirthLookup(calendar='lunar', year=2023, month=2, day=1,
                       leap_month=True, hour=0, gender='female')
    assert leap.to_birth().chart_key == '2023-03-22-0-female'
    with pytest.raises(ValueError):
        BirthLookup(calendar='lunar', year=2022, month=2, day=1,
                    leap_month=True, hour=0, gender='female')
    with pytest.raises(ValueError):
        BirthLookup(calendar='lunar', year=2026, month=12, day=1,
                    hour=0, gender='male').to_birth()


@pytest.mark.asyncio
async def test_followup_can_cite_prior_session_source_without_failing():
    class Store:
        async def session_sources(self, user_id, sid, ids):
            assert ids == {42, 999}
            return [{'id': 42, 'bvid': 'BV1234567890', 'part': 2,
                     't_hms': '00:09:17'}]

    runtime = ChatRuntime(None, None, None, None)
    runtime.store = Store()
    answer, refs = await runtime.verified_sources(1, 'session',
        '上一轮依据[天纪#42]，未知编号[天纪#999]。', [])
    assert answer == '上一轮依据[天纪#42]，未知编号。'
    assert refs == [{'id': 42, 'bvid': 'BV1234567890', 'part': 2,
                     't_hms': '00:09:17'}]


def test_route_followup():
    assert route('那财运呢？')[0] == ['wealth']
    assert route('那财运呢？')[1]
    assert route('紫微是什么？')[1]


@pytest.mark.asyncio
async def test_video_timestamp_citation_converts_only_when_verified():
    class Store:
        async def session_sources_by_locations(self, user_id, sid, locations):
            assert locations == {(2, '00:09:17'), (3, '00:04:00')}
            return [{'id': 42, 'bvid': 'BV1234567890', 'part': 2,
                     't_hms': '00:09:17'}]
        async def session_sources(self, user_id, sid, ids):
            return []

    runtime = ChatRuntime(None, None, None, None)
    runtime.store = Store()
    answer, refs = await runtime.verified_sources(1, 'session',
        '有据〔《天纪》第2集 09:17〕，无据〔《天纪》p03 00:04:00〕。', [])
    assert answer == '有据[天纪#42]，无据。'
    assert refs[0]['t_hms'] == '00:09:17'


@pytest.mark.asyncio
async def test_model_id_citation_is_linkable_without_long_source_label():
    class Store:
        async def session_sources(self, user_id, sid, ids):
            assert ids == {42, 999}
            return [{'id': 42, 'bvid': 'BV1234567890', 'part': 2,
                     't_hms': '00:09:17'}]

    runtime = ChatRuntime(None, None, None, None)
    runtime.store = Store()
    answer, refs = await runtime.verified_sources(1, 'session',
        '论述〔id 42，part 2，00:09:17〕，虚构〔id 999〕。', [])
    assert answer == '论述[天纪#42]，虚构。'
    assert len(refs) == 1


@pytest.mark.asyncio
async def test_tianji_hybrid_search_and_rerank():
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {'hits': {'hits': [{'_id': '42', '_source': {'book': '天纪', 'h2': '化忌',
                'h3': None, 'quote': '原句', 'section': 2, 't_hms': '01:02:03',
                'note': '注释', 'bvid': 'BV1', 'part': 1}},
                {'_id': '43', '_source': {'book': '天纪', 'h2': '其他', 'quote': '次要原句'}}]}}

    class Client:
        async def post(self, path, json):
            assert path == '/tianji-chunks-v1/_search'
            assert json['size'] in (5,12)
            assert json['query']['bool']['should'][0]['multi_match']['query'] in ('化忌 主劫杀','化忌是什么')
            return Response()

    class LLM:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, json_mode=False):
            assert json_mode
            self.calls += 1
            if self.calls == 1:
                assert '化忌是什么' in messages[1]['content']
                return {'content': json.dumps({'keywords': ['化忌 主劫杀'],
                    'questions': ['化忌在命理中代表什么？']})}
            raise AssertionError('应只调用一次 DeepSeek 检索规划')

    class Repo:
        async def vector_search(self, vector, model, limit, filters):
            assert vector == [0.1, 0.2]
            assert model == 'embedding-3'
            assert limit in (5,12)
            return [{'id': 43, 'h2': '其他', 'h3': None, 'quote': '次要原句'},
                    {'id': 44, 'h2': '真正相关', 'h3': None, 'quote': '重要原句'}]

    class Zhipu:
        async def embed(self, questions):
            assert questions in (['化忌在命理中代表什么？'],['化忌是什么'])
            return [[0.1, 0.2]]

        async def rerank(self, query, documents, top_n):
            assert query == '化忌是什么'
            assert len(documents) == 3
            assert top_n == 3
            return [{'index': documents.index('重要原句'), 'relevance_score': 0.9},
                    {'index': documents.index('次要原句'), 'relevance_score': 0.8}]

    search = Search(SimpleNamespace(elasticsearch_url='http://localhost:9200',
        elasticsearch_api_key='', elasticsearch_user='', elasticsearch_password='',
        zhipu_embedding_model='embedding-3'), Zhipu())
    await search.client.aclose()
    search.client = Client()
    llm = LLM()
    rows = await search.search('化忌是什么', llm, Repo())
    assert llm.calls == 1
    assert [row['id'] for row in rows] == [44, 43]


def test_rrf_rewards_agreement_across_branches():
    branches = [[{'id': 1}, {'id': 2}], [{'id': 2}, {'id': 3}]]
    assert [row['id'] for row in rrf_fuse(branches)] == [2, 1, 3]


def test_tool_result_reenters_llm_context():
    rows = [
        {'role': 'assistant', 'content': {'kind': 'tool_calls', 'tool_calls': [
            {'id': 'call-1', 'type': 'function', 'function': {'name': 'search_tianji', 'arguments': '{}'}}]}},
        {'role': 'tool', 'tool_call_id': 'call-1', 'content': {'result': {'quotes': [{'id': 42}]}}},
    ]
    messages = normalize_tail(rows)
    assert [message['role'] for message in messages] == ['assistant', 'tool']
    assert messages[1]['tool_call_id'] == 'call-1'


@pytest.mark.asyncio
async def test_tool_rejects_other_chart():
    class Repo:
        async def section(self, key, section):
            return 'secret'
    runtime = ChatRuntime(Repo(), None, None, None)
    session = {'chart_key': '2000-01-01-0-male'}
    with pytest.raises(PermissionError):
        await runtime.tool('get_chart_section', {'chart_key': '2000-01-01-0-female', 'section_type': 'career'}, session)
    with pytest.raises(ValueError):
        await runtime.tool('get_chart_section', {'chart_key': session['chart_key'], 'section_type': 'unknown'}, session)
    assert (await runtime.tool('get_chart_section', {'chart_key': session['chart_key'], 'section_type': 'career'}, session))['content'] == 'secret'


@pytest.mark.parametrize('clock_hour,index', [(0,0),(1,1),(6,3),(7,4),(8,4),(9,5),(19,10),(22,11),(23,0)])
def test_beijing_clock_hour_uses_two_hour_period(clock_hour, index):
    lookup = BirthLookup(year=2001,month=12,day=13,clock_hour=clock_hour,minute=59,gender='male')
    assert lookup.hour == index
    assert lookup.to_birth().hour == index
    assert lookup.to_birth().day == 13


def test_named_birth_rejects_whitespace_and_keeps_minutes():
    from ziwei.models import SavedBirthLookup
    with pytest.raises(ValueError):
        SavedBirthLookup(name='   ',year=2000,month=1,day=1,gender='male')
    profile = SavedBirthLookup(name=' 小林 ',calendar='lunar',year=2001,month=12,day=13,
                              clock_hour=8,minute=5,gender='male')
    assert profile.name == '小林'
    assert profile.minute == 5
    assert profile.to_birth().chart_key == '2002-01-25-4-male'
