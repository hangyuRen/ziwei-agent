import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ziwei.chat_runtime import ChatRuntime, RollingSummary


def test_summary_accepts_provider_objects_without_losing_qualifiers():
    result=RollingSummary.model_validate({
        'section_summaries': {'career': {'summary':'官禄宫原文','condition':'仅论本命','section_type':'career'}},
        'conversation_summary': {'summary':'讨论事业'},
        'confirmed_facts':[{'fact':'用户询问事业','seq':17}],
        'open_questions':[{'question':'后续方向','seq':25}],
        'source_refs':[{'id':42,'bvid':'BV123','part':2,'t_hms':'00:01:02'}]})
    assert json.loads(result.section_summaries['career'])['condition']=='仅论本命'
    assert json.loads(result.confirmed_facts[0])['seq']==17
    assert result.source_refs[0].quote_id==42
    assert result.model_dump()['source_refs'][0]['quote_id']==42
    with pytest.raises(ValidationError):
        RollingSummary.model_validate({'source_refs':[{'id':-1}]})


@pytest.mark.asyncio
async def test_summary_retries_missing_section_without_advancing_coverage_early():
    class Provider:
        calls=0
        async def chat(self,messages,json_mode=False):
            assert json_mode and 'JSON Schema' in messages[0]['content']
            self.calls+=1
            return {'content':json.dumps({'section_summaries':{} if self.calls==1 else {'career':'结论'}})}
    provider=Provider();rt=ChatRuntime(None,None,provider,None)
    result=await rt.build_summary({},[],{'career'},'chart')
    assert provider.calls==2 and result.section_summaries['career']=='结论'


@pytest.mark.asyncio
async def test_malformed_summary_falls_back_to_real_history_and_prior_corrections():
    class Provider:
        async def chat(self,*args,**kwargs):
            return {'content':'not json'}
    rt=ChatRuntime(None,None,Provider(),None)
    rows=[{'seq':1,'role':'user','content':{'text':'你好'}},
          {'seq':2,'role':'tool','content':{'result':{'section_type':'career','content':'官禄宫原文','quotes':[{'id':42,'bvid':'BV123'}]}}},
          {'seq':3,'role':'assistant','content':{'kind':'final','text':'历史回答','reasoning':'不应进入摘要'}}]
    result=await rt.build_summary({'user_corrections':['用户明确纠正的信息']},rows,{'career','overview'},'chart')
    assert '官禄宫原文' in result.section_summaries['career']
    assert '你好' in result.conversation_summary and '历史回答' in result.conversation_summary
    assert '不应进入摘要' not in result.conversation_summary
    assert result.user_corrections==['用户明确纠正的信息']
    assert result.source_refs[0].quote_id==42
    assert 'overview' in result.section_summaries


@pytest.mark.asyncio
async def test_triggered_summary_commits_canonical_model_only_after_validation():
    class Store:
        async def summary(self,*args):
            return {'summary':{},'covered_seq':0,'revision':0}
        async def context_tail(self,*args):
            return [{'seq':1,'role':'user','status':'complete','content':{'text':'旧问题'}},
                    {'seq':2,'role':'assistant','status':'complete','content':{'kind':'final','text':'旧回答'}},
                    {'seq':3,'role':'user','status':'pending','content':{'text':'你好'}}]
        async def cas_summary(self,user,sid,revision,old_seq,cut,summary):
            assert (old_seq,cut)==(0,2)
            RollingSummary.model_validate(summary)
            return True
    class Provider:
        async def chat(self,*args,**kwargs):
            return {'content':json.dumps({'conversation_summary':{'summary':'旧讨论'},'source_refs':[{'id':42}]})}
    rt=ChatRuntime(None,None,Provider(),SimpleNamespace(prompt_token_budget=1,summary_trigger_ratio=.8));rt.store=Store()
    result=await rt.summarize_if_needed(1,'sid',{'chart_key':'chart'},3)
    assert result['covered_seq']==2 and result['summary']['source_refs'][0]['quote_id']==42
