"""Replay attributed historical sources through installed business paths; no paid model calls."""
import argparse
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import tempfile
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]


def verify(workspace=None, live=False):
    metadata = json.loads((ROOT/'agent.json').read_text(encoding='utf-8'))
    module = metadata['python_module']
    core = importlib.import_module(module+'.core')
    Workflow = importlib.import_module(module+'.workflow').Workflow
    SPEC = importlib.import_module(module+'.product').SPEC
    case = json.loads((ROOT/'examples/public-project-case.json').read_text(encoding='utf-8'))
    clean = {k:v for k,v in os.environ.items() if not k.startswith('AGENT_')}
    receipts=[]
    if live:
        for source in case['sources']:
            request=Request(source['url'],headers={'User-Agent':'PublicProjectCase/0.6 (source availability check)'})
            try:
                with urlopen(request,timeout=25) as response:
                    raw=response.read(20_000_001)
                    if response.status!=200 or len(raw)>20_000_000:
                        raise ValueError('Source response exceeds 20 MB verification bound')
                    content_type=response.headers.get('Content-Type','')
                    if not (raw.startswith(b'%PDF') or b'<html' in raw.lower() or b'<!doctype' in raw.lower()):
                        raise ValueError('Unexpected source content type')
                    receipts.append({'url':source['url'],'state':'retrieved','http_status':response.status,'content_type':content_type,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                                     'note':'Availability/hash only; fixture summaries were source-read separately, not automatically semantically verified.'})
            except (HTTPError, URLError, ValueError, TimeoutError) as exc:
                receipts.append({'url':source['url'],'state':'unavailable','http_status':getattr(exc,'code',None),'error_type':type(exc).__name__,
                                 'note':'Source unavailable to this direct HTTP route. Replay still uses the attributed historical summary; no live fetch success is claimed.'})
    if workspace and Path(workspace).exists() and any(Path(workspace).iterdir()):
        raise ValueError('Public case requires an empty isolated workspace')
    with patch.dict(os.environ,clean,clear=True), tempfile.TemporaryDirectory(prefix='public-case-') as temporary:
        store=core.Store(workspace or Path(temporary)/'公开案例 workspace')
        flow=Workflow(store,SPEC['id']);project=case['project_id'];references={};runs=[];states=[]
        for command in case['operator_commands']:
            flow.save_command(project,copy.deepcopy(command))
        def resolve(value):
            if isinstance(value,str): return references.get(value,value)
            if isinstance(value,list):return [resolve(v) for v in value]
            if isinstance(value,dict):return {k:resolve(v) for k,v in value.items()}
            return value
        for phase in case['phases']:
            n=phase['source']; source=case['sources'][n]
            store.import_evidence({'schema':'field-evidence/v1','records':[source]})
            eid=next(r['id'] for r in store.export_evidence()['records'] if r['url']==source['url'])
            references['$source'+str(n)]=eid
            commands=resolve(copy.deepcopy(phase['commands']))
            report={'evaluation_backend':'scripted_substitute','title':'历史公开案例回放 · '+source['title'],'summary':source['body'],
                'findings':[{'claim':source['body'],'evidence_ids':[eid]}],
                'assessment':'历史资料与虚构项目条件的流程演练。来源摘要、经营推断和拟议工作分开保存；不代表当前判断或真实企业结果。',
                'actions':['核对原始资料和实际业务条件。'],'uncertainties':case['limits'],'follow_up':['有新资料时更新同一项目。'],
                'priority':'watch','evidence_ids':[eid]}
            if commands:report['project_update']={'commands':commands}
            actions=[{'action':'project_state','arguments':{}},{'action':'read_evidence','arguments':{'id':eid}},
                     {'action':'finish','arguments':{'report':report}}]
            class Substitute:
                def next(self,messages,timeout):return actions.pop(0)
            mission={'project_id':project,'question':'历史公开案例回放：'+source['title'],'countries':source['countries'],'topics':source['topics'],
                'context':'Historical public sources; fictional operator conditions; scripted substitute, not real model evaluation.','skill_ids':['project-continuity'],
                'max_steps':8,'deadline_seconds':60}
            run=core.Agent(store,SPEC,Substitute).run(mission,'model')
            assert run['state']=='completed',run.get('error')
            assert store.get_run(run['id'])['report']['sources'][0]['url']==source['url']
            assert 'project_update' not in report or run['report']['project_result']['state']=='applied',run['report']
            runs.append(run['id']);states.append(flow.state(project))
        final=flow.state(project)
        repeat=flow.check(project)
        if SPEC['id']=='georisk-agent':
            assert len(final['event'])==1 and len(final['alerts'])==2
            assert len(final['event'][0]['data']['evidence_ids'])==2
            assert all(a['data']['exposure_id']=='fictional-route' for a in final['alerts'])
            assert repeat['alerts_created']==0
            check_names=['cross_source_same_event','two_meaningful_changes','unrelated_exposure_silent','repeat_check_silent','saved_source_linked_reports']
        else:
            assert len(final['option'])==2 and len(final['stage'])==1
            assert final['assumption'][0]['data']['status']=='needs_review'
            assert len(final['reviews'])==1 and final['reviews'][0]['data']['stage_ids']==['verify-importer']
            assert repeat['reviews_created']==0
            assert final['stage'][0]['data']['status']=='planned'
            check_names=['comparable_entry_options','proposed_stage_not_completed','new_source_targets_assumption_options_and_stage','repeat_check_silent','saved_source_linked_reports']
        assert core.Agent(store,SPEC).run(resume=runs[0])['report']==store.get_run(runs[0])['report']
        return {'product':SPEC['id'],'version':metadata['version'],'platform':platform.system(),'python':platform.python_version(),
            'case_type':case['case_type'],'project_id':project,'checks':check_names,'saved_runs':runs,'sources':[{'url':s['url'],'published_at':s['published_at']} for s in case['sources']],
            'model_backend':'scripted_substitute','paid_model_calls':0,'live_fetches':receipts,'live_sources_complete':bool(receipts) and all(r['state']=='retrieved' for r in receipts),'scope':'Historical public-source replay with fictional enterprise/exposure. Not current advice, forecast accuracy or live-model quality evaluation.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workspace');parser.add_argument('--live',action='store_true');parser.add_argument('--output');args=parser.parse_args()
    result=verify(args.workspace,args.live)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(text,encoding='utf-8')
    print(text)
