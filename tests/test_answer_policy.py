from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4
import json

import pytest

from ziwei.search import qualified_quotes
from ziwei.chat_runtime import ChatRuntime, normalize_tail


def test_strict_rerank_threshold_and_legacy_history_filter():
    quotes=[{'id':1,'rerank_score':.49},{'id':2,'rerank_score':.5},
            {'id':3,'rerank_score':.5001},{'id':4},{'id':5,'rerank_score':float('nan')}]
    assert [r['id'] for r in qualified_quotes(quotes)]==[3]
    rows=[{'role':'assistant','content':{'kind':'tool_calls','tool_calls':[
        {'id':'c','function':{'name':'search_tianji','arguments':'{}'}}]}},
        {'role':'tool','tool_call_id':'c','content':{'result':{'quotes':quotes}}}]
    assert [r['id'] for r in json.loads(normalize_tail(rows)[1]['content'])['quotes']]==[3]
    assert rows[1]['content']['result']['quotes']==quotes


@pytest.mark.asyncio
@pytest.mark.parametrize('category', ['unrelated','casual'])
async def test_out_of_scope_and_small_talk_never_call_chart_or_rag(category):
    class Repo:
        @asynccontextmanager
        async def session_lock(self,sid):
            yield
    class Store:
        final=None
        async def request_status(self,*args):
            return {'status':'complete' if self.final else 'pending'}
        async def owned(self,*args):
            return {'chart_key':'chart','title':'已有标题'}
        async def request_messages(self,*args):
            return [{'role':'user','seq':1,'content':{'text':'你好'}}]
        async def visible(self,*args,**kwargs):
            return {'items':[]}
        async def append(self,user,sid,role,content,rid,**kwargs):
            if content['kind']=='final': self.final=content
        async def set_request_status(self,*args):
            pass
    class Provider:
        async def chat(self,*args,**kwargs):
            return {'content':json.dumps({'category':category})}
        async def stream_answer(self,messages):
            assert '没有实时天气接口' in messages[0]['content']
            yield 'answer_delta','你好，我是紫微研习。'
    rt=ChatRuntime(Repo(),None,Provider(),None);rt.store=Store()
    status=await rt.run_request(1,'sid',uuid4())
    assert status['status']=='complete'
    assert ('解读范围' in rt.store.final['text']) if category=='unrelated' else ('你好' in rt.store.final['text'])
