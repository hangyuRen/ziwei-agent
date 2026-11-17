"""Offline domestic administrative hierarchy; GeoNames IDs are read-only legacy IDs."""
from functools import lru_cache
import json
from pathlib import Path
import re

DATA_PATH = Path(__file__).with_name('data') / 'china_divisions.json'
# Search accepts common simplified/traditional variants in Taiwan district names.
_VARIANTS = str.maketrans(dict(pair for pair in (
    '臺台','灣湾','縣县','區区','鄉乡','鎮镇','東东','義义','園园','壽寿','龍龙',
    '豐丰','橋桥','樹树','蘆芦','鶯莺','雙双','貢贡','龜龟','岡冈','鳳凤','蓮莲',
    '頭头','營营','學学','鹽盐','歸归','關关','廟庙','溝沟','後后','萬万','華华',
    '莊庄','蘭兰','員员','線线','塭塭','興兴','羅罗','濱滨','馬马','烏乌','嶺岭',
    '內内','獅狮','埔埔','瑪玛','復复','達达','霧雾','崙仑','褒褒','餉饷','彌弥',
    '來来','恆恒','滿满','長长','樂乐','環环','綠绿','寧宁','連连','嶼屿','嵵嵵',
    '紅红','魚鱼','澗涧','觀观','轄辖','聖圣','濟济','順顺','氹凼',
)))


def normalized(text):
    return text.translate(_VARIANTS).casefold()


@lru_cache(maxsize=1)
def registry():
    data = json.loads(DATA_PATH.read_text())
    nodes = {n['id']: n for n in data['nodes']}
    children = {}
    for node in data['nodes']:
        children.setdefault(node['parent'], []).append(node)
    return data, nodes, children


def options(parent=None):
    return [dict(id=n['id'], label=n['name']) for n in registry()[2].get(parent, [])]


def describe_location(location_id):
    _, nodes, _ = registry()
    node = nodes.get(location_id)
    if node is None or node['level'] != 'district':
        raise ValueError('请选择有效的出生区县')
    city = nodes[node['parent']]
    province = nodes[city['parent']]
    names = []
    for name in (province['name'], city['name'], node['name']):
        if not names or names[-1] != name:
            names.append(name)
    full_name = ' / '.join(names)
    country, zone = {
        'CN:710000': ('TW', 'Asia/Taipei'),
        'CN:810000': ('HK', 'Asia/Hong_Kong'),
        'CN:820000': ('MO', 'Asia/Macau'),
    }.get(province['id'], ('CN', 'Asia/Shanghai'))
    return dict(id=node['id'], name=full_name, display_name=node['name'], full_name=full_name,
                label=full_name, country=country, timezone=zone, region='domestic',
                group=province['id'], province_id=province['id'], city_id=city['id'],
                district_id=node['id'], longitude=node['longitude'], latitude=node['latitude'],
                whole_city=node.get('whole_city', False), coordinate_source=node['coordinate_source'])


@lru_cache(maxsize=1)
def all_locations():
    return tuple(describe_location(n['id']) for n in registry()[0]['nodes'] if n['level']=='district')


def search(query, country=''):
    terms = [normalized(t) for t in re.split(r'[\s/·]+', query.strip()) if t]
    return [dict(c) for c in all_locations()
            if (not country or c['country']==country)
            and all(term in normalized(c['full_name']) for term in terms)]


def picker(province='', city='', query=''):
    data, nodes, _ = registry()
    if province and (province not in nodes or nodes[province]['level']!='province'):
        raise ValueError('无效的省级地区')
    if city and (city not in nodes or nodes[city]['level']!='city' or nodes[city]['parent']!=province):
        raise ValueError('城市与所选省级地区不匹配')
    cities = options(province) if province else []
    if not city and len(cities)==1:
        city = cities[0]['id']
    districts = [describe_location(n['id']) for n in registry()[2].get(city, [])] if city else []
    return dict(provinces=options(), cities=cities, districts=districts,
                province_id=province, city_id=city, results=search(query) if query.strip() else [],
                counts=data['counts'], version=data['version'])


# Existing saved charts may contain GeoNames IDs. Keep restoring them without
# inserting those cities or the legacy overseas list into the new picker.
_LEGACY_PROVINCES = dict(zip(
    ('22','28','10','24','20','19','05','08','23','04','02','01','07','03','25','09',
     '12','11','30','16','31','33','32','18','29','14','26','15','06','21','13'),
    ('11','12','13','14','15','21','22','23','31','32','33','34','35','36','37','41',
     '42','43','44','45','46','50','51','52','53','54','61','62','63','64','65')))


def legacy_location(city_id):
    from .astrology import city_data, location
    city = city_data().get(str(city_id))
    if city is None:
        raise ValueError('请选择有效的出生区县')
    result = location(city_id)
    name = next((n for n in city.get('alternatenames', []) if n and
                 all('\u4e00' <= x <= '\u9fff' for x in n)), city['name'])
    code = _LEGACY_PROVINCES.get(city.get('admin1code')) if city['countrycode']=='CN' else {
        'TW':'71','HK':'81','MO':'82'}.get(city['countrycode'])
    result.update(display_name=name, full_name=name, legacy=True,
                  region='domestic' if code else 'overseas',
                  province_id='CN:'+code+'0000' if code else '', city_id='')
    return result
