from datetime import datetime
import pytest
from ziwei.astrology import correct_time, generate_chart, search_locations
from ziwei.models import BirthLookup

def test_city_search():
    assert search_locations('北京')[0]['id']=='1816670'
    assert search_locations('London','overseas')[0]['timezone']=='Europe/London'

def test_solar_and_late_zi():
    c=correct_time(2000,1,1,0,1,'1816670')
    assert c['true_solar_time'].startswith('1999-12-31T23:')
    assert c['chart_date']=='2000-01-01' and c['branch']==0
    c=correct_time(2000,8,16,23,0,'1816670')
    assert c['branch']==11 and c['chart_date']=='2000-08-16'

def test_dst_gap_fold():
    with pytest.raises(ValueError,match='空档'):
        correct_time(2024,3,10,2,30,'5128581')
    a=correct_time(2024,11,3,1,30,'5128581',0)
    b=correct_time(2024,11,3,1,30,'5128581',1)
    assert a['ambiguous_clock_time'] and a['utc_offset_minutes']-b['utc_offset_minutes']==60

def test_golden_chart():
    b=BirthLookup(year=2000,month=8,day=16,hour=6,gender='male').to_birth()
    c=generate_chart(b)
    assert len(c['palaces'])==12
    p=next(p for p in c['palaces'] if p['name']=='命宫')
    assert p['earthly_branch']=='寅'
    assert [s['name'] for s in p['major_stars']]==['紫微','天府']
    assert p['decadal']['range']==[5,14]

def test_chart_sweep():
    for year in (2000,2001,2004,2010):
        for month in (1,4,7,10):
            for hour in range(12):
                for gender in ('male','female'):
                    b=BirthLookup(year=year,month=month,day=16,hour=hour,gender=gender).to_birth()
                    c=generate_chart(b)
                    assert len({p['earthly_branch'] for p in c['palaces']})==12
                    assert sum(len(p['major_stars']) for p in c['palaces'])==14


def test_engine_rejects_invalid_direct_input():
    from types import SimpleNamespace
    for hour in (-1,12,True):
        with pytest.raises(ValueError,match='时辰索引'):
            generate_chart(SimpleNamespace(hour=hour,gender='male'))
    with pytest.raises(ValueError,match='性别'):
        generate_chart(SimpleNamespace(hour=0,gender='unknown'))
