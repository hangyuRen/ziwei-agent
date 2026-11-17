import json
from pathlib import Path

import httpx
import pytest

from ziwei.astrology import correct_time, location
from ziwei.locations import (
    DATA_PATH, all_locations, describe_location, legacy_location, picker, registry, search,
)


def test_registry_covers_every_independent_source_name():
    names = json.loads((DATA_PATH.parent/'division_names_snapshot.json').read_text())
    _, nodes, _ = registry()
    for code, name in names.items():
        if code.startswith('83'):
            continue  # Replaced by the complete Taiwan township registry.
        assert nodes['CN:'+code]['name']==name, (code,name)
    taiwan = json.loads((DATA_PATH.parent/'taiwan_townships_snapshot.json').read_text())
    assert len(taiwan)==368
    for row in taiwan:
        node = nodes['TW:'+row['TOWNCODE']]
        assert node['name']==row['TOWNNAME']
        assert node['parent']=='TW:'+row['COUNTYCODE']
        assert nodes[node['parent']]['name']==row['COUNTYNAME']


def test_every_province_city_and_district_can_be_enumerated_without_truncation():
    data,nodes,children = registry()
    assert data['counts']=={'province':34,'city':365,'district':3246}
    assert len(nodes)==sum(data['counts'].values())
    root = picker()
    assert len(root['provinces'])==34
    assert not root['cities'] and not root['districts']
    visited = set()
    for province in root['provinces']:
        cities = picker(province['id'])['cities']
        assert cities
        for city in cities:
            response = picker(province['id'],city['id'])
            assert response['districts']
            assert len(response['districts'])==len(children[city['id']])
            for district in response['districts']:
                assert district['province_id']==province['id']
                assert district['city_id']==city['id']
                assert district['id'] not in visited
                visited.add(district['id'])
                assert 73<district['longitude']<136 and 3<district['latitude']<54
                assert district['region']=='domestic'
    assert visited=={n['id'] for n in data['nodes'] if n['level']=='district'}


def test_special_levels_and_new_counties():
    _,nodes,_ = registry()
    assert len(picker('CN:110000')['districts'])==16
    assert len(picker('CN:500000')['districts'])==37
    assert len(picker('CN:810000')['districts'])==18
    assert len(picker('CN:820000')['districts'])==9
    assert len(picker('CN:710000')['cities'])==22
    for code in ('419001','429004','469001','659013'):
        c=describe_location('CN:'+code)
        assert nodes[c['city_id']]['name'].endswith('直辖县级行政区划')
    for code in ('441900','442000','460400','620200'):
        c=describe_location('CN:'+code+':all')
        assert c['whole_city'] and c['city_id']=='CN:'+code
    for code,name in [('653132','岑岭县'),('653228','和康县'),('653229','和安县'),('659013','草湖市')]:
        assert describe_location('CN:'+code)['display_name']==name
    # Guard against a known unrelated Caohu place in eastern Xinjiang.
    assert 76<describe_location('CN:659013')['longitude']<77
    with pytest.raises(ValueError,match='不匹配'):
        picker('CN:440000','CN:510100')
    with pytest.raises(ValueError):
        picker('CN.')
    with pytest.raises(ValueError):
        describe_location('CN:440000')


def test_search_disambiguates_counties_and_supports_taiwan_variants():
    assert len(search('朝阳'))>1
    assert any(c['full_name']=='北京市 / 朝阳区' for c in search('朝阳'))
    assert search('北京 朝阳')[0]['id']=='CN:110105'
    assert search('武侯')[0]['full_name']=='四川省 / 成都市 / 武侯区'
    assert len(search('四川省'))==183
    assert len(search('区'))>200  # No population or 200-result cutoff.
    assert search('台北')==search('臺北')
    assert len(search('桃园'))==13
    assert search('金門') or search('金门')
    assert not search('London')
    assert len(all_locations())==3246


def test_new_district_ids_feed_solar_time_and_preserve_legacy_records():
    for code,timezone in [('CN:110105','Asia/Shanghai'),('CN:810101','Asia/Hong_Kong'),
                          ('CN:820101','Asia/Macau'),('TW:63000010','Asia/Taipei')]:
        result=correct_time(2000,1,1,12,0,code)
        assert result['location']['id']==code
        assert result['location']['timezone']==timezone
        assert result['utc_offset_minutes']==480
    assert location('1816670')['name']=='Beijing'
    assert legacy_location('1816670')['province_id']=='CN:110000'
    assert legacy_location('5128581')['timezone']=='America/New_York'
    with pytest.raises(ValueError):
        correct_time(2000,1,1,12,0,'CN:999999')


@pytest.mark.asyncio
async def test_public_api_only_offers_domestic_options_and_rejects_cross_province_city():
    from ziwei.api import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        response=await client.get('/api/location-picker')
        assert response.status_code==200 and len(response.json()['provinces'])==34
        response=await client.get('/api/location-picker',params={'province':'CN:440000','city':'CN:440300'})
        assert response.status_code==200
        assert len(response.json()['districts'])==9
        assert all(c['city_id']=='CN:440300' for c in response.json()['districts'])
        response=await client.get('/api/location-picker',params={'province':'CN:440000','city':'CN:510100'})
        assert response.status_code==422
        for path in ('/api/location-picker','/api/locations'):
            assert (await client.get(path,params={'region':'overseas'})).status_code==422
        response=await client.get('/api/locations/CN:510107')
        assert response.status_code==200 and response.json()['display_name']=='武侯区'
        assert (await client.get('/api/locations/1816670')).status_code==200
        assert (await client.get('/api/locations/CN:999999')).status_code==422
