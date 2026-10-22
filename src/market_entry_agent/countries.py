"""Public World Bank country baselines; calculations stay separate from events."""
from __future__ import annotations
import copy
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

# Common user spellings; authoritative identity remains the source economy code.
ALIASES = {
 'VNM':['VN','Vietnam','越南'], 'IDN':['ID','印度尼西亚','印尼'], 'ARE':['AE','UAE','阿联酋'],
 'USA':['US','United States','美国'], 'GBR':['GB','UK','United Kingdom','英国'], 'CHN':['CN','中国'],
 'IND':['IN','印度'], 'JPN':['JP','日本'], 'KOR':['KR','South Korea','韩国'], 'DEU':['DE','德国'],
 'FRA':['FR','法国'], 'BRA':['BR','巴西'], 'MEX':['MX','墨西哥'], 'MYS':['MY','马来西亚'],
 'SGP':['SG','新加坡'], 'THA':['TH','泰国'], 'PHL':['PH','菲律宾'], 'KHM':['KH','柬埔寨'],
 'SAU':['SA','沙特','沙特阿拉伯'], 'ZAF':['ZA','南非'], 'KEN':['KE','肯尼亚'], 'NGA':['NG','尼日利亚'],
 'AUS':['AU','澳大利亚'], 'CAN':['CA','加拿大'], 'TUR':['TR','Turkey','土耳其'], 'RUS':['RU','俄罗斯'],
 'UKR':['UA','乌克兰'], 'EGY':['EG','埃及'], 'PAK':['PK','巴基斯坦'], 'BGD':['BD','孟加拉国'],
 'NZL':['NZ','新西兰'], 'NLD':['NL','荷兰'], 'POL':['PL','波兰'], 'ESP':['ES','西班牙'],
 'ITA':['IT','意大利'], 'CHL':['CL','智利'], 'PER':['PE','秘鲁'], 'COL':['CO','哥伦比亚']}

def key(value):
    return re.sub(r'[\s_\-.,]+', '', str(value)).casefold()

@lru_cache(maxsize=1)
def dataset():
    return json.loads(Path(__file__).with_name('data').joinpath('country-baselines.json').read_text(encoding='utf-8'))

def lookup(value):
    sought=key(value)
    for row in dataset()['countries']:
        if sought in {key(x) for x in [row['code'], row['name'], *ALIASES.get(row['code'],[])]}:
            return row
    raise ValueError('Unknown country. Use an economy code or name from country-list.')

@lru_cache(maxsize=2048)
def scope_key(value):
    try:
        return lookup(value)['code']
    except ValueError:
        return key(value)


def scope_keys(values):
    return {scope_key(value) for value in values}


def matches(values, code):
    for value in values:
        try:
            if lookup(value)['code']==code: return True
        except ValueError:
            continue
    return False

def mean(values):
    return sum(values)/len(values) if values else None

def baseline(country):
    row=copy.deepcopy(lookup(country)); meta=dataset()
    wgi=row['wgi']; bready=row['bready']; complete=len(wgi)==6
    wg=mean([d['value'] for d in wgi.values()]) if complete else None
    br=mean([p['value'] for p in bready['pillars']]) if bready else None
    mode='combined' if complete and br is not None else 'wgi_only' if complete else 'incomplete'
    total=.6*br+.4*wg if mode=='combined' else wg
    row.update({'reference_score':round(total,4) if total is not None else None,'wgi_mean':round(wg,4) if wg is not None else None,'bready_mean':round(br,4) if br is not None else None,
                'formula_mode':mode,'coverage':{'wgi_dimensions':len(wgi),'bready_pillars':3 if bready else 0,'bready_topics':len(bready['topics']) if bready else 0},
                'coverage_label':{'combined':'双源研究参考','wgi_only':'仅治理观察','incomplete':'分项覆盖不全'}[mode],
                'as_of':meta['as_of'],'available_from':meta['available_from'],'period':'2025','method_version':meta['method_version'],'event_adjustment':None,'change':None})
    contributions=[]
    if complete:
        weight=.4/6 if mode=='combined' else 1/6
        contributions += [{'source':'wgi2026','label':v['label'],'value':v['value'],'weight':weight,'contribution':v['value']*weight} for v in wgi.values()]
    if mode=='combined':
        contributions += [{'source':'bready2025','label':p['label'],'value':p['value'],'weight':.6/3,'contribution':p['value']*.6/3} for p in bready['pillars']]
    row['contributions']=contributions
    row['sources']=copy.deepcopy(meta['sources']); row['limitations']=list(meta['limitations'])
    return row

def catalog():
    meta=dataset()
    rows=[baseline(c['code']) for c in meta['countries']]
    return {'as_of':meta['as_of'],'method_version':meta['method_version'],'period':'2025','limitations':meta['limitations'],'formula':meta['formula'],'sources':meta['sources'],
            'coverage':{'economies':len(rows),'combined':sum(r['formula_mode']=='combined' for r in rows),'wgi_only':sum(r['formula_mode']=='wgi_only' for r in rows),'incomplete':sum(r['formula_mode']=='incomplete' for r in rows)},
            'countries':[{k:r[k] for k in ('code','name','region','income_group','reference_score','formula_mode','coverage_label','coverage')} for r in rows]}

def compare(countries):
    if not isinstance(countries,list) or not 1<=len(countries)<=5 or not all(isinstance(c,str) for c in countries):
        raise ValueError('Choose one to five countries')
    rows=[baseline(c) for c in countries]
    if len({r['code'] for r in rows})!=len(rows): raise ValueError('Choose distinct countries')
    same=len({(r['formula_mode'],r['period'],r['method_version']) for r in rows})==1 and all(r['reference_score'] is not None for r in rows)
    common=set.intersection(*(set(r['wgi']) for r in rows))
    points=[]
    for dim in sorted(common):
        values={r['code']:r['wgi'][dim]['value'] for r in rows}
        maximum=max(values.values())
        points.append({'dimension':dim,'label':rows[0]['wgi'][dim]['label'],'values':values,'higher_point_estimate':[code for code,value in values.items() if value==maximum],'interpretation':'Point estimates only; no significance test or country suitability ranking'})
    return {'countries':rows,'common_wgi':points,'same_basis':same,'ranking':None,'note':'同口径分项可比较，细微分差不构成统计显著或企业选国结论。' if same else '覆盖或公式不同，不合并排序；请对照共同分项和各自缺口。','event_adjustment':None}

def evidence(store, countries, mission):
    result=compare(countries)
    for row in result['countries']:
        if not matches(mission['countries'],row['code']): raise ValueError('Country baseline outside mission scope')
    if mission.get('as_of'):
        stamp=datetime.fromisoformat(mission['as_of'].replace('Z','+00:00'))
        cutoff=stamp.replace(tzinfo=stamp.tzinfo or timezone.utc)
        if cutoff<datetime.fromisoformat(dataset()['available_from']):
            raise ValueError('Current country snapshot was not available at historical as_of; use a versioned historical dataset')
    records=[]
    for row in result['countries']:
        records.append({'title':row['name']+' · 国区营商环境研究参考基线','body':json.dumps(row,ensure_ascii=False),'url':row['sources'][0]['url'],
                        'countries':[row['code'],row['name'],*ALIASES.get(row['code'],[])],
                        'topics':['country-baseline','governance','investment','trade','logistics','risk','opportunity'],
                        'published_at':row['available_from'],'data_period':row['period'],'method_version':row['method_version'],'upstream_sources':row['sources'],'status':'source_claim','retrieval_kind':'country_baseline',
                        'date_basis':'Public derivative snapshot available_from, not observation period','event_key':'country-baseline:'+row['method_version']+':'+row['code']})
    store.import_evidence({'schema':'field-evidence/v1','records':records})
    imported=store.export_evidence()['records']
    ids=[r['id'] for record in records for r in imported if r.get('event_key')==record['event_key'] and r['body']==record['body']]
    return {'formula':dataset()['formula'],'source_weights':{'bready2025':0.60,'wgi2026':0.40},'comparison':result,'evidence_ids':ids,'next':'Use read_evidence for every ID you cite; this is a research derivative, not World Bank endorsement or live risk.'}

def dashboard(store, country):
    row=baseline(country); records=store.export_evidence()['records']
    events=[]
    for item in records:
        if item.get('synthetic') or item.get('retrieval_kind')=='country_baseline' or not matches(item['countries'],row['code']): continue
        stamp=item.get('published_at'); freshness='unknown'
        if stamp:
            try:
                from email.utils import parsedate_to_datetime
                try: dt=datetime.fromisoformat(stamp.replace('Z','+00:00'))
                except ValueError: dt=parsedate_to_datetime(stamp)
                age=(datetime.now(timezone.utc)-dt.replace(tzinfo=dt.tzinfo or timezone.utc)).total_seconds()/86400
                freshness='recent' if 0<=age<=45 else 'future_date' if age<0 else 'older'
            except (ValueError,TypeError): pass
        events.append({k:item.get(k) for k in ('id','title','url','published_at','observed_at','retrieval_kind','status','topics')}|{'freshness':freshness})
    events.sort(key=lambda x:x.get('observed_at') or '',reverse=True)
    runs=[{k:r[k] for k in ('id','state','created','mission')}|{'summary':(r.get('report') or {}).get('summary'),'watchpoints':(r.get('report') or {}).get('watchpoints',[])} for r in store.list_runs() if matches(r['mission']['countries'],row['code'])]
    return {'baseline':row,'evidence':events[:30],'research':runs[:12],'coverage_note':'只列当前工作空间实际导入/抓取的公开资料；空列表不表示没有风险或机会。','event_adjustment':None}
