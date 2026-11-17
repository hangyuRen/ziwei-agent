"""Build the vendored domestic hierarchy from reviewed source snapshots.

Inputs are downloaded separately; see src/ziwei/data/README.md. Runtime is offline.
Usage: python scripts/build_china_locations.py /tmp
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/tmp')
DEST = ROOT / 'src/ziwei/data'


def gcj_to_wgs(lng, lat):
    """Invert the GCJ-02 displacement for mainland reference coordinates."""
    def forward(lon, latitude):
        x, y = lon - 105, latitude - 35
        a = -100 + 2*x + 3*y + .2*y*y + .1*x*y + .2*math.sqrt(abs(x))
        a += (20*math.sin(6*x*math.pi)+20*math.sin(2*x*math.pi))*2/3
        a += (20*math.sin(y*math.pi)+40*math.sin(y/3*math.pi))*2/3
        a += (160*math.sin(y/12*math.pi)+320*math.sin(y*math.pi/30))*2/3
        b = 300 + x + 2*y + .1*x*x + .1*x*y + .1*math.sqrt(abs(x))
        b += (20*math.sin(6*x*math.pi)+20*math.sin(2*x*math.pi))*2/3
        b += (20*math.sin(x*math.pi)+40*math.sin(x/3*math.pi))*2/3
        b += (150*math.sin(x/12*math.pi)+300*math.sin(x/30*math.pi))*2/3
        rad = latitude / 180 * math.pi
        magic = 1 - .006693421622965943 * math.sin(rad)**2
        a = a*180 / ((6378245*(1-.006693421622965943))/(magic*math.sqrt(magic))*math.pi)
        b = b*180 / (6378245/math.sqrt(magic)*math.cos(rad)*math.pi)
        return lon+b, latitude+a
    wlng, wlat = lng, lat
    for _ in range(6):
        glng, glat = forward(wlng, wlat)
        wlng -= glng-lng
        wlat -= glat-lat
    return round(wlng, 6), round(wlat, 6)


def read_csv(name):
    csv.field_size_limit(20_000_000)
    with (SOURCE/name).open(encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def taiwan_centers(topology):
    scale, translate = topology['transform']['scale'], topology['transform']['translate']
    arcs = []
    for arc in topology['arcs']:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x*scale[0]+translate[0], y*scale[1]+translate[1]))
        arcs.append(points)
    for geometry in topology['objects']['towns']['geometries']:
        polygons = geometry['arcs'] if geometry['type']=='MultiPolygon' else [geometry['arcs']]
        candidates = []
        for polygon in polygons:
            ring = []
            for index in polygon[0]:
                segment = arcs[index] if index >= 0 else list(reversed(arcs[~index]))
                ring.extend(segment if not ring else segment[1:])
            if ring[-1] != ring[0]:
                ring.append(ring[0])
            area = cx = cy = 0
            for (x1,y1),(x2,y2) in zip(ring,ring[1:]):
                cross = x1*y2-x2*y1
                area += cross
                cx += (x1+x2)*cross
                cy += (y1+y2)*cross
            if area:
                candidates.append((abs(area),cx/(3*area),cy/(3*area)))
        _, lng, lat = max(candidates)
        yield geometry['properties'], round(lng,6), round(lat,6)


def build():
    names = json.loads((SOURCE/'mumuy-list.json').read_text())
    geo = {r['id']:r for r in read_csv('ok_geo.csv') if r['geo']!='EMPTY'}
    coordinates = {}
    for row in read_csv('ok_data_level3.csv'):
        if row['id'] in geo:
            code = row['ext_id'][:6]
            if code not in coordinates or len(row['id']) == 6:
                coordinates[code] = gcj_to_wgs(*map(float,geo[row['id']]['geo'].split()))

    # New divisions absent from the April 2026 coordinate snapshot. References
    # and accuracy are recorded in README; no prefecture coordinates are substituted.
    supplemental = {
        '653132': (76.662639,36.398831),  # 新华镇，岑岭县驻地
        '653228': (78.03,36.3517),       # 昆岭镇，和康县驻地
        '653229': (79.1944,35.9794),     # 红柳镇，和安县驻地
        '659013': (76.037922,39.252893), # 草湖建成区，官方道路工程参考点
    }
    coordinates.update(supplemental)
    nodes = {}

    def add(code,name,parent,level,point=None,source=None):
        assert code not in nodes, code
        node = dict(id=code,name=name,parent=parent,level=level)
        if point:
            node.update(longitude=point[0],latitude=point[1],coordinate_source=source)
        nodes[code] = node

    # Mainland, HK, MO names/IDs are maintained as an independent registry.
    for code,name in names.items():
        if code.startswith('83') or not code.endswith('0000'):
            continue
        add('CN:'+code,name,None,'province')
    add('CN:710000','台湾省',None,'province')

    municipalities = {'11','12','31','50','81','82'}
    for code,name in names.items():
        if code.startswith('83') or code.endswith('0000'):
            continue
        province = 'CN:'+code[:2]+'0000'
        if code.endswith('00'):
            add('CN:'+code,name,province,'city')

    for code,name in names.items():
        if code.startswith('83') or code.endswith('00'):
            continue
        province = 'CN:'+code[:2]+'0000'
        city = 'CN:'+code[:4]+'00'
        if code[:2] in municipalities:
            city = 'CN:'+code[:2]+'0100'
            if city not in nodes:
                add(city,nodes[province]['name'],province,'city')
        elif city not in nodes:
            assert code[2:4]=='90', (code,name)
            add(city,'自治区直辖县级行政区划' if code[:2]=='65' else '省直辖县级行政区划',province,'city')
        point = coordinates.get(code)
        if code.startswith(('81','82')):
            continue  # Separate name matching below: map-provider IDs differ.
        assert point, (code,name)
        add('CN:'+code,name,city,'district',point,'supplemental' if code in supplemental else 'areacity_gcj02_to_wgs84')

    for prefix,filename in [('81','hk-geo.json'),('82','mo-geo.json')]:
        features = json.loads((SOURCE/filename).read_text())['features']
        points = {f['properties']['name']:f['properties']['center'] for f in features}
        points['圣安多尼堂区'] = points.get('花王堂区')
        points['路氹城'] = points.get('路凼填海区')
        # The new reclamation zones span several sites; use the A-zone reference.
        points['澳门新城'] = [113.58,22.20]
        for code,name in names.items():
            if code.startswith(prefix) and not code.endswith('00'):
                point = points[name]
                add('CN:'+code,name,'CN:'+prefix+'0100','district',point,
                    'macau_new_zone_reference' if name=='澳门新城' else 'datav_district_center')

    # Cities without county subdivisions stay selectable as "全市（不设区县）".
    for node in list(nodes.values()):
        if node['level']=='city' and not any(r['parent']==node['id'] for r in nodes.values()):
            point = coordinates.get(node['id'][3:])
            assert point, node
            add(node['id']+':all',node['name'],node['id'],'district',point,'areacity_gcj02_to_wgs84')
            nodes[node['id']+':all']['whole_city'] = True

    # Taiwan's 368 townships/districts and all 22 counties/cities, including islands.
    topology = json.loads((SOURCE/'taiwan-towns.json').read_text())
    for props,lng,lat in taiwan_centers(topology):
        city = 'TW:'+props['COUNTYCODE']
        if city not in nodes:
            add(city,props['COUNTYNAME'],'CN:710000','city')
        add('TW:'+props['TOWNCODE'],props['TOWNNAME'],city,'district',(lng,lat),'taiwan_moi_boundary_centroid_wgs84')

    for node in nodes.values():
        if node['level']=='district':
            assert node['parent'] in nodes
            assert 73 < node['longitude'] < 136 and 3 < node['latitude'] < 54,node
        if node['parent']:
            assert node['parent'] in nodes
    provinces = [r for r in nodes.values() if r['level']=='province']
    assert len(provinces)==34
    counts = {level:sum(r['level']==level for r in nodes.values()) for level in ('province','city','district')}
    result = dict(version='2026-11-10',counts=counts,
        source_sha256={name:hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in
            ('mumuy-list.json','ok_data_level3.csv','ok_geo.csv','hk-geo.json','mo-geo.json','taiwan-towns.json')},
        nodes=sorted(nodes.values(),key=lambda r:r['id']))
    DEST.mkdir(exist_ok=True)
    (DEST/'china_divisions.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    (DEST/'division_names_snapshot.json').write_text(json.dumps(names,ensure_ascii=False,separators=(',',':'))+'\n')
    township_names = [{k:p[k] for k in ('COUNTYCODE','COUNTYNAME','TOWNCODE','TOWNNAME')}
                      for p,_,_ in taiwan_centers(topology)]
    (DEST/'taiwan_townships_snapshot.json').write_text(json.dumps(township_names,ensure_ascii=False,separators=(',',':'))+'\n')
    for source,target in [('mumuy-license','LICENSE-mumuy.txt'),('areacity-license','LICENSE-AreaCity.txt'),('taiwan-license','LICENSE-taiwan-atlas.txt')]:
        (DEST/target).write_text((SOURCE/source).read_text())
    print(counts)


if __name__=='__main__':
    build()
