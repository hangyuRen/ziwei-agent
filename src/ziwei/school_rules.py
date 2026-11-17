"""Python port of upstream generateChart rules; tables pinned in school_tables."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from lunar_python import Solar, LunarMonth
from .school_tables import TABLES
BRANCHES=list('子丑寅卯辰巳午未申酉戌亥')
STEMS=list('甲乙丙丁戊己庚辛壬癸')
POLICIES=('split','next-month','prev-month','origin-month')

def effective_lunar(year,month,day,policy='split'):
    if policy not in POLICIES: raise ValueError('无效的闰月归属规则')
    lunar=Solar.fromYmd(year,month,day).getLunar()
    raw_month=lunar.getMonth(); raw_day=lunar.getDay(); ly=lunar.getYear()
    lm=abs(raw_month); leap=False; ld=raw_day
    if raw_month<0:
        if policy=='next-month' or (policy=='split' and raw_day>15): lm+=1
        elif policy=='origin-month': leap=True
        if lm>12: lm=1;ly+=1
        info=LunarMonth.fromYm(ly,-lm if leap else lm)
        if info: ld=min(ld,info.getDayCount())
    return dict(lunarYear=ly,lunarMonth=lm,lunarDay=ld,isLeapMonth=leap,rawLunarMonth=raw_month,rawLunarDay=raw_day)

def lunar_info(birth,policy):
    lu=Solar.fromYmd(birth.year,birth.month,birth.day).getLunar()
    effective=effective_lunar(birth.year,birth.month,birth.day,policy)
    ys=STEMS.index(lu.getYearGan());yb=BRANCHES.index(lu.getYearZhi())
    ec=Solar.fromYmdHms(birth.year,birth.month,birth.day,birth.hour*2,0,0).getLunar().getEightChar()
    dg=lu.getDayGan()+lu.getDayZhi();ds=STEMS.index(lu.getDayGan())
    tg=STEMS[((ds%5)*2+birth.hour)%10]+BRANCHES[birth.hour]
    m=effective['lunarMonth'];mg=STEMS[((ys%5)*2+2+m-1)%10]+BRANCHES[(m+1)%12]
    return {k:effective[k] for k in ('lunarYear','lunarMonth','lunarDay','isLeapMonth')} | dict(yearStem=ys,yearBranch=yb,fourPillars=[ec.getYear(),ec.getMonth(),dg,tg],fourPillarsLunar=[STEMS[ys]+BRANCHES[yb],mg,dg,tg])

def brightness(name,branch,school):
    sid={'副截':77,'旬空':78}.get(name,TABLES['star_ids'].get(name))
    if sid is None:return None
    val=TABLES['brightness'][school][sid][branch+1]
    labels={1:'庙',2:'旺',3:'得',4:'利',5:'平',6:'不',7:'陷'} if school in ('QS','XD1') else {1:'庙',2:'旺',3:'平',4:'闲',5:'陷'}
    return labels.get(val)

def star_type(name,kind):
    if name in TABLES['sha_stars']:return 'sha'
    if name in TABLES['lucky_stars']:return 'lucky'
    if kind in ('主星','major'):return 'major'
    if kind in ('煞星','tough'):return 'sha'
    if kind in ('吉星','soft','禄存','天马'):return 'lucky'
    return 'minor'

def apply_rules(data,birth,school='QS',policy='split',as_of=None):
    if school not in TABLES['brightness']:raise ValueError('无效的星曜亮度流派')
    info=lunar_info(birth,policy);palaces=data['palaces'];ys=info['yearStem'];yb=info['yearBranch']
    def set_brightness(star,branch):
        raw=brightness(star['name'],branch,school)
        star.pop('brightnessRaw',None);star.pop('brightness',None)
        if raw:
            star['brightnessRaw']=raw
            star['brightness']='bright' if raw in ('庙','旺') else 'dim' if raw in ('陷','不','闲') else 'normal'
    for p in palaces:
        if p['name']!='命宫' and p['name'].endswith('宫'):p['name']=p['name'][:-1]
        if p['name']=='交友':p['name']='仆役'
        p['branch']=BRANCHES.index(p['earthly_branch']);p['stem']=STEMS.index(p['heavenly_stem'])
        p['stars']=[]
        for group in ('major_stars','minor_stars','adjective_stars'):
            for s in p[group]:
                star=dict(name=s['name'],type='major' if group=='major_stars' else star_type(s['name'],s['type']))
                if group=='major_stars' or s['name'] in ('文昌','文曲','左辅','右弼'):star['siHua']=s.get('mutagen') or ''
                elif s.get('mutagen'):star['siHua']=s['mutagen']
                set_brightness(star,p['branch']);p['stars'].append(star)
        for name in (p.get('suiqian12'),p.get('jiangqian12')):
            if name in ('劫煞','龙德'):p['stars'].append(dict(name=name,type=star_type(name,'')))
        p['isMingGong']=p['name']=='命宫';p['isShenGong']=p['is_body_palace']
        if p.get('decadal'):p['daXianAge']=p['decadal']['range']
    by_branch={p['branch']:p for p in palaces}
    def find(name):return next(((p,s) for p in palaces for s in p['stars'] if s['name']==name),None)
    def relocate(name,branch):
        found=find(name)
        if found is None:return
        p,s=found
        if p['branch']==branch:return
        p['stars'].remove(s);by_branch[branch]['stars'].append(s);set_brightness(s,branch)
    def push(name,branch):
        p=by_branch[branch]
        if any(s['name']==name for s in p['stars']):return
        s=dict(name=name,type=star_type(name,''));set_brightness(s,branch);p['stars'].append(s)
    ky=TABLES['kuiyue'][ys+1]
    relocate('天魁',ky[0]-1);relocate('天钺',ky[1]-1)
    for p in palaces:
        for s in p['stars']:
            if s['name'] in ('截路','空亡'):
                s['name']={'截路':'截空','空亡':'副截'}[s['name']];set_brightness(s,p['branch'])
    if ys%2:
        a=find('截空');b=find('副截')
        if a and b and a[0] is not b[0]:
            ap,ast=a;bp,bst=b
            ap['stars'].remove(ast);bp['stars'].remove(bst)
            bp['stars'].append(ast);ap['stars'].append(bst)
            set_brightness(ast,bp['branch']);set_brightness(bst,ap['branch'])
    push('大耗',(yb+6+(1 if yb%2==0 else -1))%12)
    xun=find('旬空')
    if xun:push('副旬',(xun[0]['branch']+(1 if xun[0]['branch']%2==0 else -1))%12)
    today=as_of or datetime.now(ZoneInfo('Asia/Shanghai')).date()
    target_lunar=Solar.fromYmd(today.year,today.month,today.day).getLunar()
    birth_lunar=Solar.fromYmd(birth.year,birth.month,birth.day).getLunar()
    age=target_lunar.getYear()-birth_lunar.getYear()+1
    for p in palaces:
        p['isCurrentDaXian']=bool(p.get('daXianAge') and p['daXianAge'][0]<=age<=p['daXianAge'][1])
        p['oppositeBranch']=(p['branch']+6)%12
        p['isEmpty']=not any(s['type']=='major' for s in p['stars'])
        if p['isEmpty']:
            opp=by_branch[p['oppositeBranch']]
            p.update(borrowedFromBranch=opp['branch'],borrowedFromName=opp['name'],borrowedStars=[s['name'] for s in opp['stars'] if s['type']=='major'])
        p['major_stars']=[dict(s,brightness=s.get('brightnessRaw'),mutagen=s.get('siHua')) for s in p['stars'] if s['type']=='major']
        p['minor_stars']=[dict(s,brightness=s.get('brightnessRaw'),mutagen=s.get('siHua')) for s in p['stars'] if s['type']!='major']
        p['adjective_stars']=[]
    ming=BRANCHES.index(data['earthly_branch_of_soul_palace']);shen=BRANCHES.index(data['earthly_branch_of_body_palace'])
    dx=[dict(startAge=p['daXianAge'][0],endAge=p['daXianAge'][1],palaceBranch=p['branch'],palaceName=p['name']) for p in palaces if p.get('daXianAge')]
    dx.sort(key=lambda d:d['startAge'])
    ming_zhu=['贪狼','巨门','禄存','文曲','廉贞','武曲','破军','武曲','廉贞','文曲','禄存','巨门'][ming]
    shen_zhu=['火星','天相','天梁','天同','文昌','天机','火星','天相','天梁','天同','文昌','天机'][yb]
    ziwei=next(p['branch'] for p in palaces if any(s['name']=='紫微' for s in p['stars']))
    ju=next(n for n,ch in ((2,'二'),(3,'三'),(4,'四'),(5,'五'),(6,'六')) if ch in data['five_elements_class'])
    data.update(lunarInfo=info,mingGongBranch=ming,shenGongBranch=shen,wuxingJu=ju,wuxingJuName=data['five_elements_class'],ziweiPos=ziwei,
        daXians=dx,currentAge=age,currentDaXianIndex=next((i for i,d in enumerate(dx) if d['startAge']<=age<=d['endAge']),-1),
        mingZhu=ming_zhu,shenZhu=shen_zhu,yinYangGender=('阳' if ys%2==0 else '阴')+('男' if birth.gender=='male' else '女'),soul=ming_zhu,body=shen_zhu)
    data['engine']='ziwei-python-upstream-'+TABLES['ref'][:12]
    data['conventions']=dict(leap_month=policy,late_zi='next-day',brightness=school,upstream_commit=TABLES['ref'],
        interpretation_note='v4.0 解读按 2026-10-15 旧亮度表预生成，当前上游默认 QS 亮度可能不同')
    return data
