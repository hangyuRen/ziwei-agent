from datetime import date
import gzip
import json
from pathlib import Path

import httpx
import pytest

from ziwei.astrology import generate_chart
from ziwei.models import BirthLookup
from ziwei.transformations import (
    KINDS, build_transformations, detect_self_sihua, find_incoming_palaces, get_si_hua_by_stem,
)


def test_matches_frozen_unmodified_upstream_sihua_helpers():
    path=Path(__file__).parent/'fixtures/upstream-transformations.json.gz'
    bundle=json.loads(gzip.decompress(path.read_bytes()))
    assert len(bundle['cases'])==344
    stems=set()
    for case in bundle['cases']:
        inp=case['input']
        birth=BirthLookup(**{k:v for k,v in inp.items() if k not in ('policy','school')}).to_birth()
        chart=generate_chart(birth,inp['school'],inp['policy'],date(2026,11,9))
        actual=chart['transformations']
        actual['flyingStars'].sort(key=lambda e:(e['sourceBranch'],KINDS.index(e['siHua'])))
        assert actual==case['expected'],inp
        stems.add(chart['lunarInfo']['yearStem'])
    assert stems==set(range(10))


def test_flights_retain_repeated_sources_and_detect_self_without_moving_stars():
    birth=BirthLookup(year=2000,month=8,day=16,hour=6,gender='male').to_birth()
    chart=generate_chart(birth,as_of=date(2026,11,9))
    before=json.dumps(chart['palaces'],ensure_ascii=False,sort_keys=True)
    result=build_transformations(chart,2027)
    assert result['annual']['stemName']=='丁'
    assert result['annual']['transforms']=={'禄':'太阴','权':'天同','科':'天机','忌':'巨门'}
    assert json.dumps(chart['palaces'],ensure_ascii=False,sort_keys=True)==before
    assert len(result['flyingStars'])==48
    assert sum(e['self'] for e in result['flyingStars'])==sum(len(v) for v in result['selfSihua'].values())
    repeated=False
    for p in chart['palaces']:
        own=detect_self_sihua(p)
        assert own==result['selfSihua'].get(str(p['branch']),[])
        edges=[e for e in result['flyingStars'] if e['sourceBranch']==p['branch']]
        assert len(edges)==4 and {e['siHua'] for e in edges}==set(KINDS)
        for edge in edges:
            sources=find_incoming_palaces(chart,edge['starName'],edge['siHua'])
            repeated |= len(sources)>1
            assert p in sources
            target=next(t for t in chart['palaces'] if t['branch']==edge['targetBranch'])
            assert any(s['name']==edge['starName'] for s in target['stars'])
    assert repeated
    for decade in result['daXians']:
        palace=next(p for p in chart['palaces'] if p['branch']==decade['palaceBranch'])
        assert decade['transforms']==get_si_hua_by_stem(palace['stem'])


@pytest.mark.parametrize('value',[-1,10,True,'甲'])
def test_invalid_stems_are_not_silently_replaced(value):
    with pytest.raises(ValueError):
        get_si_hua_by_stem(value)


@pytest.mark.asyncio
async def test_annual_api_uses_corrected_chart_key_and_rejects_invalid_year(monkeypatch):
    from ziwei.api import app
    class Repo:
        async def chart(self,key):
            if key!='2000-08-16-6-male':
                return None
            return {'birth_year':2000,'birth_month':8,'birth_day':16,'birth_hour':6,'gender':'male'}
    monkeypatch.setattr(app.state,'repo',Repo(),raising=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        path='/api/charts/2000-08-16-6-male/transformations'
        response=await client.get(path,params={'year':2027})
        assert response.status_code==200
        assert response.json()['annual']['year']==2027
        assert response.json()['annual']['stemName']=='丁'
        for year in ('abc',1799,2201):
            assert (await client.get(path,params={'year':year})).status_code==422
        assert (await client.get('/api/charts/missing/transformations?year=2027')).status_code==404


def test_natal_layers_follow_lunar_birth_year_and_child_has_no_current_decade():
    birth=BirthLookup(year=2026,month=1,day=1,hour=0,gender='female').to_birth()
    chart=generate_chart(birth,as_of=date(2026,11,9))
    assert chart['transformations']['natal']['stemName']=='乙'
    assert chart['transformations']['annual']['stemName']=='丙'
    assert chart['currentDaXianIndex']==-1
    for year in (0,1799,2201,True):
        with pytest.raises(ValueError):
            build_transformations(chart,year)
