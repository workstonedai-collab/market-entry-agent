"""Bounded public-term search composition. Private prose never becomes a query."""
import hashlib
import json


def validate(mission):
    config=mission.get('public_search')
    if config is None:return
    if not isinstance(config,dict) or set(config)-{'terms','facets','max_queries'}:raise ValueError('Invalid public_search configuration')
    for key,maximum in [('terms',40),('facets',20)]:
        values=config.get(key,[])
        if not isinstance(values,list) or not 1<=len(values)<=maximum or any(not isinstance(v,str) or not v.strip() or len(v)>120 for v in values):raise ValueError('Public search requires bounded, explicitly public terms and facets')
    cap=config.get('max_queries',6)
    if type(cap) is not int or not 1<=cap<=12:raise ValueError('Public search query budget must be 1–12')


def search(store,run,args,timeout):
    from .net import search_query
    config=run['mission'].get('public_search')
    if not config:raise ValueError('Adaptive public search is not enabled for this mission')
    validate(run['mission'])
    indices=args.get('term_ids');facet=args.get('facet_id')
    if not isinstance(indices,list) or not 1<=len(indices)<=5 or any(type(i) is not int or not 0<=i<len(config['terms']) for i in indices):raise ValueError('Choose 1–5 indices from the public term list')
    if type(facet) is not int or not 0<=facet<len(config['facets']):raise ValueError('Choose one public facet index')
    reason=args.get('reason','')
    if not isinstance(reason,str) or not reason.strip() or len(reason)>1000:raise ValueError('Explain how this query helps the decision')
    query=' '.join([config['terms'][i].strip() for i in dict.fromkeys(indices)]+[config['facets'][facet].strip()])
    identity=hashlib.sha256(query.encode()).hexdigest()
    with store.tasks() as db:
        db.execute('CREATE TABLE IF NOT EXISTS research_queries(run_id TEXT, identity TEXT, query TEXT, reason TEXT, PRIMARY KEY(run_id,identity))')
        db.execute('BEGIN IMMEDIATE')
        if run.get('_owner'):store.require_owner(db,run['id'],run['_owner'])
        known=db.execute('SELECT 1 FROM research_queries WHERE run_id=? AND identity=?',(run['id'],identity)).fetchone()
        count=db.execute('SELECT COUNT(*) FROM research_queries WHERE run_id=?',(run['id'],)).fetchone()[0]
        if not known and count>=config.get('max_queries',6):raise ValueError('Adaptive search query budget exhausted')
        db.execute('INSERT OR IGNORE INTO research_queries VALUES(?,?,?,?)',(run['id'],identity,query,reason))
    result=search_query(store,run['mission'],query,timeout,profile=store.meta(run['id']).get('mcp_profile'))
    result['query_budget']={'used':count+(not known),'limit':config.get('max_queries',6),'reason':reason,'private_context_sent':False}
    return result
