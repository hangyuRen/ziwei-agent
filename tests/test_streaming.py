import json
from types import SimpleNamespace

import httpx
import pytest

from ziwei.llm import LLM
from ziwei.chat_runtime import ChatRuntime


@pytest.mark.asyncio
async def test_provider_stream_separates_reasoning_answer_and_rejects_truncation():
    def handler(request):
        body=json.loads(request.content)
        assert body['stream'] is True and body['thinking']=={'type':'enabled'}
        assert 'tools' not in body and body['tool_choice']=='none'
        chunks=[{'choices':[{'delta':{'reasoning_content':'依据'},'finish_reason':None}]},
                {'choices':[{'delta':{'content':'回答'},'finish_reason':'stop'}]}]
        return httpx.Response(200, text=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n')
    settings=SimpleNamespace(llm_api_key='test',llm_model='deepseek-flash',llm_base_url='https://test')
    llm=LLM(settings)
    await llm.client.aclose()
    llm.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        assert [x async for x in llm.stream_answer([])]==[('reasoning_delta','依据'),('answer_delta','回答')]
    finally:
        await llm.close()
    llm.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text='data: [DONE]\n\n')))
    try:
        with pytest.raises(RuntimeError,match='提前中断'):
            _=[x async for x in llm.stream_answer([])]
    finally:
        await llm.close()


@pytest.mark.asyncio
async def test_stream_batches_are_durable_and_reasoning_ends_before_answer():
    class Provider:
        async def stream_answer(self, messages):
            yield 'reasoning_delta','先看'
            yield 'reasoning_delta','依据'
            yield 'answer_delta','第一段'
            yield 'answer_delta','第二段'
    rows=[]
    class Store:
        async def append(self, user, sid, role, content, rid):
            rows.append(content)
    runtime=ChatRuntime(None,None,Provider(),None)
    runtime.store=Store()
    answer,reasoning=await runtime.stream_final(1,'sid','rid',[])
    assert answer=='第一段第二段' and reasoning=='先看依据'
    assert [r['event'] for r in rows]==['reasoning_delta','reasoning_end','answer_delta']
    assert rows[0]['text']=='先看依据' and rows[2]['text']==answer


@pytest.mark.asyncio
async def test_provider_without_reasoning_does_not_invent_thoughts():
    class Provider:
        async def stream_answer(self, messages):
            yield 'answer_delta','直接回答'
    class Store:
        async def append(self,*args):
            pass
    runtime=ChatRuntime(None,None,Provider(),None);runtime.store=Store()
    assert await runtime.stream_final(1,'sid','rid',[])==('直接回答','')
