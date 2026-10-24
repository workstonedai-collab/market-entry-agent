"""Actual MCP stdio wire, permissions, project scopes and durable task behavior."""
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core');SPEC=importlib.import_module(MODULE+'.product').SPEC
mcp=importlib.import_module(MODULE+'.mcp')


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=core.Store(Path(self.temp.name)/'workspace')
        self.mission={'question':'Synthetic MCP test','countries':['Vietnam'],'topics':['trade'],'project_id':'fixture','max_steps':8,'deadline_seconds':30}
    def init(self,adapter):
        response=adapter.dispatch({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}}})
        self.assertEqual(response['result']['protocolVersion'],'2025-11-25')
        self.assertIsNone(adapter.dispatch({'jsonrpc':'2.0','method':'notifications/initialized'}))
    def test_read_only_by_default_and_protocol_initialization_required(self):
        a=mcp.Adapter(self.store,SPEC)
        self.assertIn('error',a.dispatch({'jsonrpc':'2.0','id':1,'method':'tools/list'}));self.init(a)
        tools=a.dispatch({'jsonrpc':'2.0','id':2,'method':'tools/list'})['result']['tools']
        self.assertNotIn('run_create',[t['name'] for t in tools])
        self.assertTrue(all(t['annotations']['readOnlyHint'] for t in tools))
        self.assertIn('error',a.dispatch({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'run_create','arguments':{}}}))
    def test_public_country_tool_and_protocol_errors_are_separate(self):
        a=mcp.Adapter(self.store,SPEC);self.init(a)
        result=a.dispatch({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'country_compare','arguments':{'countries':['Vietnam']}}})
        self.assertFalse(result['result']['isError']);self.assertIsInstance(result['result']['structuredContent'],dict)
        invalid=a.dispatch({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'country_compare','arguments':{'countries':'bad'}}})
        self.assertTrue(invalid['result']['isError'])
        self.assertEqual(a.dispatch({'jsonrpc':'2.0','id':4,'method':'unknown'})['error']['code'],-32601)
    def test_saved_run_project_product_scope_cannot_be_bypassed(self):
        rid=self.store.create_run(SPEC['id'],self.mission,'demo');other=self.store.create_run(SPEC['id'],dict(self.mission,project_id='other'),'demo')
        a=mcp.Adapter(self.store,SPEC,project='fixture')
        self.assertEqual(a.call('run_status',{'id':rid})['id'],rid)
        with self.assertRaises(ValueError):a.call('run_status',{'id':other})
        with self.assertRaises(ValueError):a.call('project_read',{'project_id':'other'})
        foreign=self.store.create_run('other-product',self.mission,'demo')
        with self.assertRaises(ValueError):a.call('run_status',{'id':foreign})
    def test_explicit_create_and_retries_use_saved_command_without_duplicate_model_calls(self):
        a=mcp.Adapter(self.store,SPEC,allow_runs=True,project='fixture')
        args={'client_key':'create-fixture','mission':self.mission,'engine':'demo'}
        result=a.call('run_create',args);deadline=time.monotonic()+5
        while a.run(result['id'])['state'] not in ('completed','failed') and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(a.run(result['id'])['state'],'completed')
        replay=mcp.Adapter(core.Store(self.store.workspace),SPEC,True,'fixture').call('run_create',args)
        self.assertEqual(replay['id'],result['id']);self.assertTrue(replay['reused'])
        self.assertEqual(a.run(result['id'])['runtime']['model_calls'],0)
        with self.assertRaises(ValueError):a.call('run_create',dict(args,engine='model'))
        with self.assertRaises(ValueError):a.call('run_create',dict(args,client_key='another',mission=dict(self.mission,project_id='other')))
    def test_bounded_result_paging_and_explicit_controls(self):
        run=core.Agent(self.store,SPEC).run(self.mission,'demo');a=mcp.Adapter(self.store,SPEC,True)
        first=a.call('run_report',{'id':run['id'],'offset':0,'limit':30})
        self.assertEqual(len(first['text']),30);self.assertTrue(first['truncated'])
        next_page=a.call('run_report',{'id':run['id'],'offset':30,'limit':30});self.assertEqual(next_page['offset'],30)
        queued=self.store.create_run(SPEC['id'],self.mission,'demo')
        self.assertEqual(a.call('run_control',{'id':queued,'state':'paused'})['state'],'paused')
        self.assertEqual(a.call('run_control',{'id':queued,'state':'cancelled'})['state'],'cancelled')
    def test_malformed_stream_is_bounded_and_notifications_have_no_output(self):
        requests=['not-json',json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}}),json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'}),json.dumps({'jsonrpc':'2.0','id':2,'method':'ping'})]
        target=io.StringIO();mcp.serve(self.store,SPEC,input_stream=io.StringIO('\n'.join(requests)+'\n'),output_stream=target)
        responses=[json.loads(line) for line in target.getvalue().splitlines()]
        self.assertEqual(len(responses),3);self.assertEqual(responses[0]['error']['code'],-32700)
        self.assertEqual(responses[1]['result']['protocolVersion'],'2025-06-18');self.assertEqual(responses[-1]['id'],2)
    def test_cli_stdio_has_only_protocol_lines_and_no_banner(self):
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'}]
        result=subprocess.run([sys.executable,'-m',MODULE,'--workspace',str(self.store.workspace),'mcp-serve','--project','fixture'],input='\n'.join(json.dumps(r) for r in requests)+'\n',capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        responses=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(responses),2);self.assertTrue(all(x['jsonrpc']=='2.0' for x in responses))
        self.assertNotIn('run_create',[t['name'] for t in responses[-1]['result']['tools']])

if __name__=='__main__':unittest.main()
