"""Behavior checks for report writing, source receipts, comparisons and decision aids."""
import copy
import importlib
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core')
SPEC=importlib.import_module(MODULE+'.product').SPEC
health=importlib.import_module(MODULE+'.source_health')
net=importlib.import_module(MODULE+'.net')
decision=importlib.import_module(MODULE+'.decision')
Workflow=importlib.import_module(MODULE+'.workflow').Workflow
ROOT=Path(__file__).resolve().parents[1]


class DecisionPaths(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=core.Store(Path(self.temp.name)/'private workspace')
        self.case=json.loads((ROOT/'examples/public-project-case.json').read_text(encoding='utf-8'))
        self.store.import_evidence({'schema':'field-evidence/v1','records':self.case['sources']})
        self.ids={f'$source{i}':next(e['id'] for e in self.store.export_evidence()['records'] if e['url']==s['url']) for i,s in enumerate(self.case['sources'])}
        self.eid=self.ids['$source0'];source=self.case['sources'][0]
        self.mission={'question':'Report behavior fixture','countries':source['countries'],'topics':source['topics'],'max_steps':8,'deadline_seconds':30}
        self.flow=Workflow(self.store,SPEC['id'])
        for c in self.case['operator_commands']:self.flow.save_command('case',c)
    def resolve(self,value):
        if isinstance(value,str):return self.ids.get(value,value)
        if isinstance(value,list):return [self.resolve(v) for v in value]
        if isinstance(value,dict):return {k:self.resolve(v) for k,v in value.items()}
        return value
    def report(self):
        return {'title':'Saved analysis','summary':'Fixture summary','assessment':'Conditional analysis','findings':[], 'actions':[],'uncertainties':['Fixture'],'follow_up':[],'evidence_ids':[],'priority':'routine'}
    def register(self,kind='feed'):
        self.store.register_sources({'sources':[{'id':'official','url':'https://example.org/feed','allowed_hosts':['example.org'],'kind':kind,'countries':self.mission['countries'],'topics':self.mission['topics']}]})
    def test_actual_model_context_gets_versioned_writing_skill_without_extra_call(self):
        captured=[];report=self.report();report['project_changes']=[{'untrusted':'fake host result'}]
        class Model:
            def next(_,messages,timeout):captured.extend(messages);return {'action':'finish','arguments':{'report':report}}
        run=core.Agent(self.store,SPEC,Model).run(self.mission,'model')
        self.assertEqual(run['state'],'completed',run['error']);self.assertEqual(run['runtime']['model_calls'],1)
        skill=self.store.meta(run['id'])['writing_skill']
        self.assertTrue(any(skill['instructions'] in m['content'] for m in captured if m['role']=='system'))
        self.assertEqual(run['report']['writing_skill']['version'],skill['version'])
        self.assertEqual(run['runtime']['skill_versions']['report-writing'],skill['version'])
        self.assertNotIn('project_changes',run['report'])
        self.assertEqual(self.store.get_run(run['id'])['report'],run['report'])
    def test_writing_skill_is_frozen_across_failure_and_resume(self):
        captured=[]
        class Failing:
            def next(_,messages,timeout):captured.extend(messages);raise RuntimeError('fixture_failure')
        first=core.Agent(self.store,SPEC,Failing).run(self.mission,'model');self.assertEqual(first['state'],'failed')
        frozen=self.store.meta(first['id'])['writing_skill']
        class Finish:
            def next(_,messages,timeout):
                self.assertTrue(any(frozen['instructions'] in m['content'] for m in messages));return {'action':'finish','arguments':{'report':self.report()}}
        skills=importlib.import_module(MODULE+'.skills')
        changed=copy.deepcopy(skills.BUILTINS);changed[0]['instructions']='Changed file after interruption'
        with patch.object(skills,'BUILTINS',changed):done=core.Agent(self.store,SPEC,Finish).run(resume=first['id'])
        self.assertEqual(done['state'],'completed');self.assertEqual(done['report']['writing_skill']['version'],frozen['version'])
    def test_tool_catalog_matches_actual_task_prerequisites_and_scope(self):
        agent=core.Agent(self.store,SPEC)
        names={t['name'] for t in agent.task_tools(self.mission)}
        self.assertFalse(names.intersection({'web_search','fetch_page','fetch_feed','project_state'}))
        self.assertNotIn('"name": "web_search"',agent.system(self.mission))
        self.register('page');self.assertIn('fetch_page',{t['name'] for t in agent.task_tools(self.mission)})
        self.assertNotIn('fetch_feed',{t['name'] for t in agent.task_tools(self.mission)})
        self.assertIn('web_search',{t['name'] for t in agent.task_tools(dict(self.mission,search_queries=['public query']))})
        other=dict(self.mission,countries=['Unrelated']);self.assertNotIn('fetch_page',{t['name'] for t in agent.task_tools(other)})
    def test_success_failure_and_staleness_keep_last_success(self):
        self.register();self.assertEqual(health.overview(self.store)['never_fetched'],1)
        body=b'<rss><channel><item><title>Source update</title><link>https://example.org/item</link><description>Public source fixture</description></item></channel></rss>'
        with patch.object(core,'fetch_public_https',return_value=body):core.fetch_feed(self.store,'official')
        good=health.overview(self.store)['sources'][0];self.assertEqual(good['freshness'],'fresh')
        with patch.object(core,'fetch_public_https',side_effect=ValueError('source_network_or_timeout')):
            with self.assertRaises(ValueError):core.fetch_feed(self.store,'official')
        bad=health.overview(self.store)['sources'][0];self.assertEqual(bad['last_success'],good['last_success']);self.assertTrue(bad['latest_attempt_failed']);self.assertEqual(bad['last_error'],'source_network_or_timeout')
        self.assertEqual(health.overview(self.store,datetime.now(timezone.utc)+timedelta(days=2))['stale'],1)
        reopened=core.Store(self.store.workspace);self.assertEqual(health.overview(reopened)['sources'][0]['failures'],1)
    def test_cached_page_does_not_advance_network_success_time(self):
        self.register('page');body=('<html><article>'+('Public fixture source paragraph. '*8)+'</article></html>').encode()
        with patch.object(core,'fetch_public_https',return_value=body) as fetch:
            first=net.fetch_page(self.store,source_id='official');time=health.overview(self.store)['sources'][0]['last_success'];second=net.fetch_page(self.store,source_id='official')
        self.assertFalse(first['cached']);self.assertTrue(second['cached']);self.assertEqual(fetch.call_count,1)
        row=health.overview(self.store)['sources'][0];self.assertEqual(row['last_success'],time);self.assertTrue(row['cached'])
    def test_exception_body_is_not_persisted(self):
        self.register()
        with self.assertRaises(ValueError):health.retrieve(self.store,'official',lambda:(_ for _ in ()).throw(ValueError('credential-like body https://example.org/?token=private-test')))
        self.assertEqual(health.overview(self.store)['sources'][0]['last_error'],'retrieval_failed')
    def test_refresh_interval_requires_bounded_number(self):
        for value in [False,0,721,'24']:
            with self.assertRaises(ValueError):self.store.register_sources({'sources':[{'id':'bad','refresh_hours':value}]})
    def test_decision_aids_validate_references_and_survive_export(self):
        report=self.report();report['decision_options']=[{'name':'Conditional route','fit':'Buyer requires local support','tradeoff':'Less direct customer access','requirements':'Cost quote unknown','next_check':'Request service quote','evidence_ids':[self.eid]}]
        report['validation_priorities']=[{'question':'Can the partner support the equipment?','why_first':'Changes delivery feasibility','next_step':'Request written scope','if_supported':'Compare offer','if_not':'Try another route','evidence_ids':[self.eid]}]
        decision.validate(report,{self.eid});self.assertIn('Cost quote unknown','\n'.join(decision.markdown(report)))
        report['decision_options'][0]['evidence_ids']=['unread']
        with self.assertRaisesRegex(ValueError,'unread'):decision.validate(report,{self.eid})
    def test_product_changes_or_option_requirements_are_saved(self):
        if MODULE=='georisk_agent':
            for command in self.resolve(self.case['phases'][0]['commands']):self.flow.save_command('case',command)
            self.flow.check('case')
            for command in self.resolve(self.case['phases'][1]['commands']):self.flow.save_command('case',command)
            self.flow.check('case');alerts=self.flow.state('case')['alerts'];latest=alerts[-1]['data']
            self.assertTrue(latest['previous']);self.assertTrue(any(d['field']=='severity' for d in latest['changes']))
            self.assertTrue(latest['new_evidence_ids']);self.assertTrue(latest['source_details'][0]['saved_excerpt'])
            with self.store.tasks() as db:self.assertNotIn('changes',self.flow.get(db,'case','alert',alerts[-1]['id'])['data'])
            self.assertEqual(self.flow.check('case')['alerts_created'],0)
        else:
            command=self.resolve(self.case['phases'][0]['commands'][0]);command['data'].update(tradeoff='Lower fixed investment, less channel control',requirements='Written importer/service scope; budget unknown',next_validation='Check buyer demand before spending on service stock')
            self.flow.save_command('case',command);option=self.flow.state('case')['comparison'][0]
            self.assertEqual(option['tradeoff'],command['data']['tradeoff']);self.assertEqual(self.flow.history('case','option',command['id'])[0]['data']['requirements'],command['data']['requirements'])

    def test_model_result_and_product_extensions_survive_reopen_and_markdown(self):
        report=self.report();report['evidence_ids']=[self.eid];report['priority']='watch'
        mission=dict(self.mission,project_id='case')
        if MODULE=='georisk_agent':report['project_update']={'commands':self.resolve(self.case['phases'][0]['commands'])}
        else:
            report['decision_options']=[{'name':'Conditional entry','fit':'Buyer confirmed','tradeoff':'Channel control','requirements':'Unknown quotation','next_check':'Obtain written offer','evidence_ids':[self.eid]}]
            report['validation_priorities']=[{'question':'Buyer demand','why_first':'Changes investment','next_step':'Interview buyer','if_supported':'Compare offers','if_not':'Defer spending','evidence_ids':[self.eid]}]
        actions=[{'action':'project_state','arguments':{}},{'action':'read_evidence','arguments':{'id':self.eid}},{'action':'finish','arguments':{'report':report}}]
        class Model:
            def next(_,messages,timeout):return actions.pop(0)
        run=core.Agent(self.store,SPEC,Model).run(mission,'model');self.assertEqual(run['state'],'completed',run['error'])
        saved=core.Store(self.store.workspace).get_run(run['id'])['report'];self.assertEqual(saved,run['report'])
        if MODULE=='georisk_agent':
            self.assertEqual(len(saved['project_changes']),1);self.assertIn('本次变化与业务影响',core.markdown(saved));self.assertEqual(saved['project_changes'][0]['data']['source_details'][0]['id'],self.eid)
        else:
            self.assertEqual(len(saved['decision_options']),1);self.assertIn('Unknown quotation',core.markdown(saved));self.assertIn('Defer spending',core.markdown(saved))
    def test_saved_report_review_cli_does_not_call_a_provider(self):
        report=self.report()
        class Model:
            def next(_,messages,timeout):return {'action':'finish','arguments':{'report':report}}
        run=core.Agent(self.store,SPEC,Model).run(self.mission,'model')
        source=Path(self.temp.name)/'saved-report.json';source.write_text(json.dumps(run['report']),encoding='utf-8');output=Path(self.temp.name)/'review'
        result=subprocess.run([sys.executable,str(ROOT/'scripts/evaluate_reports.py'),'--report',str(source),'--output',str(output)],capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
        self.assertFalse(json.loads(result.stdout.decode('utf-8'))['live_model_called'])
        review=json.loads((output/'review.json').read_text(encoding='utf-8'));self.assertTrue(review['references_present_in_source_list']);self.assertTrue(review['human_review'])
