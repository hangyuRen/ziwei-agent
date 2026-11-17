from datetime import datetime
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ziwei.models import BirthLookup
from ziwei.sessions import session_public


def fake_chart(key):
    y,m,d,h,g=key.split('-')
    return dict(chart_key=key,birth_year=int(y),birth_month=int(m),birth_day=int(d),
                birth_hour=int(h),gender=g,content={})


@pytest.mark.asyncio
@pytest.mark.parametrize('calendar,year,month,day',[
    ('solar',2002,1,25),('lunar',2001,12,13),
])
async def test_resolution_retains_clock_and_corrected_time(monkeypatch,calendar,year,month,day):
    from ziwei import api
    async def chart(key):
        return fake_chart(key)
    monkeypatch.setattr(api.app.state,'repo',SimpleNamespace(chart=chart),raising=False)
    lookup=BirthLookup(name='时间测试',calendar=calendar,year=year,month=month,day=day,
                       clock_hour=8,minute=5,gender='male',location_id='CN:110105')
    result=await api.resolve(lookup)
    assert result['input_birth']['clock_hour']==8 and result['input_birth']['minute']==5
    assert result['clock_time']=='2002-01-25T08:05'
    assert result['time_correction']['clock_time']=='2002-01-25T08:05:00'
    assert result['time_correction']['true_solar_time']!='2002-01-25T08:05:00'


@pytest.mark.asyncio
async def test_lunar_clock_without_location_is_gregorian_and_missing_hour_is_not_invented(monkeypatch):
    from ziwei import api
    async def chart(key):
        return fake_chart(key)
    monkeypatch.setattr(api.app.state,'repo',SimpleNamespace(chart=chart),raising=False)
    result=await api.resolve(BirthLookup(calendar='lunar',year=2001,month=12,day=13,
                                        clock_hour=0,minute=5,gender='male'))
    assert result['clock_time']=='2002-01-25T00:05'
    assert 'time_correction' not in result
    legacy=await api.resolve(BirthLookup(year=2002,month=1,day=25,hour=4,gender='male'))
    assert 'clock_time' not in legacy and 'time_correction' not in legacy


@pytest.mark.asyncio
async def test_session_creation_preserves_exact_input_and_rejects_wrong_chart(monkeypatch):
    from ziwei import api
    calls=[]
    class Store:
        async def create(self,*args):
            calls.append(args)
            return {'input_birth':args[3]}
    monkeypatch.setattr(api.app.state,'store',Store(),raising=False)
    raw=dict(name='时间测试',year=2002,month=1,day=25,clock_hour=8,minute=5,
             gender='male',location_id='CN:110105',time_fold=0)
    lookup=BirthLookup(**raw)
    key=lookup.to_birth().chart_key
    result=await api.create_session(api.CreateSession(chart_key=key,chart_name=raw['name'],input_birth=raw),user={'id':1})
    assert result['input_birth']==lookup.model_dump()
    assert calls[0][:3]==(1,key,raw['name'])
    with pytest.raises(HTTPException) as err:
        await api.create_session(api.CreateSession(chart_key='2000-01-01-0-male',input_birth=raw),user={'id':1})
    assert err.value.status_code==422 and len(calls)==1


def test_session_public_decodes_owned_snapshot_and_keeps_legacy_null():
    row=dict(id='session',title='时间测试',chart_key='2002-01-25-4-male',chart_name='时间测试',
             last_seq=0,last_interaction_at=datetime(2026,11,10),created_at=datetime(2026,11,10))
    assert session_public(row)['input_birth'] is None
    raw={'year':2002,'clock_hour':8,'minute':5,'location_id':'CN:110105'}
    assert session_public(row|{'chart_input_birth':json.dumps(raw)})['input_birth']==raw
