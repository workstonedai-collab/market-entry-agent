"""Installed-package paths for dossiers, cited versions, setup, feedback, Word and MCP."""
import base64
from contextlib import redirect_stdout
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from urllib.request import build_opener, ProxyHandler, Request
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def verify():
    metadata=json.loads((ROOT/'agent.json').read_text(encoding='utf-8'));module=metadata['python_module']
    core=importlib.import_module(module+'.core');SPEC=importlib.import_module(module+'.product').SPEC
    app=importlib.import_module(module+'.app');Lifecycle=importlib.import_module(module+'.lifecycle').Lifecycle
    Knowledge=importlib.import_module(module+'.knowledge').Knowledge
    Client=importlib.import_module(module+'.mcp_client').Client
    worker_status=importlib.import_module(module+'.worker_health').status
    clean={k:v for k,v in os.environ.items() if not k.startswith('AGENT_')};clean['AGENT_UI_TOKEN']='acceptance-token-not-a-user-secret'
    checks=[]
    with patch.dict(os.environ,clean,clear=True),tempfile.TemporaryDirectory(prefix='project-research-') as temporary:
        home=Path(temporary);workspace=home/'研究工作空间';store=core.Store(workspace);kb=Knowledge(store,SPEC['id']);lc=Lifecycle(store,SPEC['id']);project='synthetic-project'
        collection=kb.create(project,'Synthetic research material')
        job=kb.queue(project,collection['id'],'公开说明.md','# Synthetic source\nThe European Union published a synthetic rule.\n'.encode(),dict(title='Synthetic source',countries=['EU'],topics=['trade'],published_at='2025-01-01'))
        assert kb.process(project,job['id'])['state']=='completed';pin=kb.pin(project,[collection['id']]);hit=kb.search(pin,'欧盟')[0]
        assert not kb.search(pin,'欧盟',filters={'published_after':'2026-01-01'})
        checks.append('installed_private_bilingual_search_and_date_filter')
        report=dict(evaluation_backend='scripted_substitute',title='Synthetic installed-path report',summary='A saved source and a conditional interpretation.',assessment='This verifies software paths, not model quality or current policy.',findings=[{'claim':'The selected synthetic source contains the supplied sentence.','evidence_ids':[hit['id']]}],actions=['Check the applicable scope.'],uncertainties=['Synthetic acceptance material.'],follow_up=['Inspect another permitted source.'],evidence_ids=[hit['id']],priority='routine')
        actions=iter([{'action':'read_evidence','arguments':{'id':hit['id']}},{'action':'finish','arguments':{'report':report}}])
        class Scripted:
            def next(self,*args,**kwargs):return next(actions)
        mission=dict(question='Read selected synthetic material.',countries=['EU'],topics=['trade'],project_id=project,knowledge_ids=[collection['id']],max_steps=6,deadline_seconds=60)
        run=core.Agent(store,SPEC,Scripted).run(mission,'model');assert run['state']=='completed',run['error']
        old=kb.documents(project,collection['id'])[0]
        update=kb.queue(project,collection['id'],'公开说明.md',b'New European Union statement.',dict(title='Updated synthetic source',countries=['EU'],topics=['trade'],published_at='2026-01-01'),old['id'])
        assert kb.process(project,update['id'])['state']=='completed'
        assert 'synthetic rule' in lc.dispatch('knowledge','cited',dict(project_id=project,run_id=run['id'],id=hit['id']))['body']
        assert lc.dispatch('desk','overview',{'project_id':project})['recent'][0]['id']==run['id']
        checks.append('saved_report_dossier_and_frozen_citation_after_replacement')
        real_server=app.AgentHTTPServer;ready=threading.Event();servers=[]
        def factory(address,handler):
            server=real_server(address,handler);servers.append(server);ready.set();return server
        opener=build_opener(ProxyHandler({}))
        def request(path,body=None):
            headers={'Authorization':'Bearer '+clean['AGENT_UI_TOKEN']}
            if body is not None:headers['Content-Type']='application/json'
            req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            with opener.open(req,timeout=10) as response:raw=response.read();ctype=response.headers.get('Content-Type','')
            return json.loads(raw) if 'application/json' in ctype else raw
        with patch.object(app,'AgentHTTPServer',side_effect=factory),redirect_stdout(io.StringIO()):
            thread=threading.Thread(target=app.serve,args=(store,'127.0.0.1',0),daemon=True);thread.start()
            try:
                assert ready.wait(5),'HTTP server did not bind';base='http://127.0.0.1:'+str(servers[0].server_port)
                before=request('/api/setup/status');assert before['model_calls']==0
                saved=request('/api/setup/model',{'settings':{'base_url':'https://example.invalid/v1','model':'synthetic-model','api_key':'acceptance-only-key','remember_key':False,'max_tokens':6000,'reasoning_effort':'low'}})
                assert saved['credential_storage']=='current_process_only'
                assert 'acceptance-only-key' not in (workspace/'model-profile.json').read_text(encoding='utf-8')
                assert 'acceptance-only-key' not in json.dumps(request('/api/setup/status'))
                assert request('/api/state')['model_configured']
                source=before['source_pack'][0]['id'];assert request('/api/setup/sources',{'source_ids':[source]})['network_called'] is False
                assert request('/api/desk/overview?project_id='+project)['recent'][0]['id']==run['id']
                vote=request('/api/feedback/save',dict(project_id=project,kind='report',target=run['id'],rating='needs_correction',note='Marked acceptance feedback, not a user quality assessment.'));assert vote['settings_changed'] is False
                raw=request('/api/report.docx?run_id='+run['id'])
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:assert b'Synthetic installed-path report' in archive.read('word/document.xml')
                (home/'browser-report.docx').write_bytes(raw)
                checks+=['real_http_setup_without_secret_echo_or_network_test','real_http_source_selection_without_fetch','real_http_dossier_feedback_and_word_download']
            finally:
                if servers:servers[0].shutdown();servers[0].server_close()
                thread.join(timeout=5);assert not thread.is_alive(),'HTTP worker must stop before workspace cleanup'
        command=[sys.executable,'-m',module,'--workspace',str(workspace),'export',run['id'],'--output',str(home/'命令行 报告.docx')]
        exported=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=20,check=False);assert exported.returncode==0,exported.stderr
        assert json.loads(exported.stdout)['adapter']=='builtin-docx';checks.append('native_cli_word_export_without_optional_program')
        def connect(allow=False):
            command=[sys.executable,'-m',module,'--workspace',str(workspace),'mcp-serve','--project',project]+(['--allow-runs'] if allow else [])
            client=Client({'command':command},30)
            try:
                client.send('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'installed-acceptance','version':'1'}})
                client.send('notifications/initialized',{},notification=True)
                return client
            except Exception:
                client.close()
                raise
        def call(client,name,args):
            result=client.send('tools/call',{'name':name,'arguments':args});assert not result.get('isError'),result
            return result.get('structuredContent') or json.loads(result['content'][0]['text'])
        client=connect()
        try:
            tools=client.send('tools/list',{})['tools'];assert not any(t['name']=='run_create' for t in tools)
            assert project in call(client,'project_overview',{'project_id':project,'limit':6000})['text']
            assert 'synthetic rule' in call(client,'knowledge_citation',{'id':run['id'],'evidence_id':hit['id'],'limit':6000})['text']
        finally:client.close()
        checks.append('real_stdio_mcp_read_only_dossier_and_frozen_citation')
        client=connect(True)
        try:
            created=call(client,'run_create',{'client_key':'explicit-demo','mission':mission,'engine':'demo'})
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                status=call(client,'run_status',{'id':created['id']})
                if status['state']=='completed':break
                time.sleep(.05)
            assert status['state']=='completed',status
        finally:client.close()
        checks.append('real_stdio_explicit_demo_execution_and_saved_status')
        worker=subprocess.run([sys.executable,'-m',module,'--workspace',str(workspace),'worker','--once'],capture_output=True,text=True,encoding='utf-8',timeout=20,check=False)
        assert worker.returncode==0,worker.stderr
        status=worker_status(store,SPEC['id']);assert status['sessions'][0]['observed_state']=='stopped';assert status['sessions'][0]['tick_finished']
        checks.append('real_worker_once_heartbeat_tick_and_stop')
        assert not store.export_evidence()['records'];checks.append('private_material_stays_out_of_public_exchange')
        return {'product':SPEC['id'],'version':metadata['version'],'checks':checks,'model_backend':'scripted_substitute','paid_model_calls':0,'external_messages':0}


if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    print(json.dumps(verify(),ensure_ascii=False))
