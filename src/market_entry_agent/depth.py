"""Optional sequential research branches sharing one run's durable query/call budgets."""
import hashlib
import json
import re
from .notebook import text


def validate(mission):
    config=mission.get('research_depth')
    if config is None:return
    if not isinstance(config,dict) or set(config)-{'max_branches','max_queries_per_branch'}:raise ValueError('Invalid research_depth configuration')
    if not mission.get('public_search'):raise ValueError('Research branches require an explicit public_search scope')
    for key,default,maximum in [('max_branches',2,4),('max_queries_per_branch',2,3)]:
        number=config.get(key,default)
        if type(number) is not int or not 1<=number<=maximum:raise ValueError('Research depth budget outside bounds')


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS research_branches(run_id TEXT,id TEXT,revision INTEGER,data TEXT,PRIMARY KEY(run_id,id))')


def snapshot(store,rid):
    store.get_run(rid)
    with store.tasks() as db:
        initialize(db);rows=db.execute('SELECT * FROM research_branches WHERE run_id=? ORDER BY id',(rid,)).fetchall()
    return [dict(json.loads(row['data']),id=row['id'],revision=row['revision']) for row in rows]


def save(db,store,run,branch,expected):
    if run.get('_owner'):store.require_owner(db,run['id'],run['_owner'])
    old=db.execute('SELECT revision FROM research_branches WHERE run_id=? AND id=?',(run['id'],branch['id'])).fetchone()
    if (old[0] if old else 0)!=expected:raise ValueError('Research branch revision conflict')
    value=dict(branch,revision=expected+1)
    db.execute('INSERT OR REPLACE INTO research_branches VALUES(?,?,?,?)',(run['id'],branch['id'],value['revision'],json.dumps(value,ensure_ascii=False)))
    return value


def search(store,run,args,timeout):
    from .adaptive import search as public_search
    config=run['mission'].get('research_depth')
    if not config:raise ValueError('Research branches are not enabled')
    validate(run['mission']);bid=args.get('id')
    if not isinstance(bid,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',bid):raise ValueError('Research branch requires a stable ID')
    question=text(args.get('question'),1000)
    fingerprint=hashlib.sha256(json.dumps([args['term_ids'],args['facet_id']],sort_keys=True).encode()).hexdigest()
    with store.tasks() as db:
        initialize(db);db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT data FROM research_branches WHERE run_id=? AND id=?',(run['id'],bid)).fetchone()
        if row:branch=json.loads(row[0])
        else:
            if db.execute('SELECT COUNT(*) FROM research_branches WHERE run_id=?',(run['id'],)).fetchone()[0]>=config.get('max_branches',2):raise ValueError('Research branch budget exhausted')
            branch={'id':bid,'revision':0,'question':question,'state':'investigating','queries':[],'conclusion':'','evidence_ids':[],'stop_reason':''}
        if branch['question']!=question:raise ValueError('Branch question is immutable; use another ID within budget')
        if branch['state']=='closed':raise ValueError('Research branch already closed')
        query=next((q for q in branch['queries'] if q['fingerprint']==fingerprint),None)
        if query and query['state']=='completed':return {'branch':branch,'results':[store.read(eid) for eid in query['result_ids']],'reused':True}
        if not query:
            if len(branch['queries'])>=config.get('max_queries_per_branch',2):raise ValueError('Per-branch query budget exhausted')
            query={'fingerprint':fingerprint,'state':'pending','result_ids':[]};branch['queries'].append(query)
            branch=save(db,store,run,branch,branch['revision'])
    try:
        result=public_search(store,run,{k:args[k] for k in ('term_ids','facet_id','reason')},timeout)
    except ValueError as exc:
        query.update(state='failed',error=str(exc)[:180])
        with store.tasks() as db:
            db.execute('BEGIN IMMEDIATE');save(db,store,run,branch,branch['revision'])
        raise
    query.update(state='completed',result_ids=[r['id'] for r in result['results']])
    with store.tasks() as db:
        db.execute('BEGIN IMMEDIATE');branch=save(db,store,run,branch,branch['revision'])
    return {'branch':branch,'results':result['results'],'query_budget':result['query_budget'],'reused':False}


def close(store,run,args):
    if not run['mission'].get('research_depth'):raise ValueError('Research branches are not enabled')
    branch=next((b for b in snapshot(store,run['id']) if b['id']==args['id']),None)
    if not branch:raise ValueError('Unknown research branch')
    ids=args.get('evidence_ids',[])
    read={s['observation'].get('id') for s in run['steps'] if s['action']=='read_evidence' and 'error' not in s['observation']}
    if not isinstance(ids,list) or len(ids)>20 or any(eid not in read or store.read(eid).get('retrieval_kind')=='search_snippet' for eid in ids):raise ValueError('Branch conclusions cite only original evidence read in this run')
    value=dict(branch,state='closed',conclusion=text(args.get('conclusion')),stop_reason=text(args.get('stop_reason'),1000),evidence_ids=ids)
    if value==branch:return {'branch':branch}
    if branch['state']=='closed':raise ValueError('Closed branch conclusions are retained; start a new task to reassess')
    with store.tasks() as db:
        db.execute('BEGIN IMMEDIATE');value=save(db,store,run,value,args['expected_revision'])
    return {'branch':value}


def brief(branches):
    return [{'id':b['id'],'revision':b['revision'],'question':b['question'][:400],'state':b['state'],
             'queries_used':len(b['queries']),'conclusion':b['conclusion'][:600],'stop_reason':b['stop_reason'][:400],
             'evidence_ids':b['evidence_ids']} for b in branches]


def markdown(branches):
    if not branches:return []
    lines=['','## 研究分支 / Research branches','']
    for b in branches:
        lines+=['### '+b['question'],b['conclusion'] or '尚未形成分支结论。','状态：'+b['state']+'；已保存检索：'+str(len(b['queries'])),'取材停止原因：'+(b['stop_reason'] or '未记录'), '依据：'+', '.join(b['evidence_ids']),'']
    return lines
