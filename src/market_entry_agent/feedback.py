"""Explicit user feedback and skill-context observations; neither changes policy."""
import hashlib
import json
import time
from .memory import project_id

RATINGS=('useful','duplicate','irrelevant','follow','adopted','needs_correction')


class Feedback:
    def __init__(self,store,product):
        self.store,self.product=store,product
        with store.tasks() as db:db.executescript('''
        CREATE TABLE IF NOT EXISTS user_feedback(id TEXT PRIMARY KEY,product TEXT,project TEXT,kind TEXT,target TEXT,context TEXT,rating TEXT,note TEXT,created REAL);
        CREATE INDEX IF NOT EXISTS feedback_scope ON user_feedback(product,project,kind,target,created);
        ''')

    def validate_target(self,project,kind,target,context=''):
        project_id(project)
        if not isinstance(target,str) or not 1<=len(target)<=100:raise ValueError('Invalid feedback target')
        if kind=='report':
            run=self.store.get_run(target)
            if run['product']!=self.product or run['mission'].get('project_id')!=project or run['state']!='completed':raise ValueError('Feedback needs a completed report in this project/product')
            if context:raise ValueError('Report feedback does not accept a monitor context')
        elif kind=='monitor':
            from .monitoring import Monitors
            Monitors(self.store,self.product).get(project,context)
            with self.store.tasks() as db:row=db.execute('SELECT id FROM monitor_deliveries WHERE id=? AND monitor_id=?',(target,context)).fetchone()
            if not row:raise ValueError('Digest outside monitor')
        else:raise ValueError('Feedback kind must be report or monitor')

    def save(self,project,kind,target,rating,note='',context=''):
        self.validate_target(project,kind,target,context)
        if rating not in RATINGS:raise ValueError('Unknown feedback rating')
        if not isinstance(note,str) or len(note)>2000:raise ValueError('Feedback note exceeds 2000 characters')
        identity=[self.product,project,kind,target,context,rating,note]
        fid='feedback-'+hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()[:32]
        with self.store.tasks() as db:
            db.execute('INSERT INTO user_feedback VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET created=excluded.created',(fid,self.product,project,kind,target,context,rating,note,time.time()))
        return {'id':fid,'rating':rating,'settings_changed':False,'note':'Saved operator feedback; monitoring changes still require preview and confirmation.'}

    def list(self,project,kind=None,context=None):
        project_id(project)
        query='SELECT * FROM user_feedback WHERE product=? AND project=?';params=[self.product,project]
        if kind is not None:query+=' AND kind=?';params.append(kind)
        if context is not None:query+=' AND context=?';params.append(context)
        with self.store.tasks() as db:rows=db.execute(query+' ORDER BY created DESC,rowid DESC LIMIT 500',params).fetchall()
        return [dict(r) for r in rows]

    def suggestions(self,project,mid):
        from .monitoring import Monitors
        monitor=Monitors(self.store,self.product).get(project,mid)
        latest={}
        for row in self.list(project,'monitor',mid):latest.setdefault(row['target'],row)
        counts={rating:sum(r['rating']==rating for r in latest.values()) for rating in RATINGS}
        advice=[]
        if counts['duplicate']:advice.append('检查重复资料的来源与汇总间隔，预览后再决定是否修改。')
        if counts['irrelevant']:advice.append('回看无关快报，明确不关注的主体、主题或匹配词；修改范围后重新确认。')
        if counts['follow']:advice.append('把希望继续关注的变化写入提醒标准，保持来源和公开检索范围明确。')
        if counts['needs_correction']:advice.append('先对照来源与日期检查报告问题，再决定修正研究要求还是监测条件。')
        return {'monitor_id':mid,'revision':monitor['revision'],'counts':counts,'suggestions':advice,'requires_confirmation':True,'settings_changed':False}

    def skill_usage(self,project):
        project_id(project)
        from .learning import Learning
        versions=Learning(self.store,self.product).versions(project)
        metrics={(s['name'],s['version']):{'name':s['name'],'version':s['version'],'loaded_contexts':0,'completed_reports':0,'related_feedback':{r:0 for r in RATINGS},'run_ids':[]} for s in versions}
        feedback={}
        for row in self.list(project,'report'):feedback.setdefault(row['target'],row)
        with self.store.tasks() as db:
            rows=db.execute('SELECT r.id,r.state,m.payload FROM runs r JOIN project_runs p ON p.run_id=r.id JOIN run_meta m ON m.run_id=r.id WHERE r.product=? AND p.product=? AND p.project_id=?',(self.product,self.product,project)).fetchall()
        for row in rows:
            meta=json.loads(row['payload']);loaded=meta.get('loaded_skills',{})
            for name,skill in loaded.items():
                entry=metrics.get((name,skill.get('version')))
                if entry is None:continue
                entry['loaded_contexts']+=1;entry['completed_reports']+=row['state']=='completed'
                if len(entry['run_ids'])<30:entry['run_ids'].append(row['id'])
                vote=feedback.get(row['id'])
                if vote:entry['related_feedback'][vote['rating']]+=1
        return {'versions':list(metrics.values()),'meaning':'Loaded into saved task context, not proof that a skill caused a better report. Feedback is an operator observation; no automatic score or activation.'}
