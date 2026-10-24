"""Bounded research branches and an actual opt-in MCP search subprocess."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core');SPEC=importlib.import_module(MODULE+'.product').SPEC
depth=importlib.import_module(MODULE+'.depth');client=importlib.import_module(MODULE+'.mcp_client');net=importlib.import_module(MODULE+'.net')

STUB='''import sys,json,os,time
log=sys.argv[1]
for line in sys.stdin:
 m=json.loads(line)
 with open(log,'a',encoding='utf-8') as f:f.write(json.dumps({'message':m,'private_key_present':'AGENT_MODEL_API_KEY' in os.environ,'allowed_key_present':'SYNTHETIC_SEARCH_TOKEN' in os.environ})+'\\n')
 if len(sys.argv)>2:time.sleep(20)
 if 'id' not in m:continue
 method=m['method']
 if method=='initialize':result={'protocolVersion':'2025-11-25','capabilities':{'tools':{}},'serverInfo':{'name':'synthetic fixture','version':'1'}}
 elif method=='tools/list':result={'tools':[{'name':'public_search','inputSchema':{'type':'object'}}]}
 else:result={'content':[],'structuredContent':{'results':[{'title':'Synthetic discovery','url':'https://www.gov.uk/example','body':'Discovery snippet, not a rule.'},{'title':'Outside source','url':'https://example.org/outside','body':'Must be excluded.'}]},'isError':False}
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
'''


class DepthExternal(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.store=core.Store(self.root/'workspace');self.agent=core.Agent(self.store,SPEC)
        self.mission={'question':'PRIVATE COMPANY QUOTE','context':'DO NOT SEND PRIVATE BACKGROUND','countries':['Vietnam'],'topics':['trade'],'max_steps':16,'deadline_seconds':30,
          'public_search':{'terms':['Vietnam','CPTPP'],'facets':['rules','effective date'],'max_queries':3},'research_depth':{'max_branches':2,'max_queries_per_branch':1}}
        self.store.import_evidence({'schema':'field-evidence/v1','records':[{'title':'Synthetic body','body':'Original source text.','url':'https://example.org/body','countries':['Vietnam'],'topics':['trade'],'status':'synthetic','published_at':'2024-01-01'}]})
        self.eid=self.store.export_evidence()['records'][0]['id'];self.rid=self.store.create_run(SPEC['id'],self.mission,'model');self.run=self.store.get_run(self.rid)
        self.stub=self.root/'server.py';self.stub.write_text(STUB,encoding='utf-8');self.log=self.root/'wire.jsonl';self.config=self.root/'mcp-private.json'
        self.profile={'command':[sys.executable,str(self.stub),str(self.log)],'tool':'public_search','query_field':'query','arguments':{'limit':3},'env_allowlist':['SYNTHETIC_SEARCH_TOKEN'],'allowed_hosts':['www.gov.uk']}
        self.config.write_text(json.dumps({'public_search_profiles':{'public':self.profile}}),encoding='utf-8')
    def args(self,bid='origin',facet=0):return {'id':bid,'question':'Decision question '+bid,'term_ids':[0],'facet_id':facet,'reason':'LOCAL PRIVATE REASON'}
    def search_result(self,*args,**kwargs):return {'query':args[2],'results':[self.store.read(self.eid)]}
    def test_optional_depth_requires_scope_and_has_bounded_configuration(self):
        bad=dict(self.mission);bad.pop('public_search')
        with self.assertRaises(ValueError):core.validate_mission(bad)
        with self.assertRaises(ValueError):core.validate_mission(dict(self.mission,research_depth={'max_branches':5}))
        plain=dict(self.mission);plain.pop('research_depth')
        self.assertNotIn('research_branch',[t['name'] for t in self.agent.task_tools(plain)])
        self.assertIn('research_branch',[t['name'] for t in self.agent.task_tools(self.mission)])
    def test_branch_query_reuse_and_caps_survive_reopening(self):
        with patch.object(net,'search_query',side_effect=self.search_result) as remote:
            first=depth.search(self.store,self.run,self.args(),5)
            again=depth.search(core.Store(self.store.workspace),self.run,self.args(),5)
            self.assertTrue(again['reused']);self.assertEqual(remote.call_count,1)
            self.assertEqual(first['branch']['revision'],2)
            with self.assertRaisesRegex(ValueError,'Per-branch'):depth.search(self.store,self.run,self.args(facet=1),5)
            depth.search(self.store,self.run,self.args('alternative',1),5)
            with self.assertRaisesRegex(ValueError,'branch budget'):depth.search(self.store,self.run,self.args('extra'),5)
            self.assertEqual(remote.call_count,2)
        self.assertEqual(len(depth.snapshot(core.Store(self.store.workspace),self.rid)),2)
    def test_global_query_budget_is_shared_between_branches(self):
        mission=dict(self.mission,public_search=dict(self.mission['public_search'],max_queries=1));rid=self.store.create_run(SPEC['id'],mission,'model');run=self.store.get_run(rid)
        with patch.object(net,'search_query',side_effect=self.search_result) as remote:
            depth.search(self.store,run,self.args(),5)
            with self.assertRaisesRegex(ValueError,'query budget'):depth.search(self.store,run,self.args('other',1),5)
            self.assertEqual(remote.call_count,1)
        self.assertEqual(depth.snapshot(self.store,rid)[1]['queries'][0]['state'],'failed')
    def test_close_branch_cites_only_read_body_and_keeps_stop_reason(self):
        with patch.object(net,'search_query',side_effect=self.search_result):depth.search(self.store,self.run,self.args(),5)
        args={'id':'origin','expected_revision':2,'conclusion':'Conditional conclusion','evidence_ids':[self.eid],'stop_reason':'No additional useful public evidence'}
        with self.assertRaises(ValueError):depth.close(self.store,self.run,args)
        self.run['steps']=[{'action':'read_evidence','observation':self.store.read(self.eid)}]
        result=depth.close(self.store,self.run,args);self.assertEqual(result['branch']['state'],'closed')
        self.assertEqual(depth.close(self.store,self.run,args),result)
        with self.assertRaises(ValueError):depth.search(self.store,self.run,self.args(),5)
    def test_actual_agent_direct_report_and_exports_keep_branch_state(self):
        eid=self.eid
        report={'title':'Synthetic report','summary':'Conditional choice','assessment':'Original direct output.','findings':[{'claim':'Source text','evidence_ids':[eid]}],'actions':['Obtain quote'],'uncertainties':['Quote missing'],'follow_up':[],'evidence_ids':[eid],'priority':'watch'}
        actions=[{'action':'research_branch','arguments':self.args()}, {'action':'read_evidence','arguments':{'id':eid}},
          {'action':'close_branch','arguments':{'id':'origin','expected_revision':2,'conclusion':'Source condition requires a quote','stop_reason':'Useful sources exhausted','evidence_ids':[eid]}},
          {'action':'finish','arguments':{'report':report}}]
        seen=[]
        class Model:
            def next(self,messages,timeout):seen.extend(messages);return actions.pop(0)
        with patch.object(net,'search_query',side_effect=self.search_result):run=core.Agent(self.store,SPEC,Model).run(self.mission,'model')
        self.assertEqual(run['state'],'completed',run['error']);self.assertEqual(run['report']['assessment'],'Original direct output.')
        self.assertEqual(run['report']['research_branches'][0]['state'],'closed');self.assertIn('Research branches',core.markdown(run['report']))
        self.assertIn('SAVED_RESEARCH_BRANCHES',json.dumps(seen))
        self.assertEqual(core.Store(self.store.workspace).get_run(run['id'])['report'],run['report'])
    def test_real_mcp_wire_sends_only_public_query_and_explicit_env(self):
        env={'AGENT_MCP_CONFIG':str(self.config),'AGENT_MODEL_API_KEY':'SYNTHETIC_PRIVATE_KEY','SYNTHETIC_SEARCH_TOKEN':'SYNTHETIC_ALLOWED_KEY'}
        with patch.dict(os.environ,env):
            config=client.profile('public');result=client.search(self.store,self.mission,'Vietnam rules',5,config)
            cached=client.search(self.store,self.mission,'Vietnam rules',5,config)
        rows=[json.loads(line) for line in self.log.read_text().splitlines()];calls=[r['message'] for r in rows if r['message']['method']=='tools/call']
        self.assertEqual(calls[0]['params']['arguments'],{'limit':3,'query':'Vietnam rules'})
        self.assertEqual(len(calls),1);self.assertTrue(cached['cached'])
        self.assertTrue(all(not r['private_key_present'] and r['allowed_key_present'] for r in rows))
        self.assertEqual(len(result['results']),1);self.assertEqual(result['results'][0]['retrieval_kind'],'search_snippet')
        self.assertNotIn('DO NOT SEND',self.log.read_text());self.assertNotIn('PRIVATE COMPANY',self.log.read_text())
    def test_frozen_external_profile_works_after_configuration_file_removed(self):
        mission=dict(self.mission,mcp_search='public')
        class Broken:
            def next(self,messages,timeout):raise RuntimeError('Synthetic interruption')
        with patch.dict(os.environ,{'AGENT_MCP_CONFIG':str(self.config)}):failed=core.Agent(self.store,SPEC,Broken).run(mission,'model')
        self.config.unlink();seen=[]
        actions=[{'action':'adaptive_search','arguments':{k:self.args()[k] for k in ('term_ids','facet_id','reason')}},
                 {'action':'finish','arguments':{'report':{'title':'Conditional','summary':'Need more evidence','assessment':'No usable original body.','findings':[],'actions':[],'uncertainties':['Missing original source'],'follow_up':[],'evidence_ids':[],'priority':'routine'}}}]
        class Recovered:
            def next(self,messages,timeout):seen.extend(messages);return actions.pop(0)
        with patch.object(client,'search',return_value={'query':'Vietnam rules','results':[]}) as remote:done=core.Agent(self.store,SPEC,Recovered).run(resume=failed['id'])
        self.assertEqual(done['state'],'completed',done['error']);self.assertEqual(remote.call_args.args[-1]['name'],'public')
        self.assertNotIn(str(self.stub),json.dumps(seen));self.assertIn('public',done['runtime']['integration_versions'])
    def test_external_process_timeout_is_bounded(self):
        profile=dict(self.profile,command=self.profile['command']+['hang'],name='public',version='synthetic')
        started=time.monotonic()
        with self.assertRaisesRegex(ValueError,'timeout'):client.search(self.store,self.mission,'different public query',.1,profile)
        self.assertLess(time.monotonic()-started,4)
    def test_skill_contract_does_not_grant_missing_tools_or_execute_scripts(self):
        folder=self.root/'skills'/'fixture';folder.mkdir(parents=True)
        (folder/'SKILL.md').write_text('---\nname: synthetic-contract\ndescription: Synthetic procedure\ninputs: Mission and source excerpts\noutputs: Conditional interpretation\nrequires_tools: unavailable_tool\n---\nUse available evidence. Do not execute scripts.',encoding='utf-8')
        actions=[{'action':'load_skill','arguments':{'name':'synthetic-contract'}},{'action':'finish','arguments':{'report':{'title':'Synthetic','summary':'Conditional','assessment':'Direct report.','findings':[],'actions':[],'uncertainties':[],'follow_up':[],'evidence_ids':[],'priority':'routine'}}}]
        class Model:
            def next(self,messages,timeout):return actions.pop(0)
        with patch.dict(os.environ,{'AGENT_SKILLS_DIR':str(folder.parent)}):run=core.Agent(self.store,SPEC,Model).run(self.mission,'model')
        self.assertEqual(run['state'],'completed');observation=run['steps'][0]['observation']
        self.assertEqual(observation['missing_tools'],['unavailable_tool']);self.assertFalse(observation['scripts_executed'])
        self.assertEqual(observation['contract']['outputs'],'Conditional interpretation')

if __name__=='__main__':unittest.main()
