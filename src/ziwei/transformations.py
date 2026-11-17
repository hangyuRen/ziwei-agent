"""Python port of upstream sihua.ts; natal placements are shared by all views.

Renhuai123/ziwei-doushu, MIT, commit 7922285d947b36610e7e31c232d8f1e2a0d0871d.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

REFERENCE = '7922285d947b36610e7e31c232d8f1e2a0d0871d'
STEMS = '甲乙丙丁戊己庚辛壬癸'
KINDS = ('禄', '权', '科', '忌')
# constants.ts SI_HUA_TABLE, including 戊右弼科、庚太阴科、壬左辅科.
SI_HUA_TABLE = (
    ('廉贞', '破军', '武曲', '太阳'),
    ('天机', '天梁', '紫微', '太阴'),
    ('天同', '天机', '文昌', '廉贞'),
    ('太阴', '天同', '天机', '巨门'),
    ('贪狼', '太阴', '右弼', '天机'),
    ('武曲', '贪狼', '天梁', '文曲'),
    ('太阳', '武曲', '太阴', '天同'),
    ('巨门', '太阳', '文曲', '文昌'),
    ('天梁', '紫微', '左辅', '武曲'),
    ('破军', '巨门', '太阴', '贪狼'),
)


def get_si_hua_by_stem(stem):
    if type(stem) is not int or not 0 <= stem < 10:
        raise ValueError('天干索引必须为 0–9 的整数')
    return dict(zip(KINDS, SI_HUA_TABLE[stem]))


def detect_self_sihua(palace):
    names = {s['name'] for s in palace['stars']}
    return [dict(siHua=kind, starName=star) for kind, star in get_si_hua_by_stem(palace['stem']).items()
            if star in names]


def find_incoming_palaces(chart, star_name, kind):
    if kind not in KINDS:
        raise ValueError('无效的四化类型')
    return [p for p in chart['palaces'] if get_si_hua_by_stem(p['stem'])[kind] == star_name]


def build_transformations(chart, year=None):
    """48 directed palace-stem flights, self transforms, natal/decadal/annual layers.

    A flight changes the transformation relationship, never the star's palace.
    Repeated palace stems retain every source, as findIncomingPalaces does upstream.
    """
    year = year if year is not None else datetime.now(ZoneInfo('Asia/Shanghai')).year
    if type(year) is not int or not 1800 <= year <= 2200:
        raise ValueError('流年年份仅支持 1800–2200')
    by_branch = {p['branch']: p for p in chart['palaces']}
    star_palaces = {s['name']: p for p in chart['palaces'] for s in p['stars']}

    def layer(stem):
        transforms = get_si_hua_by_stem(stem)
        placements = []
        for kind, star in transforms.items():
            target = star_palaces.get(star)
            if target is None:
                raise ValueError(f'命盘缺少四化星：{star}')
            placements.append(dict(siHua=kind, starName=star,
                                   targetBranch=target['branch'], targetPalace=target['name']))
        return dict(stemIndex=stem, stemName=STEMS[stem], transforms=transforms, placements=placements)

    flights = []
    self_sihua = {}
    for palace in chart['palaces']:
        for target in layer(palace['stem'])['placements']:
            flights.append(target | dict(sourceBranch=palace['branch'], sourcePalace=palace['name'],
                stemIndex=palace['stem'], stemName=STEMS[palace['stem']],
                self=palace['branch']==target['targetBranch']))
        found = detect_self_sihua(palace)
        if found:
            self_sihua[str(palace['branch'])] = found
    decades = []
    for index, decade in enumerate(chart['daXians']):
        palace = by_branch[decade['palaceBranch']]
        decades.append(dict(index=index, **decade, **layer(palace['stem'])))
    return dict(reference=REFERENCE, natal=layer(chart['lunarInfo']['yearStem']),
                daXians=decades, annual=dict(year=year, **layer((year-4) % 10)),
                flyingStars=flights, selfSihua=self_sihua)
