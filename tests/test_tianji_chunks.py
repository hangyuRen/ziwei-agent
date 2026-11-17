import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from ziwei.tianji_chunks import build_chunks,make_catalog,reference_sources
from ziwei.search import Search, unique_chunks


def test_chunk_boundaries_reconstruction_provenance_and_stable_ids():
    records=[{'book':'书','h2':'章节','h3':'小节','quote':'甲'*375,'part':1,'bvid':'BV1','t_hms':'00:01:00'},
             {'book':'书','h2':'章节','h3':'小节','quote':'乙'*375,'part':2,'bvid':'BV1','t_hms':'00:02:00'},
             {'book':'书','h2':'章节','h3':'小节','quote':'丙'*375,'part':3,'bvid':'BV1','t_hms':'00:03:00'}]
    rows,sections=build_chunks(records)
    assert len(rows)==3
    assert [row['chunk_index'] for row in rows]==[1,2,3]
    assert all(row['chunk_total']==3 and len(row['body'])<=500 for row in rows)
    assert rows[0]['body']+''.join(row['body'][20:] for row in rows[1:])=='\n'.join(row['quote'] for row in records)
    assert all(a['body'][-20:]==b['body'][:20] for a,b in zip(rows,rows[1:]))
    assert all(row['tianji_chunk'].startswith('来源：书\n章节：章节\n小节：小节\n\n') for row in rows)
    assert all(4886<row['id']<2**53 for row in rows)
    assert {source['part'] for row in rows for source in row['sources']}=={1,2,3}
    assert rows==build_chunks(records)[0]
    assert make_catalog(sections)['sections'][0]['intro']


def test_separate_books_and_optional_h3_are_not_merged():
    rows,sections=build_chunks([{'book':'甲','h2':'同名','quote':'一'}, {'book':'乙','h2':'同名','h3':'','quote':'二'}, {'book':'甲','h2':'同名','h3':'另一节','quote':'三'}])
    assert len(rows)==len(sections)==3
    assert len({row['section_id'] for row in rows})==3


def test_exact_boundary_does_not_emit_tiny_duplicate_tail():
    for n,expected in [(500,1),(501,2),(980,2),(981,3)]:
        rows,_=build_chunks([{'book':'书','h2':'章','quote':'甲'*n}])
        assert len(rows)==expected


def test_provenance_exposes_original_citation_ids():
    rows,_=build_chunks([{'id':42,'book':'书','h2':'章','quote':'原文','part':2,'t_hms':'00:01:00'}])
    sources=reference_sources(rows)
    assert sources[1]['id']==42 and sources[1]['part']==2


@pytest.mark.asyncio
async def test_plan_uses_real_introductions_and_rejects_invented_paths():
    search=Search(SimpleNamespace(elasticsearch_url='http://localhost:9200',elasticsearch_api_key='',elasticsearch_user='',elasticsearch_password=''))
    section={'section_id':'real','book':'02-palaces','h2':'官禄宫','h3':'','intro':'官禄是到公家单位领固定薪水。'}
    search.catalog={'books':[{'book':'02-palaces','intro':'十二宫'}], 'chapters':[{'book':'02-palaces','h2':'官禄宫','intro':'工作事业'}], 'sections':[section]}
    directory=search.directory_context('想问工作',[{'section_id':'real'}])
    class LLM:
        async def chat(self,messages,json_mode=False):
            payload=json.loads(messages[1]['content'])
            assert payload['directory']['sections'][0]['intro']==section['intro']
            return {'content':json.dumps({'keywords':['官禄宫'],'questions':['官禄宫如何分析事业？'],'heading_paths':[{'book':'02-palaces','h2':'官禄宫','h3':''},{'book':'虚构书','h2':'虚构标题','h3':''}]})}
    try:
        keywords,questions,ids=await search.plan_query('想问工作',LLM(),directory)
        assert keywords==['官禄宫'] and ids==['real']
    finally:
        await search.close()


def test_multi_question_results_cover_both_topics_despite_saturated_rerank():
    from ziwei.search import cover_questions
    rows=[{'id':1,'section_id':'化忌','rerank_score':1.0},
          {'id':2,'section_id':'化忌','rerank_score':1.0},
          {'id':3,'section_id':'化禄','rerank_score':1.0}]
    selected=cover_questions(rows,[[{'id':1}],[{'id':3}]],2)
    assert [row['section_id'] for row in selected]==['化忌','化禄']


@pytest.mark.asyncio
async def test_original_video_citation_inside_a_chunk_is_verified():
    from ziwei.chat_runtime import ChatRuntime
    runtime=ChatRuntime(None,None,None,None)
    rows=[{'id':1000000042,'part':1,'t_hms':'00:01:00','sources':[{'original_id':42,'bvid':'BV2','part':2,'t_hms':'00:02:00'}]}]
    answer,refs=await runtime.verified_sources(1,'test','依据[天纪#42]。',rows)
    assert answer=='依据[天纪#42]。'
    assert refs==[{'id':42,'bvid':'BV2','part':2,'t_hms':'00:02:00'}]
