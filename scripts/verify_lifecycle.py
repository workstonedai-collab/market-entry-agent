"""Installed CLI lifecycle replay with attributed historical public source summaries."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def verify():
    meta=json.loads((ROOT/'agent.json').read_text(encoding='utf-8'));module=meta['python_module']
    core=importlib.import_module(module+'.core');SPEC=importlib.import_module(module+'.product').SPEC
    Knowledge=importlib.import_module(module+'.knowledge').Knowledge
    Monitors=importlib.import_module(module+'.monitoring').Monitors
    Learning=importlib.import_module(module+'.learning').Learning
    source=json.loads((ROOT/'examples/public-project-case.json').read_text(encoding='utf-8'))['sources'][0]
    clean={k:v for k,v in os.environ.items() if not k.startswith('AGENT_')}
    with patch.dict(os.environ,clean,clear=True),tempfile.TemporaryDirectory(prefix='lifecycle-') as folder:
        home=Path(folder);workspace=home/'用户资料 workspace';project='historical-example'
        def cli(area,action,payload=None,file=None):
            command=[sys.executable,'-m',module,'--workspace',str(workspace),'manage',area,action,'--project',project]
            if payload is not None:
                data=home/'command.json';data.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8');command+=['--data',str(data)]
            if file:command+=['--file',str(file)]
            result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=30,check=False)
            if result.returncode:raise AssertionError(result.stderr)
            return json.loads(result.stdout)
        collection=cli('knowledge','create',{'name':'Historical public summary'})
        document=home/'历史公开材料.txt';document.write_text('Attributed historical source: '+source['url']+'\n'+source['body'],encoding='utf-8')
        imported=cli('knowledge','import',{'collection_id':collection['id'],'metadata':{k:source[k] for k in ('title','countries','topics','published_at')}},document)
        assert imported['state']=='completed',imported
        store=core.Store(workspace);kb=Knowledge(store,SPEC['id']);pin=kb.pin(project,[collection['id']]);eid=kb.search(pin)[0]['id']
        mission={'project_id':project,'question':'历史公开材料的保存与出处回放','countries':source['countries'],'topics':source['topics'],'knowledge_ids':[collection['id']],'max_steps':8,'deadline_seconds':60}
        cli('learning','policy',{'policy':{'mode':'local','auto_activate':False,'max_calls_per_day':0}})
        actions=iter([{'action':'read_evidence','arguments':{'id':eid}},{'action':'finish','arguments':{'report':{'evaluation_backend':'scripted_substitute','title':'Historical lifecycle replay','summary':source['body'],'assessment':'Attributed historical summary; this verifies storage and scope, not current conditions or independent model quality.','findings':[{'claim':source['body'],'evidence_ids':[eid]}],'actions':['Check original source and current applicability.'],'uncertainties':['No live model interpretation in this replay.'],'follow_up':[],'evidence_ids':[eid],'priority':'routine'}}}])
        class Scripted:
            def next(self,*args,**kwargs):return next(actions)
        run=core.Agent(store,SPEC,Scripted).run(mission,'model');assert run['state']=='completed',run.get('error')
        assert core.Store(workspace).get_run(run['id'])['report']['sources'][0]['document_location']
        config={'name':'Historical local-material watch','mission':mission,'kind':'theme' if SPEC['id']=='georisk-agent' else 'operating','source_ids':[],'criteria':'Notice new substantive source text; retain original date.','include_terms':[],'exclude_terms':[],'min_sources':1,'check_interval':60,'digest_interval':60,'timezone':'UTC+00:00','quiet_hours':[],'engine':'rules','notify_first_run':False}
        monitor=cli('monitors','save',{'config':config});assert monitor['state']=='draft'
        assert Monitors(store,SPEC['id']).check(project,monitor['id'],refresh=False)['state']=='not_due_or_not_confirmed'
        preview=cli('monitors','preview',{'id':monitor['id']});cli('monitors','confirm',{'id':monitor['id'],'hash':preview['hash']})
        watches=Monitors(store,SPEC['id']);active=watches.get(project,monitor['id']);stamp=active['next_due']+1
        assert watches.check(project,monitor['id'],stamp,False)['state']=='baseline_saved'
        assert watches.check(project,monitor['id'],stamp+61,False)['state']=='no_change'
        learned=cli('learning','feedback',{'run_id':run['id'],'lesson':'分别保存原始资料日期与本次发现日期。'})
        assert learned['state']=='completed',learned
        skills=cli('learning','status')['skills'];assert skills and skills[0]['source_run_ids']==[run['id']]
        cli('learning','activate',{'name':skills[0]['name'],'version':skills[0]['version']})
        assert Learning(store,SPEC['id']).active(project)
        assert store.export_evidence()['records']==[], 'Private import must not enter public evidence export'
        return {'product':SPEC['id'],'version':meta['version'],'checks':['installed_cli_private_import','attributed_historical_public_source','selected_collection_report','saved_report_reopen_with_location','unconfirmed_watch_blocked','explicit_confirmation','baseline_and_no_change_silence','feedback_to_versioned_skill','private_export_boundary'],'source_url':source['url'],'model_backend':'scripted_substitute','paid_model_calls':0,'external_messages':0}


if __name__=='__main__':print(json.dumps(verify(),ensure_ascii=False))
