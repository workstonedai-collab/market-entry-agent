"""Typed private research memory with explicit revisions and deterministic relevance."""
from datetime import datetime, timezone
import copy
import hashlib
import json
import re
from .memory import project_id, stamp

KINDS=('source_fact','hypothesis','judgment','decision_proposal','operator_decision')


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS research_memory(product TEXT,project TEXT,key TEXT,revision INTEGER,
      data TEXT,created TEXT,PRIMARY KEY(product,project,key,revision));
    CREATE TABLE IF NOT EXISTS research_forgotten(product TEXT,project TEXT,key TEXT,
      PRIMARY KEY(product,project,key));
    ''')


def terms(value):
    # Chinese bigrams and whole Latin words, without a tokenizer or remote embedding call.
    value=str(value).casefold()
    words=set(re.findall(r'[a-z0-9_]{2,}',value))
    for chunk in re.findall(r'[\u4e00-\u9fff]+',value):
        words.update(chunk[i:i+2] for i in range(max(1,len(chunk)-1)))
    return words


def relevance(value, question):
    return len(terms(value).intersection(terms(question)))


def ranked(rows, question, limit=8):
    ordered=sorted(enumerate(rows),key=lambda pair:(-relevance(pair[1].get('text',''),question),pair[0]))
    result=[]
    # Preserve both directions when they are relevant, rather than only the newest agreement.
    for relation in ('opposes','supports'):
        row=next((r for _,r in ordered if r.get('relation')==relation and relevance(r.get('text',''),question)>0),None)
        if row is not None and row not in result:result.append(row)
    for _,row in ordered:
        if row not in result:result.append(row)
        if len(result)>=limit:break
    return result[:limit]


class ResearchMemory:
    def __init__(self, store, product):
        self.store,self.product=store,product

    def _rows(self,db,project,key=None):
        project_id(project)
        query='SELECT * FROM research_memory WHERE product=? AND project=?'
        args=[self.product,project]
        if key is not None:project_id(key);query+=' AND key=?';args.append(key)
        return db.execute(query+' ORDER BY created DESC,revision DESC',args).fetchall()

    @staticmethod
    def unpack(row):
        return dict(json.loads(row['data']),key=row['key'],revision=row['revision'],recorded_at=row['created'])

    def list(self,project,as_of=None):
        cutoff=stamp(as_of) if as_of else datetime.now(timezone.utc)
        with self.store.tasks() as db:rows=self._rows(db,project)
        selected={}
        for row in rows:
            if stamp(row['created'])<=cutoff and row['key'] not in selected:selected[row['key']]=self.unpack(row)
        return list(selected.values())

    def history(self,project,key):
        with self.store.tasks() as db:return [self.unpack(row) for row in self._rows(db,project,key)[:100]]

    def _save(self,db,project,key,data,expected):
        project_id(project);project_id(key)
        old=self._rows(db,project,key);revision=old[0]['revision'] if old else 0
        if type(expected) is not int or expected!=revision:raise ValueError('Research memory revision conflict')
        if len(json.dumps(data,ensure_ascii=False))>16000:raise ValueError('Research memory record too large')
        if not old and len({r['key'] for r in self._rows(db,project)})>=500:raise ValueError('Research memory capacity is 500 records; forget unused records')
        created=datetime.now(timezone.utc).isoformat(timespec='microseconds')
        db.execute('INSERT INTO research_memory VALUES(?,?,?,?,?,?)',(self.product,project,key,revision+1,json.dumps(data,ensure_ascii=False),created))
        return dict(data,key=key,revision=revision+1,recorded_at=created)

    def save(self,project,key,data,expected_revision):
        if not isinstance(data,dict) or set(data)-{'kind','text','relation','change_reason','countries','topics'}:raise ValueError('Unsupported research memory fields')
        if data.get('kind') not in KINDS or data.get('kind')=='source_fact':raise ValueError('Operator edits use hypothesis, judgment, proposal or operator_decision; source facts retain exact run provenance')
        from .business import text, strings, choice
        value={'kind':data['kind'],'text':text(data.get('text')),'relation':choice(data.get('relation','context'),('supports','opposes','context')),
               'change_reason':text(data.get('change_reason'),1000),'countries':strings(data.get('countries',[])),
               'topics':strings(data.get('topics',[])),'origin':'operator','fragments':[],'evidence_ids':[]}
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM research_forgotten WHERE product=? AND project=? AND key=?',(self.product,project,key)).fetchone():raise ValueError('Forgotten key cannot be recreated; choose a new key')
            return self._save(db,project,key,value,expected_revision)

    def capture(self,db,run,state):
        project=run['mission'].get('project_id')
        if not project or run['mission'].get('as_of'):return []
        keys=[]
        for note in state.get('notes',[]):
            key='r-'+hashlib.sha256((run['id']+':'+note['id']).encode()).hexdigest()[:24]
            if self._rows(db,project,key) or db.execute('SELECT 1 FROM research_forgotten WHERE product=? AND project=? AND key=?',(self.product,project,key)).fetchone():continue
            value=copy.deepcopy(note);value.update(run_id=run['id'],countries=run['mission']['countries'],topics=run['mission']['topics'],origin='agent_proposal')
            keys.append(self._save(db,project,key,value,0)['key'])
        return keys

    def recall(self,mission):
        if not mission.get('project_id'):return []
        from .countries import scope_keys
        rows=self.list(mission['project_id'],mission.get('as_of'))
        rows=[r for r in rows if (not r.get('countries') or scope_keys(r['countries']).intersection(scope_keys(mission['countries'])))
              and (not r.get('topics') or set(r['topics']).intersection(mission['topics']))]
        selected=ranked(rows,mission['question'],8)
        for row in selected:
            row['text']=row['text'][:1000]
            row['fragments']=[{k:f.get(k) for k in ('evidence_id','offset','url','published_at','retrieval_kind')}|{'quote':f['quote'][:300]} for f in row.get('fragments',[])[:2]]
            row['citation_notice']='Historical research memory, not a source read in this run. Read original evidence before citing. Operator decisions are recorded instructions, not independent facts.'
        return selected

    def forget(self,project,key):
        project_id(project);project_id(key)
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            count=db.execute('DELETE FROM research_memory WHERE product=? AND project=? AND key=?',(self.product,project,key)).rowcount
            db.execute('INSERT OR IGNORE INTO research_forgotten VALUES(?,?,?)',(self.product,project,key))
        return {'removed_revisions':count,'note':'Removed from future recall. Saved reports, evidence, task checkpoints and frozen run contexts are separate records and remain retained.'}


def focus(memory,question):
    result=copy.deepcopy(memory)
    facts=result.get('facts',[])
    important={'budget','constraints','deadline','预算','约束','交期','产品'}
    result['facts']=sorted(facts,key=lambda r:(-int(r.get('key') in important),-relevance(r.get('key','')+' '+r.get('value',''),question)))[:12]
    result['omitted_facts']=len(facts)-len(result['facts'])
    result['previous']=sorted(result.get('previous',[]),key=lambda r:-relevance(r.get('question','')+' '+r.get('summary',''),question))[:3]
    result['notice']='Selected by current question and critical constraints, no semantic verification. Full operator facts remain available through memory CLI/API; current mission takes precedence.'
    return result
