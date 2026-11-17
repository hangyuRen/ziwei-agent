"""Pure Python natal chart and apparent solar time. No JS runtime."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from functools import lru_cache
import math
import geonamescache
from iztro_py import astro
from iztro_py.i18n import t

@lru_cache(maxsize=1)
def city_data():
    return geonamescache.GeonamesCache().get_cities()

def location(city_id):
    if str(city_id).startswith(('CN:', 'TW:')):
        from .locations import describe_location
        return describe_location(str(city_id))
    c = city_data().get(str(city_id))
    if c is None:
        raise ValueError('请选择有效的出生城市')
    return dict(id=str(c['geonameid']), name=c['name'], country=c['countrycode'],
                longitude=c['longitude'], timezone='Asia/Shanghai' if c['countrycode']=='CN' else c['timezone'])

def search_locations(query='', region='domestic', country=''):
    query=query.strip().casefold()
    result=[]
    for c in city_data().values():
        domestic=c['countrycode'] in ('CN','HK','MO','TW')
        if (region=='domestic') != domestic or (country and c['countrycode']!=country): continue
        names=[c['name'],*c.get('alternatenames',[])]
        if query and not any(query in n.casefold() for n in names): continue
        result.append(c)
    result.sort(key=lambda c:-c['population'])
    out=[]
    for c in result[:60]:
        item=location(c['geonameid'])
        cn=next((n for n in c.get('alternatenames',[]) if any('\u4e00'<=x<='\u9fff' for x in n)),None)
        item['label']=f"{cn or c['name']} / {c['name']} · {c['countrycode']}"
        out.append(item)
    return out

def correct_time(year,month,day,hour,minute,city_id,fold=0):
    place=location(city_id)
    naive=datetime(year,month,day,hour,minute)
    zone=ZoneInfo(place['timezone'])
    aware=naive.replace(tzinfo=zone,fold=fold)
    if aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=naive:
        raise ValueError('该时间处于夏令时跳时空档，请核对出生记录')
    offset=aware.utcoffset().total_seconds()/60
    n=naive.timetuple().tm_yday
    days=366 if year%4==0 and (year%100!=0 or year%400==0) else 365
    gamma=2*math.pi/days*(n-1+(hour+minute/60-12)/24)
    eot=229.18*(.000075+.001868*math.cos(gamma)-.032077*math.sin(gamma)-.014615*math.cos(2*gamma)-.040849*math.sin(2*gamma))
    longitude_minutes=4*place['longitude']-offset
    solar=naive+timedelta(seconds=round((longitude_minutes+eot)*60))
    branch=((solar.hour+1)//2)%12
    chart_date=solar.date()+timedelta(days=1 if solar.hour==23 else 0)
    ambiguous=naive.replace(tzinfo=zone,fold=0).utcoffset()!=naive.replace(tzinfo=zone,fold=1).utcoffset()
    return dict(location=place,clock_time=naive.isoformat(),utc_offset_minutes=offset,
        dst_minutes=aware.dst().total_seconds()/60,longitude_correction_minutes=longitude_minutes,
        equation_of_time_minutes=eot,total_correction_minutes=longitude_minutes+eot,
        true_solar_time=solar.isoformat(),chart_date=chart_date.isoformat(),branch=branch,
        late_zi_rule='next-day',ambiguous_clock_time=ambiguous,fold=fold)

def generate_chart(birth, brightness_school="QS", leap_month_policy="split", as_of=None, transformation_year=None):
    if type(birth.hour) is not int or not 0 <= birth.hour <= 11:
        raise ValueError('时辰索引必须为 0–11 的整数')
    if birth.gender not in ('male','female'):
        raise ValueError('性别必须为 male 或 female')
    from .school_rules import effective_lunar, apply_rules
    effective=effective_lunar(birth.year,birth.month,birth.day,leap_month_policy)
    if brightness_school not in ('QS','XD1','ZZ','XD2'):
        raise ValueError('无效的星曜亮度流派')
    chart=astro.by_solar(f'{birth.year}-{birth.month}-{birth.day}',birth.hour,
        '男' if birth.gender=='male' else '女',True,'zh-CN')
    if leap_month_policy!='split' and effective['rawLunarMonth']<0:
        chart=astro.by_lunar(f"{effective['lunarYear']}-{effective['lunarMonth']}-{effective['lunarDay']}",birth.hour,
            '男' if birth.gender=='male' else '女',effective['isLeapMonth'],False,'zh-CN')
    def translate(value):
        if isinstance(value,dict): return {k:translate(v) for k,v in value.items()}
        if isinstance(value,list): return [translate(v) for v in value]
        if isinstance(value,str):
            for prefix in ('', 'palaces.', 'stars.major.', 'stars.minor.', 'heavenlyStem.', 'earthlyBranch.'):
                translated=t(prefix+value,'zh-CN')
                if translated != prefix+value: return translated
            return value
        return value
    data=translate(chart.model_dump(mode='json'))
    result = apply_rules(data,birth,brightness_school,leap_month_policy,as_of)
    from .transformations import build_transformations
    result['transformations'] = build_transformations(result, transformation_year if transformation_year is not None else (as_of.year if as_of else None))
    return result
