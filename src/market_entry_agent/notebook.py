"""Private, revisioned research state. Source fragments are checked against read spans."""
import copy
import hashlib
import json
import re


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS research_notes(run_id TEXT PRIMARY KEY, revision INTEGER, content TEXT);
    CREATE TABLE IF NOT EXISTS research_revisions(run_id TEXT, revision INTEGER, content TEXT,
      PRIMARY KEY(run_id,revision));
    CREATE TABLE IF NOT EXISTS research_commands(run_id TEXT, command_id TEXT, PRIMARY KEY(run_id,command_id));
    ''')


def text(value, limit=3000):
    if not isinstance(value, str) or not value.strip() or len(value)>limit:
        raise ValueError('Research text must be nonempty and bounded')
    return value


def snapshot(store, rid):
    store.get_run(rid)
    with store.tasks() as db:
        initialize(db)
        row=db.execute('SELECT revision,content FROM research_notes WHERE run_id=?',(rid,)).fetchone()
    return dict(json.loads(row['content']),revision=row['revision']) if row else {
        'revision':0,'questions':[],'notes':[],'next_step':'','stop_reason':'',
        'notice':'Research working state, not independently verified facts or approved decisions.'}


def fragments(store, run, values):
    if not isinstance(values,list) or len(values)>8:raise ValueError('At most eight evidence fragments per note')
    result=[]
    for item in values:
        if not isinstance(item,dict):raise ValueError('Fragment must be an object')
        eid=item.get('evidence_id');offset=item.get('offset',0);quote=text(item.get('quote'),2000)
        if type(offset) is not int or offset<0:raise ValueError('Fragment offset must be nonnegative')
        end=offset+len(quote)
        spans=[s['observation'] for s in run['steps'] if s['action']=='read_evidence' and 'error' not in s['observation'] and s['observation'].get('id')==eid]
        if not any(s.get('body_offset',0)<=offset and end<=s.get('body_offset',0)+len(s['body']) for s in spans):
            raise ValueError('Fragment must be inside a successfully read evidence span')
        source=store.read(eid)
        if source.get('retrieval_kind')=='search_snippet':raise ValueError('Search snippets are discovery, not source facts')
        if source['body'][offset:end]!=quote:raise ValueError('Fragment does not match saved source text')
        result.append({'evidence_id':eid,'offset':offset,'quote':quote,'url':source['url'],
                       'title':source['title'],'published_at':source.get('published_at'),
                       'document_location':source.get('document_location'),'retrieval_kind':source.get('retrieval_kind','imported_text')})
    return result


def update(store, run, args):
    before=snapshot(store,run['id']);revision=args.get('expected_revision')
    command_id=hashlib.sha256(json.dumps(args,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with store.tasks() as db:
        if db.execute('SELECT 1 FROM research_commands WHERE run_id=? AND command_id=?',(run['id'],command_id)).fetchone():return before
    if type(revision) is not int or revision!=before['revision']:raise ValueError('Research revision conflict; read research_state')
    result=copy.deepcopy(before)
    read={s['observation'].get('id') for s in run['steps'] if s['action']=='read_evidence' and 'error' not in s['observation']}
    for key in ('questions','notes'):
        if key not in args:continue
        values=args[key]
        if not isinstance(values,list) or len(values)>20:raise ValueError('At most twenty research updates per action')
        records={r['id']:r for r in result[key]}
        for item in values:
            if not isinstance(item,dict) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',str(item.get('id',''))):raise ValueError('Research item requires a stable ID')
            row={'id':item['id'],'text':text(item.get('text'))}
            if key=='questions':
                row['status']=item.get('status','open')
                if row['status'] not in ('open','investigating','answered','unresolved'):raise ValueError('Invalid question state')
                row['why']=text(item.get('why','Relevant to the current decision'),1000)
            else:
                row['kind']=item.get('kind')
                if row['kind'] not in ('source_fact','hypothesis','judgment','decision_proposal'):raise ValueError('Invalid research note kind')
                row['evidence_ids']=item.get('evidence_ids',[])
                if not isinstance(row['evidence_ids'],list) or any(e not in read for e in row['evidence_ids']):raise ValueError('Research note cites unread evidence')
                row['fragments']=fragments(store,run,item.get('fragments',[]))
                if any(f['evidence_id'] not in row['evidence_ids'] for f in row['fragments']):raise ValueError('Fragment must have a listed evidence ID')
                if row['kind']=='source_fact' and not row['fragments']:raise ValueError('Source facts require an exact read fragment')
                row['relation']=item.get('relation','context')
                if row['relation'] not in ('supports','opposes','context'):raise ValueError('Invalid evidence relation')
                row['question_id']=item.get('question_id','')
                row['change_reason']=text(item.get('change_reason','Initial research note'),1000)
                row['origin']='agent_proposal'
            records[row['id']]=row
        if len(records)>40:raise ValueError('At most forty items per research category')
        result[key]=list(records.values())
    qids={q['id'] for q in result['questions']}
    if any(n.get('question_id') and n['question_id'] not in qids for n in result['notes']):raise ValueError('Unknown research question')
    for key in ('next_step','stop_reason'):
        if key in args:
            if not isinstance(args[key],str) or len(args[key])>2000:raise ValueError('Bounded research progress text required')
            result[key]=args[key]
    if result==before:return before
    result['revision']=revision+1
    with store.tasks() as db:
        initialize(db);db.execute('BEGIN IMMEDIATE')
        if run.get('_owner'):store.require_owner(db,run['id'],run['_owner'])
        current=db.execute('SELECT revision FROM research_notes WHERE run_id=?',(run['id'],)).fetchone()
        if (current['revision'] if current else 0)!=revision:raise ValueError('Research revision conflict')
        raw=json.dumps(result,ensure_ascii=False)
        db.execute('INSERT OR REPLACE INTO research_notes VALUES(?,?,?)',(run['id'],result['revision'],raw))
        db.execute('INSERT INTO research_revisions VALUES(?,?,?)',(run['id'],result['revision'],raw))
        db.execute('INSERT INTO research_commands VALUES(?,?)',(run['id'],command_id))
    return result


def brief(state):
    questions=[dict(q,text=q['text'][:500],why=q['why'][:200]) for q in state['questions'][:12]]
    notes=[{k:n[k] for k in ('id','kind','text','evidence_ids','relation','question_id','change_reason')} for n in state['notes'][:12]]
    for n in notes:n['text']=n['text'][:600];n['change_reason']=n['change_reason'][:200]
    return {'revision':state['revision'],'questions':questions,'notes':notes,
            'next_step':state['next_step'][:1000],'stop_reason':state['stop_reason'][:1000],
            'notice':state['notice'],'complete_state_tool':'research_state'}


def markdown(state):
    if not state or not state.get('revision'):return []
    lines=['','## 研究进展 / Research state','']
    for q in state['questions']:lines+=['- '+q['text']+' ('+q['status']+')']
    for n in state['notes']:
        lines+=['','- '+n['kind']+' · '+n['text']]
        for f in n['fragments']:lines+=['  - '+f['quote']+' ['+f['evidence_id']+' @ '+str(f['offset'])+']']
    if state['next_step']:lines+=['','下一步：'+state['next_step']]
    if state['stop_reason']:lines+=['','取材停止原因：'+state['stop_reason']]
    return lines
