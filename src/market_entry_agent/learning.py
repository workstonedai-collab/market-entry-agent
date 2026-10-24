"""Opt-in private procedural learning; never grants tools or blocks report delivery."""
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from .memory import project_id


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


class Learning:
    def __init__(self,store,product):
        self.store,self.product=store,product
        with store.tasks() as db:db.executescript('''
        CREATE TABLE IF NOT EXISTS learning_policy(product TEXT,project TEXT,payload TEXT,PRIMARY KEY(product,project));
        CREATE TABLE IF NOT EXISTS learning_jobs(id TEXT PRIMARY KEY,product TEXT,project TEXT,run_id TEXT,lesson TEXT,state TEXT,model_started REAL,version TEXT,error TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS learned_versions(product TEXT,project TEXT,name TEXT,version TEXT,payload TEXT,created REAL,PRIMARY KEY(product,project,name,version));
        CREATE TABLE IF NOT EXISTS learned_active(product TEXT,project TEXT,name TEXT,version TEXT,PRIMARY KEY(product,project,name));
        ''')

    def policy(self,project,value=None):
        project_id(project)
        if value is not None:
            if not isinstance(value,dict) or set(value)-{'mode','auto_activate','max_calls_per_day'}:raise ValueError('Unknown learning policy fields')
            if value.get('mode') not in ('off','local','model') or type(value.get('auto_activate')) is not bool or type(value.get('max_calls_per_day')) is not int or not 0<=value['max_calls_per_day']<=20:raise ValueError('Learning policy requires mode, auto_activate and max_calls_per_day 0..20')
            if value['mode']=='model' and not value['max_calls_per_day']:raise ValueError('Model learning needs a positive daily call limit')
            with self.store.tasks() as db:db.execute('INSERT OR REPLACE INTO learning_policy VALUES(?,?,?)',(self.product,project,json.dumps(value)))
        with self.store.tasks() as db:row=db.execute('SELECT payload FROM learning_policy WHERE product=? AND project=?',(self.product,project)).fetchone()
        return json.loads(row[0]) if row else {'mode':'off','auto_activate':False,'max_calls_per_day':0}

    def enqueue(self,run_id,lesson='',project=None):
        run=self.store.get_run(run_id);project=project or run['mission'].get('project_id')
        project_id(project)
        if run['product']!=self.product or run['mission'].get('project_id')!=project:raise ValueError('Learning source outside project/product')
        if run['state']!='completed':raise ValueError('Learning requires a completed saved task; completion is not factual verification')
        if not isinstance(lesson,str) or len(lesson)>4000:raise ValueError('Feedback must be at most 4000 characters')
        policy=self.policy(project)
        if policy['mode']=='off':return {'state':'disabled','model_calls':0}
        jid='learn-'+fingerprint([self.product,project,run_id,lesson])[:28]
        with self.store.tasks() as db:db.execute('INSERT OR IGNORE INTO learning_jobs VALUES(?,?,?,?,?,?,?,?,?,?)',(jid,self.product,project,run_id,lesson,'queued',None,None,None,time.time()))
        with self.store.tasks() as db:state=db.execute('SELECT state FROM learning_jobs WHERE id=?',(jid,)).fetchone()[0]
        return {'id':jid,'state':state,'model_calls':0}

    def _draft(self,run,lesson):
        successful=[]
        for step in run['steps']:
            if step['action'] not in ('finish','load_skill','recall') and 'error' not in step['observation'] and 'reused_step' not in step['observation'] and step['action'] not in successful:successful.append(step['action'])
        # No source text, customer names or report prose is copied into the reusable procedure.
        steps=['围绕本次用户问题和已确认的资料范围安排取材。当前输入优先于历史记忆。']
        if 'search_evidence' in successful:steps.append('先检索本任务选中的本地证据与知识库，按需要读取具体片段。')
        if any(x in successful for x in ('web_search','adaptive_search','research_branch')):steps.append('需要补充外部资料时，只使用用户允许的公开词和检索方向。')
        if 'fetch_page' in successful:steps.append('搜索摘要用于发现来源；取得正文并读取后，再据此引用具体事实。')
        if 'country_baseline' in successful:steps.append('比较国区背景时，保留指标的期次、覆盖范围和缺失值，与当前事件分开分析。')
        steps.append('交代证据、推断和适用条件，形成并保存本次报告。资料不足时说明会改变判断的缺口。')
        if lesson.strip():steps.append('用户纠正：'+lesson.strip())
        mode=run['mission'].get('task_mode','research')
        name='learned-'+mode
        prior=next((v for v in self.versions(run['mission']['project_id']) if v['name']==name and v['active']),None)
        if prior:
            previous=prior['instructions'].split('\n\n注意：',1)[0].splitlines()
            previous=[re.sub(r'^\d+\.\s*','',line).strip() for line in previous if line.strip()]
            steps=list(dict.fromkeys(previous+steps))
            successful=list(dict.fromkeys(prior['contract']['requires_tools']+successful))
        return {'name':'learned-'+mode,'description':'本项目积累的研究步骤与用户纠正。','instructions':'\n'.join(str(i+1)+'. '+v for i,v in enumerate(steps)),
                'requires_tools':','.join(successful[:12]),'inputs':'Current task, selected collections and permitted evidence','outputs':'Saved source-attributed research with conditions and next checks',
                'pitfalls':'任务完成不等于事实已被独立核实。需要结合日期、适用范围和相反证据重新判断。'}

    def process(self,jid,model_factory=None):
        with self.store.tasks() as db:row=db.execute('SELECT * FROM learning_jobs WHERE id=? AND product=?',(jid,self.product)).fetchone()
        if not row:raise ValueError('Unknown learning job')
        row=dict(row);project=row['project'];policy=self.policy(project)
        if row['state']=='processing' and (row['model_started'] or row['created'])<time.time()-120:
            state='unknown' if row['model_started'] else 'queued'
            with self.store.tasks() as db:db.execute('UPDATE learning_jobs SET state=?,error=? WHERE id=?',(state,'Interrupted model call is not retried automatically' if state=='unknown' else None,jid))
            row['state']=state
        if row['state']!='queued':return row
        if policy['mode']=='off':return dict(row,state='disabled')
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            if policy['mode']=='model':
                midnight=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
                calls=db.execute('SELECT count(*) FROM learning_jobs WHERE product=? AND project=? AND model_started>=?',(self.product,project,midnight)).fetchone()[0]
                if calls>=policy['max_calls_per_day']:return dict(row,state='daily_budget_wait')
            changed=db.execute("UPDATE learning_jobs SET state='processing',model_started=? WHERE id=? AND state='queued'",(time.time() if policy['mode']=='model' else None,jid)).rowcount
            if not changed:return dict(row,state='busy')
        try:
            run=self.store.get_run(row['run_id']);draft=self._draft(run,row['lesson'])
            if policy['mode']=='model':
                if model_factory is None:
                    from .core import Model
                    model_factory=Model
                prompt='Write the skill in natural Chinese, keeping technical names where needed. Create one reusable documentation-only research skill from the supplied host procedure and explicit user correction. Capture lessons, not incident logs or source facts. Preserve previously enabled user corrections unless the new explicit correction supersedes them. Do not invent tools, execute scripts, broaden permissions or include customer identities. Return JSON {"action":"propose_skill","arguments":{"description":"...","instructions":"...","pitfalls":"..."}}. The task is already saved; this cannot rewrite it.'
                result=model_factory().next([{'role':'system','content':prompt},{'role':'user','content':json.dumps(draft,ensure_ascii=False)}],timeout=40)
                if not isinstance(result,dict) or result.get('action')!='propose_skill' or not isinstance(result.get('arguments'),dict):raise ValueError('Invalid learned skill response')
                args=result['arguments']
                if set(args)!={'description','instructions','pitfalls'}:raise ValueError('Unexpected learned skill fields')
                draft.update(args)
            prior=next((v for v in self.active(project) if v['name']==draft['name']),None)
            sources=list(dict.fromkeys((prior['source_run_ids'] if prior else [])+[row['run_id']]))
            result=self.save(project,draft,sources,jid)
            # A concurrent opt-out takes effect before activation.
            if self.policy(project)['mode']!='off' and self.policy(project)['auto_activate']:self.activate(project,result['name'],result['version'])
            with self.store.tasks() as db:db.execute("UPDATE learning_jobs SET state='completed',version=? WHERE id=?",(result['version'],jid))
        except Exception as exc:
            code=str(exc)[:160] if isinstance(exc,(ValueError,RuntimeError)) else type(exc).__name__
            with self.store.tasks() as db:db.execute("UPDATE learning_jobs SET state='failed',error=? WHERE id=?",(code,jid))
        with self.store.tasks() as db:return dict(db.execute('SELECT * FROM learning_jobs WHERE id=?',(jid,)).fetchone())

    def save(self,project,draft,source_runs,source_job=None):
        from .skills import normalize
        from .core import REGISTRY
        project_id(project)
        if not isinstance(draft,dict) or set(draft)-{'name','description','instructions','requires_tools','inputs','outputs','pitfalls'}:raise ValueError('Unsupported skill fields')
        if not draft.get('name','').startswith('learned-'):raise ValueError('Private learned names must start with learned-')
        for field,bound in [('instructions',6000),('pitfalls',2000)]:
            if not isinstance(draft.get(field,''),str) or len(draft.get(field,''))>bound:raise ValueError('Learned skill text exceeds bounds')
        entry=dict({k:v for k,v in draft.items() if k!='pitfalls'},origin='private_project_learning')
        entry['instructions']=draft['instructions']+'\n\n注意：'+draft.get('pitfalls','')
        entry=normalize([entry])[draft['name']]
        if any(tool not in REGISTRY.tools for tool in entry['contract']['requires_tools']):raise ValueError('Skill references an unavailable tool')
        for rid in source_runs:
            run=self.store.get_run(rid)
            if run['product']!=self.product or run['mission'].get('project_id')!=project:raise ValueError('Skill source outside project')
        value=dict(entry,source_run_ids=source_runs,source_job=source_job,created=time.time())
        with self.store.tasks() as db:db.execute('INSERT OR IGNORE INTO learned_versions VALUES(?,?,?,?,?,?)',(self.product,project,entry['name'],entry['version'],json.dumps(value,ensure_ascii=False),time.time()))
        return value

    def versions(self,project):
        project_id(project)
        with self.store.tasks() as db:
            active={r['name']:r['version'] for r in db.execute('SELECT name,version FROM learned_active WHERE product=? AND project=?',(self.product,project))}
            rows=db.execute('SELECT payload FROM learned_versions WHERE product=? AND project=? ORDER BY created DESC',(self.product,project)).fetchall()
        return [dict(json.loads(r[0]),active=active.get(json.loads(r[0])['name'])==json.loads(r[0])['version']) for r in rows]

    def activate(self,project,name,version=None):
        versions=self.versions(project)
        if version and not any(r['name']==name and r['version']==version for r in versions):raise ValueError('Skill version outside project')
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM learned_active WHERE product=? AND project=? AND name=?',(self.product,project,name))
            if version:
                if db.execute('SELECT count(*) FROM learned_active WHERE product=? AND project=?',(self.product,project)).fetchone()[0]>=8:raise ValueError('At most eight active learned skills per project')
                db.execute('INSERT INTO learned_active VALUES(?,?,?,?)',(self.product,project,name,version))
        return {'name':name,'version':version,'active':bool(version)}

    def active(self,project):
        return [r for r in self.versions(project) if r['active']]

    def jobs(self,project):
        project_id(project)
        with self.store.tasks() as db:return [dict(r) for r in db.execute('SELECT * FROM learning_jobs WHERE product=? AND project=? ORDER BY created DESC LIMIT 100',(self.product,project))]

    def export(self,project,name,version):
        row=next((r for r in self.versions(project) if r['name']==name and r['version']==version),None)
        if not row:raise ValueError('Skill version outside project')
        return '---\nname: '+json.dumps(row['name'])+'\ndescription: '+json.dumps(row['description'],ensure_ascii=False)+'\ninputs: '+json.dumps(row['contract']['inputs'])+'\noutputs: '+json.dumps(row['contract']['outputs'])+'\nrequires_tools: '+json.dumps(','.join(row['contract']['requires_tools']))+'\n---\n\n'+row['instructions']+'\n'

    def tick(self):
        with self.store.tasks() as db:ids=[r[0] for r in db.execute("SELECT id FROM learning_jobs WHERE product=? AND (state='queued' OR state='processing') ORDER BY created LIMIT 2",(self.product,))]
        return [self.process(jid) for jid in ids]
