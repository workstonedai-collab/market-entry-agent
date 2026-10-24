"""Opt-in newline JSON-RPC MCP stdio adapter over existing local capabilities."""
import hashlib
import json
import sys
import threading
from . import __version__
from .core import Agent, validate_mission
from .contracts import check, field

PROTOCOL='2025-11-25'
SUPPORTED=(PROTOCOL,'2025-06-18','2025-03-26','2024-11-05')
TEXT=field('string',minLength=1,maxLength=128)
PAGE={'offset':field('integer',minimum=0,maximum=1000000),'limit':field('integer',minimum=1,maximum=6000)}


def schema(properties,required=()):
    return field('object',properties=properties,required=list(required),additionalProperties=False)


class Adapter:
    def __init__(self,store,spec,allow_runs=False,project=None):
        if project:
            from .memory import project_id
            project_id(project)
        self.store,self.spec,self.allow_runs,self.project=store,spec,allow_runs,project
        self.initialized=False;self.ready=False;self.workers=threading.BoundedSemaphore(2)
        with store.tasks() as db:
            db.execute('CREATE TABLE IF NOT EXISTS mcp_commands(product TEXT,key TEXT,fingerprint TEXT,run_id TEXT,PRIMARY KEY(product,key))')

    def tools(self):
        entries=[('country_list','List bundled public country coverage.',schema({})),
          ('country_compare','Compare 1–5 countries; preserve different data bases.',schema({'countries':field('array',maxItems=5,items=TEXT)},['countries'])),
          ('run_status','Read saved task state and budgets in this workspace.',schema({'id':TEXT},['id'])),
          ('run_report','Read a bounded saved report excerpt; not a new model call.',schema({'id':TEXT,**PAGE},['id'])),
          ('research_read','Read a bounded research notebook excerpt for a saved run.',schema({'id':TEXT,**PAGE},['id'])),
          ('project_read','Read a bounded private business-project snapshot.',schema({'project_id':TEXT,**PAGE},['project_id']))]
        if self.allow_runs:entries += [
          ('run_create','Explicitly create a bounded task. Model mode can incur configured provider charges. client_key deduplicates create retries.',schema({'client_key':TEXT,'mission':field('object'),'engine':field('string',maxLength=8)},['client_key','mission','engine'])),
          ('run_resume','Explicitly resume an existing task with its saved scope, instructions and budgets.',schema({'id':TEXT},['id'])),
          ('run_control','Pause or cancel a saved task at its next safe boundary.',schema({'id':TEXT,'state':field('string',maxLength=16)},['id','state']))]
        return [{'name':name,'description':description,'inputSchema':contract,
                 'annotations':{'readOnlyHint':not name.startswith(('run_create','run_resume','run_control')),'destructiveHint':False,'openWorldHint':name in ('run_create','run_resume')}} for name,description,contract in entries]

    def run(self,rid):
        run=self.store.get_run(rid)
        if run['product']!=self.spec['id'] or (self.project and run['mission'].get('project_id')!=self.project):raise ValueError('Task outside this adapter project/product scope')
        return run

    def start(self,rid):
        if not self.workers.acquire(blocking=False):raise ValueError('Two adapter workers are active; retry later')
        def work():
            try:Agent(self.store,self.spec).run(resume=rid)
            except (ValueError,RuntimeError):pass # A concurrent owner retains its task.
            finally:self.workers.release()
        threading.Thread(target=work,daemon=True).start()

    @staticmethod
    def page(value,args):
        raw=json.dumps(value,ensure_ascii=False);offset=args.get('offset',0);limit=args.get('limit',3000)
        if offset>len(raw):raise ValueError('Offset exceeds saved result length')
        return {'text':raw[offset:offset+limit],'offset':offset,'next_offset':min(len(raw),offset+limit),'total_characters':len(raw),'truncated':offset+limit<len(raw)}

    def call(self,name,args):
        tool=next((t for t in self.tools() if t['name']==name),None)
        if not tool:raise ValueError('Unknown or disabled MCP tool')
        check(tool['inputSchema'],args)
        if name=='country_list':
            from .countries import catalog
            return catalog()
        if name=='country_compare':
            from .countries import compare
            return compare(args['countries'])
        if name=='project_read':
            if self.project and args['project_id']!=self.project:raise ValueError('Project outside adapter scope')
            from .workflow import Workflow
            return self.page(Workflow(self.store,self.spec['id']).state(args['project_id']),args)
        if name=='run_create':
            mission=validate_mission(args['mission']);engine=args['engine']
            if engine not in ('demo','model'):raise ValueError('engine must be demo or model')
            if self.project and mission.get('project_id')!=self.project:raise ValueError('Mission outside adapter project scope')
            fingerprint=hashlib.sha256(json.dumps([mission,engine],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            with self.store.tasks() as db:old=db.execute('SELECT fingerprint,run_id FROM mcp_commands WHERE product=? AND key=?',(self.spec['id'],args['client_key'])).fetchone()
            if old:
                if old['fingerprint']!=fingerprint:raise ValueError('client_key was already used for different input')
                run=self.run(old['run_id']);return {'id':run['id'],'state':run['state'],'reused':True,'note':'Existing task retained; use explicit run_resume if needed.'}
            rid=self.store.create_run(self.spec['id'],mission,engine)
            with self.store.tasks() as db:
                db.execute('INSERT OR IGNORE INTO mcp_commands VALUES(?,?,?,?)',(self.spec['id'],args['client_key'],fingerprint,rid))
                saved=db.execute('SELECT fingerprint,run_id FROM mcp_commands WHERE product=? AND key=?',(self.spec['id'],args['client_key'])).fetchone()
            if saved['run_id']!=rid:
                self.store.control(rid,'cancelled')
                if saved['fingerprint']!=fingerprint:raise ValueError('Concurrent client_key conflict')
                return {'id':saved['run_id'],'reused':True}
            # A worker-limit error leaves a durable queued task, recoverable with run_resume.
            try:self.start(rid)
            except ValueError:return {'id':rid,'state':'queued','note':'Workers are busy; use run_resume later.'}
            return {'id':rid,'state':self.run(rid)['state'],'reused':False}
        run=self.run(args['id'])
        if name=='run_status':return {k:run[k] for k in ('id','state','error','runtime','created','updated')}
        if name=='run_report':
            if not run.get('report'):raise ValueError('Task has no saved report')
            return self.page(run['report'],args)
        if name=='research_read':
            from .notebook import snapshot
            from .depth import snapshot as branch_snapshot
            return self.page(dict(snapshot(self.store,run['id']),branches=branch_snapshot(self.store,run['id'])),args)
        if name=='run_control':return self.store.control(run['id'],args['state'])
        if name=='run_resume':
            if run['state'] not in ('completed','cancelled'):self.start(run['id'])
            return {'id':run['id'],'state':self.run(run['id'])['state']}
        raise ValueError('Unsupported MCP tool')

    def dispatch(self,message):
        if not isinstance(message,dict) or message.get('jsonrpc')!='2.0' or not isinstance(message.get('method'),str):return self.error(None,-32600,'Invalid JSON-RPC request')
        rid=message.get('id');method=message['method'];params=message.get('params',{})
        if 'id' not in message:
            if method=='notifications/initialized' and self.initialized:self.ready=True
            return None
        if type(rid) not in (int,str) or not isinstance(params,dict):return self.error(None,-32600,'Invalid JSON-RPC id or params')
        if method=='initialize':
            self.initialized=True;self.ready=False
            version=params.get('protocolVersion');return {'jsonrpc':'2.0','id':rid,'result':{'protocolVersion':version if version in SUPPORTED else PROTOCOL,'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':self.spec['id'],'version':__version__},'instructions':'Local workspace access. Read-only by default; task execution requires explicit adapter startup permission. Private state may be returned to this MCP client.'}}
        if method=='ping':return {'jsonrpc':'2.0','id':rid,'result':{}}
        if not self.ready:return self.error(rid,-32002,'Initialize and send notifications/initialized first')
        if method=='tools/list':
            if params.get('cursor'):return self.error(rid,-32602,'Unknown pagination cursor')
            return {'jsonrpc':'2.0','id':rid,'result':{'tools':self.tools()}}
        if method=='tools/call':
            name=params.get('name')
            if not any(t['name']==name for t in self.tools()):return self.error(rid,-32602,'Unknown or disabled tool')
            try:
                data=self.call(name,params.get('arguments',{}));result={'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}],'structuredContent':data,'isError':False}
            except (ValueError,KeyError,TypeError) as exc:result={'content':[{'type':'text','text':str(exc)[:180]}],'isError':True}
            return {'jsonrpc':'2.0','id':rid,'result':result}
        return self.error(rid,-32601,'Method not found')

    @staticmethod
    def error(rid,code,message):return {'jsonrpc':'2.0','id':rid,'error':{'code':code,'message':message}}


def serve(store,spec,allow_runs=False,project=None,input_stream=None,output_stream=None):
    adapter=Adapter(store,spec,allow_runs,project);source=input_stream or sys.stdin;target=output_stream or sys.stdout
    for stream in (source,target):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    while True:
        line=source.readline(1000001)
        if not line:break
        if len(line)>1000000:
            while line and not line.endswith('\n'):line=source.readline(1000001)
            response=adapter.error(None,-32700,'MCP input exceeds 1000000 characters')
        else:
            try:response=adapter.dispatch(json.loads(line,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Invalid JSON constant'))))
            except (ValueError,UnicodeError):response=adapter.error(None,-32700,'Invalid JSON')
        if response is not None:target.write(json.dumps(response,ensure_ascii=False,separators=(',',':'))+'\n');target.flush()
