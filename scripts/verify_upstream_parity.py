"""Compare the Python engine with frozen upstream TS output. No JS required."""
import gzip,json,sys
from collections import Counter
from datetime import date
from pathlib import Path
from ziwei.astrology import generate_chart
from ziwei.models import BirthLookup
FIELDS=('lunarInfo','mingGongBranch','shenGongBranch','wuxingJu','wuxingJuName','ziweiPos','daXians','currentAge','currentDaXianIndex','mingZhu','shenZhu','yinYangGender')
PALACE_FIELDS=('branch','stem','name','stars','daXianAge','isMingGong','isShenGong','isCurrentDaXian','oppositeBranch','isEmpty','borrowedFromBranch','borrowedFromName','borrowedStars')
def canonical(c):
    out={k:c.get(k) for k in FIELDS}
    out['palaces']=[]
    for p in sorted(c['palaces'],key=lambda p:p['branch']):
        q={k:p[k] for k in PALACE_FIELDS if k in p}
        q['stars']=sorted(q['stars'],key=lambda s:(s['name'],s['type']))
        out['palaces'].append(q)
    return out

def run(path):
    bundle=json.loads(gzip.decompress(Path(path).read_bytes()))
    failures=[];counts=Counter();reference_errors=[]
    for i,case in enumerate(bundle['cases']):
        inp=case['input']
        if 'error' in case:
            reference_errors.append(case);continue
        try:
            b=BirthLookup(**{k:v for k,v in inp.items() if k not in ('policy','school')}).to_birth()
            actual=canonical(generate_chart(b,inp['school'],inp['policy'],date(2026,11,9)))
            expected=canonical(case['expected'])
            if actual!=expected:
                diff=[k for k in actual if actual[k]!=expected[k]]
                for k in diff:counts[k]+=1
                if len(failures)<10:failures.append(dict(input=inp,different=diff,actual=actual,expected=expected))
        except Exception as e:
            counts['exception']+=1
            if len(failures)<10:failures.append(dict(input=inp,error=repr(e)))
    report=dict(ref=bundle['ref'],total=len(bundle['cases']),reference_errors=len(reference_errors),compared=len(bundle['cases'])-len(reference_errors),reference_error_cases=[x['input'] for x in reference_errors],mismatches=dict(counts),examples=failures)
    Path('/tmp/ziwei-parity-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='examples'},ensure_ascii=False))
    return report
if __name__=='__main__':
    report=run(sys.argv[1] if len(sys.argv)>1 else 'tests/fixtures/upstream-parity.json.gz')
    sys.exit(bool(report['mismatches']))
