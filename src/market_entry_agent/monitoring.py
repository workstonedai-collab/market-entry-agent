"""Confirmed project watches, incremental receipts, quiet digests and bounded recovery."""
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .memory import project_id


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def zone(name):
    # Fixed UTC offsets remain portable on Windows without an optional tzdata package.
    match=re.fullmatch(r'UTC([+-])(\d{2}):(\d{2})',name or '')
    if match:
        from datetime import timedelta
        h,m=int(match[2]),int(match[3])
        if h>14 or m>59 or (h==14 and m):raise ValueError('UTC offset outside bounds')
        return timezone((1 if match[1]=='+' else -1)*timedelta(hours=h,minutes=m))
    try:return ZoneInfo(name)
    except (ZoneInfoNotFoundError,ValueError,TypeError):raise ValueError('Timezone unavailable; use a fixed offset such as UTC+08:00 or install tzdata') from None


def schema(config,store,product):
    from .core import validate_mission
    if not isinstance(config,dict):raise ValueError('Monitor configuration must be an object')
    allowed={'name','mission','kind','source_ids','criteria','include_terms','exclude_terms','min_sources','check_interval','digest_interval','timezone','quiet_hours','engine','notify_first_run','delivery','delivery_profile','delivery_binding','source_bindings','allow_private_delivery'}
    if set(config)-allowed:raise ValueError('Unknown monitoring fields')
    c=json.loads(json.dumps(config,ensure_ascii=False))
    for key in ('name','criteria'):
        if not isinstance(c.get(key),str) or not c[key].strip() or len(c[key])>(200 if key=='name' else 2000):raise ValueError('Monitor needs bounded name and criteria')
    validate_mission(c.get('mission'));project_id(c['mission'].get('project_id'))
    if c['mission'].get('as_of'):raise ValueError('Continuous monitoring needs a current mission; remove historical as_of')
    if 'monitor_criteria' in c['mission'] or 'monitor_evidence_ids' in c['mission']:raise ValueError('Use a normal research mission for monitor configuration')
    if c.get('kind') not in ('event','theme','operating'):raise ValueError('Monitor kind must be event, theme or operating')
    if c.get('engine') not in ('rules','model'):raise ValueError('Monitor engine must be rules or model')
    for key,low,high in [('check_interval',60,604800),('digest_interval',60,604800),('min_sources',1,5)]:
        if type(c.get(key)) is not int or not low<=c[key]<=high:raise ValueError(key+' exceeds integer bounds')
    if c['digest_interval']<c['check_interval']:raise ValueError('Digest interval must be at least the check interval')
    for key in ('include_terms','exclude_terms','source_ids'):
        if not isinstance(c.get(key),list) or len(c[key])>30 or any(not isinstance(x,str) or not x.strip() or len(x)>200 for x in c[key]):raise ValueError('Monitor requires bounded '+key)
    known={s['id']:s for s in store.sources()}
    if len(c['source_ids'])>8:raise ValueError('Select at most eight registered sources')
    for sid in c['source_ids']:
        if sid not in known:raise ValueError('Unknown registered source')
    if c.get('notify_first_run') not in (True,False) or type(c['notify_first_run']) is not bool:raise ValueError('notify_first_run must be boolean')
    bindings={sid:digest(known[sid]) for sid in c['source_ids']}
    if c['mission'].get('mcp_search'):
        from .mcp_client import profile
        bindings['mcp:'+c['mission']['mcp_search']]=profile(c['mission']['mcp_search'])['version']
    if c.get('source_bindings') is not None and c['source_bindings']!=bindings:raise ValueError('Source settings changed; edit and reconfirm monitor')
    c['source_bindings']=bindings
    c.setdefault('delivery','local')
    if c['delivery'] not in ('local','hermes'):raise ValueError('Delivery must be local or hermes')
    c.setdefault('allow_private_delivery',False)
    if type(c['allow_private_delivery']) is not bool:raise ValueError('allow_private_delivery must be boolean')
    if c['delivery']=='hermes':
        if (c['mission'].get('knowledge_ids') or c['engine']=='model') and not c['allow_private_delivery']:raise ValueError('Confirm whether private project context, memory and selected knowledge may be included in external digests')
        from .notifications import binding
        current=binding(c.get('delivery_profile'))
        if c.get('delivery_binding') is not None and c['delivery_binding']!=current:raise ValueError('Delivery settings changed; edit and reconfirm monitor')
        c['delivery_binding']=current
    else:c.pop('delivery_binding',None);c.pop('delivery_profile',None)
    zone(c.get('timezone'))
    quiet=c.get('quiet_hours')
    if not isinstance(quiet,list) or len(quiet) not in (0,2) or any(type(x) is not int or not 0<=x<=23 for x in quiet):raise ValueError('quiet_hours must be [] or two hours 0..23')
    if len(quiet)==2 and quiet[0]==quiet[1]:raise ValueError('Quiet hours need distinct start and end')
    if c['mission'].get('knowledge_ids'):
        from .knowledge import Knowledge
        Knowledge(store,product).pin(c['mission']['project_id'],c['mission']['knowledge_ids'])
    return c


class Monitors:
    def __init__(self,store,product):
        self.store,self.product=store,product
        with store.tasks() as db:db.executescript('''
        CREATE TABLE IF NOT EXISTS monitors(id TEXT PRIMARY KEY,product TEXT,project TEXT,revision INTEGER,config TEXT,hash TEXT,confirmed TEXT,state TEXT,next_due REAL,last_digest REAL,failures INTEGER,lease REAL,owner TEXT);
        CREATE TABLE IF NOT EXISTS monitor_receipts(id TEXT PRIMARY KEY,monitor_id TEXT,revision INTEGER,slot REAL,state TEXT,run_id TEXT,payload TEXT,error TEXT,updated REAL);
        CREATE TABLE IF NOT EXISTS monitor_seen(monitor_id TEXT,revision INTEGER,fact TEXT,PRIMARY KEY(monitor_id,revision,fact));
        CREATE TABLE IF NOT EXISTS monitor_items(id TEXT PRIMARY KEY,monitor_id TEXT,revision INTEGER,payload TEXT,delivered INTEGER,created REAL);
        CREATE TABLE IF NOT EXISTS monitor_deliveries(id TEXT PRIMARY KEY,monitor_id TEXT,payload TEXT,state TEXT,updated REAL);
        ''')

    def get(self,project,mid):
        project_id(project)
        with self.store.tasks() as db:row=db.execute('SELECT * FROM monitors WHERE id=? AND product=? AND project=?',(mid,self.product,project)).fetchone()
        if not row:raise ValueError('Monitor outside project/product')
        value=dict(row);value['config']=json.loads(value['config']);value.pop('owner',None)
        return value

    def list(self,project):
        project_id(project)
        with self.store.tasks() as db:ids=[r[0] for r in db.execute('SELECT id FROM monitors WHERE product=? AND project=? ORDER BY id',(self.product,project))]
        return [self.get(project,mid) for mid in ids]

    def save(self,project,config,mid=None,expected_revision=0):
        clean=dict(config)
        clean.pop('source_bindings',None);clean.pop('delivery_binding',None)
        c=schema(clean,self.store,self.product)
        if c['mission']['project_id']!=project:raise ValueError('Mission must belong to this monitor project')
        mid=mid or 'monitor-'+uuid.uuid4().hex[:20]
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM monitors WHERE id=?',(mid,)).fetchone()
            if old and (old['product']!=self.product or old['project']!=project):raise ValueError('Monitor outside project/product')
            if (old['revision'] if old else 0)!=expected_revision:raise ValueError('Monitor revision changed; reload before editing')
            if old and old['lease']>time.time():raise ValueError('Pause and wait for the active check before editing')
            revision=expected_revision+1
            db.execute('INSERT OR REPLACE INTO monitors VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(mid,self.product,project,revision,json.dumps(c,ensure_ascii=False),digest(c),None,'draft',0,0,0,0,None))
        return self.get(project,mid)

    def confirm(self,project,mid,expected_hash):
        value=self.get(project,mid)
        # Validate sources and selected collections again at the confirmation boundary.
        schema(value['config'],self.store,self.product)
        if expected_hash!=value['hash']:raise ValueError('Monitor settings changed; preview and confirm the current revision')
        with self.store.tasks() as db:
            changed=db.execute("UPDATE monitors SET confirmed=hash,state='active',next_due=? WHERE id=? AND product=? AND project=? AND hash=? AND lease<=?",(time.time(),mid,self.product,project,expected_hash,time.time())).rowcount
        if not changed:raise ValueError('Monitor settings changed or a worker is active')
        return self.get(project,mid)

    def control(self,project,mid,state):
        self.get(project,mid)
        if state not in ('paused','archived'):raise ValueError('Use explicit confirmation to activate or resume monitoring')
        with self.store.tasks() as db:db.execute('UPDATE monitors SET state=? WHERE id=?',(state,mid))
        return self.get(project,mid)

    def evidence(self,c):
        from .countries import scope_keys
        mission=c['mission']
        # Store.search has a top-20 API cap. Watches examine every in-scope record instead.
        rows=[r for r in self.store.export_evidence()['records'] if scope_keys(mission['countries']).intersection(scope_keys(r['countries'])) and set(mission['topics']).intersection(r['topics'])]
        if mission.get('knowledge_ids'):
            from .knowledge import Knowledge
            kb=Knowledge(self.store,self.product);pin=kb.pin(mission['project_id'],mission['knowledge_ids'])
            rows.extend(kb.evidence(r) for r in kb._rows(pin))
        allowed_urls={s['url'] for s in self.store.sources() if s['id'] in c['source_ids']}
        def matches(r):
            if allowed_urls and r.get('visibility')!='private' and r['url'] not in allowed_urls and r.get('source_id') not in c['source_ids']:return False
            if c.get('delivery')=='hermes' and r.get('visibility')=='private' and not c.get('allow_private_delivery'):return False
            if r.get('retrieval_kind') in ('search_snippet','country_baseline'):return False
            hay=(r['title']+' '+r['body']).lower()
            return (not c['include_terms'] or any(x.lower() in hay for x in c['include_terms'])) and not any(x.lower() in hay for x in c['exclude_terms'])
        return [r for r in rows if matches(r)]

    @staticmethod
    def fact(row):
        # URLs, discovery time and generated analysis never make a fact new.
        return digest({'body':' '.join(row['body'].lower().split()),'countries':sorted(row['countries']),'topics':sorted(row['topics'])})

    def preview(self,project,mid):
        value=self.get(project,mid);c=value['config'];rows=self.evidence(c)
        return {'id':mid,'hash':value['hash'],'revision':value['revision'],'settings':c,'matches':[dict(id=r['id'],title=r['title'],excerpt=r['body'][:400],published_at=r.get('published_at'),location=r.get('document_location')) for r in rows[:20]],'matching_records':len(rows),'note':'Local preview only; no source refresh, confirmation, model call or delivery. Rules mode uses the explicit term/source filters; model mode additionally applies the written criteria.'}

    def refresh_sources(self,c):
        from .core import fetch_feed
        from .net import fetch_page,web_search
        deadline=time.monotonic()+120
        def remaining(cap):
            value=deadline-time.monotonic()
            if value<=0:raise ValueError('monitor_collection_deadline_exceeded')
            return min(cap,value)
        for sid in c['source_ids']:
            source=next((s for s in self.store.sources() if s['id']==sid),None)
            if not source:raise ValueError('A confirmed source is no longer registered')
            if source.get('kind')=='page':fetch_page(self.store,source_id=sid,timeout=remaining(20),fresh=True)
            else:fetch_feed(self.store,sid,timeout=remaining(12))
        mission=dict(c['mission'],monitor_refresh=True)
        for index,_ in enumerate(mission.get('search_queries',[])):
            found=web_search(self.store,mission,index,timeout=remaining(30))
            for row in found.get('results',[])[:3]:
                fetch_page(self.store,evidence_id=row['id'],timeout=remaining(20),fresh=True)

    def _claim(self,project,mid,stamp):
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM monitors WHERE id=? AND product=? AND project=?',(mid,self.product,project)).fetchone()
            if not row or row['state']!='active' or row['hash']!=row['confirmed'] or row['next_due']>stamp or row['lease']>time.time():return None
            receipt='fire-'+digest([mid,row['revision'],row['next_due']])[:28]
            old=db.execute('SELECT * FROM monitor_receipts WHERE id=?',(receipt,)).fetchone()
            # An interrupted model call without a saved terminal run must not be silently charged again.
            owner=uuid.uuid4().hex
            db.execute('UPDATE monitors SET lease=?,owner=? WHERE id=?',(time.time()+900,owner,mid))
            db.execute('INSERT OR IGNORE INTO monitor_receipts VALUES(?,?,?,?,?,?,?,?,?)',(receipt,mid,row['revision'],row['next_due'],'processing',None,'{}',None,stamp))
        return dict(row),receipt,dict(old) if old else None,owner

    def _complete(self,mid,receipt,owner,stamp,payload,facts,error=None):
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM monitors WHERE id=? AND owner=?',(mid,owner)).fetchone()
            if not row:raise ValueError('Monitor execution ownership changed')
            failures=row['failures']+1 if error else 0
            if error:
                delay=min(86400,60*2**min(failures-1,10));state='failed'
            else:delay=json.loads(row['config'])['check_interval'];state=payload['state']
            actual=max(stamp,time.time())
            next_due=actual+delay if error else row['next_due']+(int(max(0,actual-row['next_due'])//delay)+1)*delay
            db.execute('UPDATE monitors SET next_due=?,lease=0,owner=NULL,failures=? WHERE id=? AND owner=?',(next_due,failures,mid,owner))
            previous=db.execute('SELECT state,payload FROM monitor_receipts WHERE id=?',(receipt,)).fetchone()
            if error and previous and previous['state'] in ('model_running','analysis_wait'):
                state='analysis_wait';payload=dict(json.loads(previous['payload']),**payload)
            db.execute('UPDATE monitor_receipts SET state=?,payload=?,error=?,updated=? WHERE id=?',(state,json.dumps(payload,ensure_ascii=False),error,stamp,receipt))
            if not error:db.executemany('INSERT OR IGNORE INTO monitor_seen VALUES(?,?,?)',[(mid,row['revision'],fact) for fact in facts])
            for item in payload.get('items',[]):db.execute('INSERT OR IGNORE INTO monitor_items VALUES(?,?,?,?,?,?)',(item['id'],mid,row['revision'],json.dumps(item,ensure_ascii=False),0,stamp))
        return payload

    def check(self,project,mid,stamp=None,refresh=True,agent_factory=None):
        stamp=time.time() if stamp is None else stamp
        claimed=self._claim(project,mid,stamp)
        if not claimed:return {'id':mid,'state':'not_due_or_not_confirmed'}
        row,receipt,old,owner=claimed;c=json.loads(row['config'])
        try:
            schema(c,self.store,self.product)
            if old and old['state'] in ('model_running','analysis_wait'):
                if old['run_id']:
                    run=self.store.get_run(old['run_id'])
                    if run['state']!='completed':raise ValueError('interrupted_analysis_requires_explicit_run_resume')
                    pending=json.loads(old['payload']);fresh=pending['fresh'];rows=pending['rows']
                else:raise ValueError('interrupted_analysis_has_unknown_admission')
            else:
                if refresh:self.refresh_sources(c)
                rows=self.evidence(c)
                with self.store.tasks() as db:seen={r[0] for r in db.execute('SELECT fact FROM monitor_seen WHERE monitor_id=? AND revision=?',(mid,row['revision']))}
                fresh=[r for r in rows if self.fact(r) not in seen]
                # Group exact duplicate source bodies, retaining corroboration URLs separately.
                first=not seen
                if first and not c['notify_first_run']:
                    result=self._complete(mid,receipt,owner,stamp,{'state':'baseline_saved','items':[]},[self.fact(r) for r in rows])
                    try:self.deliver(project,mid,stamp)
                    except (ValueError,OSError):result['delivery_state']='blocked_check_saved'
                    return result
                run=None
            items=[]
            if fresh:
                groups={}
                for item in fresh:
                    key=re.sub(r'[^\w]+','',item['title'].lower())
                    groups.setdefault(key,[]).append(item)
                eligible=[]
                for group in groups.values():
                    hosts={__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(r['url']).hostname or r.get('document_version') for r in group}
                    if len(hosts)>=c['min_sources']:eligible.extend(group)
                fresh=eligible
                if fresh:
                    if c['engine']=='model':
                        fresh=fresh[:40]
                        if not run:
                            from .core import Agent
                            mission=dict(c['mission'],monitor_criteria=c['criteria'],monitor_evidence_ids=[r['id'] for r in fresh[:40]])
                            # Current evidence is supplied locally, never used to derive public search queries.
                            mission['search_queries']=[];mission.pop('public_search',None);mission.pop('research_depth',None)
                            with self.store.tasks() as db:
                                db.execute('BEGIN IMMEDIATE')
                                rid=self.store.create_run(self.product,mission,'model',db=db)
                                db.execute("UPDATE monitor_receipts SET state='model_running',run_id=?,payload=? WHERE id=?",(rid,json.dumps({'fresh':fresh,'rows':rows},ensure_ascii=False),receipt))
                            run=(agent_factory or Agent)(self.store,__import__(__package__+'.product',fromlist=['SPEC']).SPEC).run(resume=rid)
                        if run['state']!='completed':raise ValueError('monitor_analysis_failed:'+run['id'])
                        decision=run['report'].get('monitor_decision')
                        if not isinstance(decision,dict) or type(decision.get('notify')) is not bool or not isinstance(decision.get('reason'),str):raise ValueError('monitor_analysis_missing_decision')
                        if decision['notify']:items=[{'id':'change-'+digest([mid,row['revision'],sorted(self.fact(r) for r in fresh)])[:24],'title':run['report']['title'],'summary':run['report']['summary'],'reason':decision['reason'],'run_id':run['id'],'evidence_ids':run['report']['evidence_ids'],'kind':c['kind']}]
                    else:
                        unique={self.fact(r):r for r in fresh}
                        for fact,r in list(unique.items()):
                            items.append({'id':'change-'+digest([mid,row['revision'],fact])[:24],'title':r['title'],'summary':r['body'][:600],'reason':'符合已确认的来源与匹配词范围；以下为来源摘录，需结合适用条件理解。','evidence_ids':[r['id']],'published_at':r.get('published_at'),'observed_at':r['observed_at'],'kind':c['kind']})
            payload={'state':'changes_saved' if items else 'no_change','items':items,'considered':len(rows),'fresh':len(fresh),'receipt':receipt}
            result=self._complete(mid,receipt,owner,stamp,payload,[self.fact(r) for r in fresh])
            try:self.deliver(project,mid,stamp)
            except (ValueError,OSError):result['delivery_state']='blocked_check_saved'
            return result
        except Exception as exc:
            code=str(exc)[:180] if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__
            result=self._complete(mid,receipt,owner,stamp,{'state':'failed','items':[],'receipt':receipt},[],code)
            if 'analysis_' in code or 'reconfirm' in code or 'settings changed' in code:

                with self.store.tasks() as db:db.execute("UPDATE monitors SET state='paused' WHERE id=?",(mid,))
            return result

    def deliver(self,project,mid,stamp=None):
        stamp=time.time() if stamp is None else stamp;value=self.get(project,mid);c=value['config']
        if value['state']!='active' or value['confirmed']!=value['hash'] or stamp-value['last_digest']<c['digest_interval']:return {'state':'waiting'}
        hour=datetime.fromtimestamp(stamp,zone(c['timezone'])).hour;quiet=c['quiet_hours']
        if quiet and (quiet[0]<=hour<quiet[1] if quiet[0]<quiet[1] else hour>=quiet[0] or hour<quiet[1]):return {'state':'quiet_hours'}
        if c.get('delivery')=='hermes':
            from .notifications import binding
            if binding(c['delivery_profile'])!=c['delivery_binding']:raise ValueError('Delivery destination changed; edit and reconfirm monitor')
        if c.get('delivery')=='hermes':
            from .notifications import send
            with self.store.tasks() as db:pending=[dict(r) for r in db.execute("SELECT id,payload FROM monitor_deliveries WHERE monitor_id=? AND state IN ('pending','sending') ORDER BY updated LIMIT 2",(mid,))]
            for queued in pending:
                if json.loads(queued['payload']).get('revision')==value['revision']:send(self.store,c,queued['id'])
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            items=db.execute('SELECT id,payload FROM monitor_items WHERE monitor_id=? AND revision=? AND delivered=0 ORDER BY created LIMIT 100',(mid,value['revision'])).fetchall()
            if not items:return {'state':'quiet_no_changes'}
            did='digest-'+digest([mid,value['revision'],[r['id'] for r in items]])[:24]
            payload={'id':did,'monitor_id':mid,'title':c['name'],'project_id':project,'items':[json.loads(r['payload']) for r in items],'created':stamp,'delivery':'local_inbox','revision':value['revision']}
            db.execute("INSERT OR IGNORE INTO monitor_deliveries VALUES(?,?,?,'pending',?)",(did,mid,json.dumps(payload,ensure_ascii=False),stamp))
            db.executemany('UPDATE monitor_items SET delivered=1 WHERE id=?',[(r['id'],) for r in items])
            db.execute('UPDATE monitors SET last_digest=? WHERE id=?',(stamp,mid))
        if c.get('delivery')=='hermes':
            from .notifications import send
            payload['external_delivery']=send(self.store,c,did)
        return payload

    def history(self,project,mid):
        self.get(project,mid)
        with self.store.tasks() as db:
            receipts=[dict(r,payload=json.loads(r['payload'])) for r in db.execute('SELECT * FROM monitor_receipts WHERE monitor_id=? ORDER BY slot DESC LIMIT 100',(mid,))]
            inbox=[dict(r,payload=json.loads(r['payload'])) for r in db.execute('SELECT * FROM monitor_deliveries WHERE monitor_id=? ORDER BY updated DESC LIMIT 100',(mid,))]
        return {'receipts':receipts,'inbox':inbox}

    def retry(self,project,mid,receipt):
        value=self.get(project,mid)
        if value['hash']!=value['confirmed']:raise ValueError('Confirm current monitor settings first')
        with self.store.tasks() as db:
            row=db.execute('SELECT * FROM monitor_receipts WHERE id=? AND monitor_id=? AND revision=?',(receipt,mid,value['revision'])).fetchone()
            if not row or row['state'] not in ('failed','analysis_wait'):raise ValueError('No recoverable receipt in this revision')
            if value['lease']>time.time():raise ValueError('Monitor has an active check')
            db.execute("UPDATE monitors SET state='active',next_due=? WHERE id=?",(row['slot'],mid))
        return self.get(project,mid)

    def acknowledge(self,project,mid,did):
        self.get(project,mid)
        with self.store.tasks() as db:
            count=db.execute("UPDATE monitor_deliveries SET state='read',updated=? WHERE id=? AND monitor_id=?",(time.time(),did,mid)).rowcount
        if not count:raise ValueError('Digest outside monitor')
        return {'id':did,'state':'read'}

    def tick(self):
        with self.store.tasks() as db:rows=[dict(r) for r in db.execute("SELECT project,id FROM monitors WHERE product=? AND state='active' AND confirmed=hash ORDER BY next_due LIMIT 20",(self.product,))]
        results=[]
        for row in rows:
            results.append(dict(self.check(row['project'],row['id']),monitor_id=row['id']))
            try:self.deliver(row['project'],row['id'])
            except (ValueError,OSError):pass  # A check receipt and pending digest remain visible; never regenerate analysis.
        return results
