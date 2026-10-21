import importlib,json,os,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
MODULE='market_entry_agent'
c=importlib.import_module(MODULE+'.countries'); core=importlib.import_module(MODULE+'.core');research=importlib.import_module(MODULE+'.research');product=importlib.import_module(MODULE+'.product')
class CountryTests(unittest.TestCase):
 def test_all_scores_reproduce_contributions_without_imputing(self):
  stats=c.catalog()['coverage'];self.assertEqual(stats['economies'],215);self.assertEqual(stats['combined'],101)
  for raw in c.dataset()['countries']:
   row=c.baseline(raw['code']);self.assertIsNone(row['change']);self.assertIsNone(row['event_adjustment'])
   if row['reference_score'] is None:self.assertEqual(row['formula_mode'],'incomplete');continue
   self.assertAlmostEqual(sum(r['weight'] for r in row['contributions']),1,places=10)
   self.assertAlmostEqual(sum(r['contribution'] for r in row['contributions']),row['reference_score'],places=3)
   if row['formula_mode']=='wgi_only':self.assertIsNone(row['bready']);self.assertIsNone(row['bready_mean'])
 def test_official_workbook_selected_cells_and_topics(self):
  vn=c.baseline('越南');idn=c.baseline('ID')
  self.assertEqual(vn['wgi']['ge']['value'],55.951043299999995)
  self.assertAlmostEqual(vn['bready']['topics'][0]['value'],76.6213348765432)
  self.assertEqual(len(idn['bready']['topics']),10)
  self.assertTrue(vn['wgi']['ge']['locator'].startswith('ge!M'))
 def test_different_coverage_never_ranked(self):
  comp=c.compare(['Vietnam','UAE']);self.assertFalse(comp['same_basis']);self.assertIsNone(comp['ranking'])
  self.assertTrue(c.compare(['VN','ID'])['same_basis'])
  self.assertTrue(all(p['higher_point_estimate']==['ARE'] for p in c.compare(['VN','AE'])['common_wgi']))
  with self.assertRaises(ValueError):c.compare(['VN','Vietnam'])
  with self.assertRaises(ValueError):c.compare(['unknown'])
 def test_lookup_and_dashboard_do_not_mutate_snapshot(self):
  a=c.baseline('VN');a['wgi']['ge']['value']=0;self.assertNotEqual(c.baseline('Vietnam')['wgi']['ge']['value'],0)
 def test_baseline_scope_time_citations_and_private_context(self):
  with tempfile.TemporaryDirectory() as temp:
   store=core.Store(temp);mission=dict(product.SPEC['starter'],context='PRIVATE-DO-NOT-EXPORT',countries=['越南','印尼'])
   agent=core.Agent(store,product.SPEC);rid=store.create_run(product.SPEC['id'],mission,'model');run=store.get_run(rid)
   result=agent.execute('country_baseline',{'countries':['VNM','IDN']},run,30)
   self.assertEqual(len(result['evidence_ids']),2)
   self.assertNotIn('PRIVATE-DO-NOT-EXPORT',json.dumps(store.export_evidence()))
   for eid in result['evidence_ids']:self.assertEqual(agent.execute('read_evidence',{'id':eid},run,30)['retrieval_kind'],'country_baseline')
   with self.assertRaisesRegex(ValueError,'scope'):agent.execute('country_baseline',{'countries':['USA']},run,30)
   old=dict(mission,as_of='2024-12-31T23:59:59Z')
   with self.assertRaisesRegex(ValueError,'historical'):c.evidence(store,['VN'],old)
   report=product.demo_report(mission,[],[]);report['evidence_ids']=result['evidence_ids']
   with self.assertRaisesRegex(ValueError,'read'):agent.execute('finish',{'report':report},run,30)
 def test_dashboard_truthful_event_freshness_and_empty_state(self):
  with tempfile.TemporaryDirectory() as temp:
   store=core.Store(temp);self.assertEqual(c.dashboard(store,'VN')['evidence'],[])
   rows=[{'title':'Old public event','body':'Old claim','url':'https://example.org/old','countries':['Vietnam'],'topics':['trade'],'published_at':'2024-01-01','status':'source_claim'}, {'title':'Fictional','body':'Demo','url':'https://example.org/demo','countries':['Vietnam'],'topics':['trade'],'status':'synthetic'}]
   store.import_evidence({'schema':'field-evidence/v1','records':rows});d=c.dashboard(store,'VN');self.assertEqual(len(d['evidence']),1);self.assertEqual(d['evidence'][0]['freshness'],'older');self.assertIsNone(d['event_adjustment'])
 def test_roadmap_dependencies_and_read_citations(self):
  stage={'id':'one','goal':'Pilot','actions':['Interview'],'deliverables':['Memo'],'depends_on':[],'completion_signal':'Three interviews','evidence_ids':['abc']}
  research.validate_extensions({'roadmap':[stage],'watchpoints':[{'condition':'Rule changes','exposure':'Importer','next_check':'Official notice','evidence_ids':['abc']}]},{'abc'})
  for bad in [dict(stage,depends_on=['one']),dict(stage,evidence_ids=['unread']),dict(stage,actions=[])]:
   with self.assertRaises(ValueError):research.validate_extensions({'roadmap':[bad]},{'abc'})
 def test_research_framework_not_factual_evidence(self):
  p=research.plan('market-entry-agent',{'question':'Q','countries':['VN'],'topics':['trade']});self.assertEqual([l['id'] for l in p['lenses']],['macro','industry','competition','entry']);self.assertTrue(p['input_fingerprint'])
 def test_requested_structured_output_is_saved_not_only_prose(self):
  with tempfile.TemporaryDirectory() as temp:
   store=core.Store(temp);mission=dict(product.SPEC['starter'],output_sections=['watchpoints'])
   agent=core.Agent(store,product.SPEC);rid=store.create_run(product.SPEC['id'],mission,'model')
   ids=agent.execute('country_baseline',{'countries':['Vietnam']},store.get_run(rid),30)['evidence_ids']
   row=agent.execute('read_evidence',{'id':ids[0]},store.get_run(rid),30)
   store.checkpoint(rid,0,'read_evidence',row,[])
   report=product.demo_report(mission,[],[]);report['evidence_ids']=ids
   with self.assertRaisesRegex(ValueError,'structured watchpoints'):agent.execute('finish',{'report':report},store.get_run(rid),30)
   report['watchpoints']=[{'condition':'Review on new release','exposure':'Country research assumptions','next_check':'Official source version','evidence_ids':ids}]
   final=agent.execute('finish',{'report':report},store.get_run(rid),30)['report'];store.finish(rid,final)
   self.assertEqual(store.get_run(rid)['report']['watchpoints'],report['watchpoints'])
   self.assertIn('观察条件',core.markdown(store.get_run(rid)['report']))
 def test_output_section_names_are_bounded(self):
  with self.assertRaisesRegex(ValueError,'output_sections'):core.validate_mission(dict(product.SPEC['starter'],output_sections=['arbitrary']))
 def test_optional_local_instructions_are_explicit_and_private(self):
  with tempfile.TemporaryDirectory() as temp:
   store=core.Store(temp);agent=core.Agent(store,product.SPEC);p=Path(temp)/'instructions.txt';p.write_text('USER-OWNED-INSTRUCTIONS')
   with patch.dict(os.environ,{'AGENT_INSTRUCTIONS_FILE':str(p)}):self.assertIn('USER-OWNED-INSTRUCTIONS',agent.system(product.SPEC['starter']))
   self.assertNotIn('USER-OWNED-INSTRUCTIONS',json.dumps(store.export_evidence()))
   p.write_text('x'*24001)
   with patch.dict(os.environ,{'AGENT_INSTRUCTIONS_FILE':str(p)}):
    with self.assertRaisesRegex(ValueError,'size limit'):agent.system(product.SPEC['starter'])
 def test_missing_local_instructions_fail_without_publishing_path(self):
  with tempfile.TemporaryDirectory() as temp:
   store=core.Store(temp);agent=core.Agent(store,product.SPEC)
   with patch.dict(os.environ,{'AGENT_INSTRUCTIONS_FILE':str(Path(temp)/'missing.txt')}):run=agent.run(product.SPEC['starter'],'model')
   self.assertEqual(run['state'],'failed');self.assertEqual(run['error'],'FileNotFoundError')
if __name__=='__main__':unittest.main()
