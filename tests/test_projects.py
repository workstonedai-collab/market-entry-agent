"""Business behavior, source scope, saved results and operator/agent boundaries."""
import copy
import importlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core')
SPEC=importlib.import_module(MODULE+'.product').SPEC
Workflow=importlib.import_module(MODULE+'.workflow').Workflow
ROOT=Path(__file__).resolve().parents[1]


def finished(eid, commands=None):
    report={'title':'Project regression','summary':'Test fixture','findings':[{'claim':'Fixture source statement','evidence_ids':[eid]}],
      'assessment':'Proposed analysis','actions':[],'uncertainties':['Fixture'],'follow_up':[],'priority':'watch','evidence_ids':[eid]}
    if commands is not None:report['project_update']={'commands':commands}
    return report


class ProjectBase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=core.Store(Path(self.temp.name)/'私有 business workspace');self.flow=Workflow(self.store,SPEC['id']);self.project='case'
        self.case=json.loads((ROOT/'examples/public-project-case.json').read_text(encoding='utf-8'))
        self.source=self.case['sources'][0]
        self.store.import_evidence({'schema':'field-evidence/v1','records':[self.source]})
        self.eid=self.store.export_evidence()['records'][0]['id']
        for c in self.case['operator_commands']:self.flow.save_command(self.project,c)
        self.mission={'project_id':self.project,'question':'Fixture project test','countries':self.source['countries'],'topics':self.source['topics'],'max_steps':10,'deadline_seconds':30}
    def resolve(self,value):
        if isinstance(value,str):return self.eid if value=='$source0' else value
        if isinstance(value,list):return [self.resolve(v) for v in value]
        if isinstance(value,dict):return {k:self.resolve(v) for k,v in value.items()}
        return value
    def commands(self):return self.resolve(copy.deepcopy(self.case['phases'][0]['commands']))
    def run_report(self,commands=None):
        actions=[{'action':'project_state','arguments':{}},{'action':'read_evidence','arguments':{'id':self.eid}},{'action':'finish','arguments':{'report':finished(self.eid,commands)}}]
        class Model:
            def next(self,messages,timeout):return actions.pop(0)
        return core.Agent(self.store,SPEC,Model).run(self.mission,'model')


class CommonProjects(ProjectBase):
    def test_version_history_idempotence_and_stale_revision(self):
        kind='exposure' if MODULE=='georisk_agent' else 'profile'
        old=self.flow.state(self.project)[kind][0];data=dict(old['data']);key='note' if kind=='exposure' else 'constraints';data[key]='Changed operator condition'
        result=self.flow.save_command(self.project,{'kind':kind,'id':old['id'],'expected_revision':old['revision'],'data':data})
        self.assertEqual(result['revision'],2)
        self.assertEqual(self.flow.save_command(self.project,{'kind':kind,'id':old['id'],'expected_revision':old['revision'],'data':data})['revision'],2)
        with self.assertRaisesRegex(ValueError,'revision_conflict'):self.flow.save_command(self.project,{'kind':kind,'id':old['id'],'expected_revision':1,'data':dict(data,**{key:'Later edit'})})
        self.assertEqual(len(self.flow.history(self.project,kind,old['id'])),2)
    def test_project_and_product_isolation_with_shared_evidence(self):
        self.assertTrue(any(self.flow.state(self.project)[k] for k in self.flow.kinds))
        self.assertFalse(any(self.flow.state('other')[k] for k in self.flow.kinds))
        other=Workflow(self.store,'other-product');self.assertFalse(any(other.state(self.project)[k] for k in other.kinds))
        self.assertNotIn('operator',json.dumps(self.store.export_evidence()))
    def test_cli_open_save_and_history(self):
        app=importlib.import_module(MODULE+'.app');output=io.StringIO()
        with patch('sys.stdout',output):self.assertEqual(app.main(['--workspace',str(self.store.workspace),'project',self.project]),0)
        self.assertEqual(json.loads(output.getvalue())['project_id'],self.project)
    def test_agent_finish_applies_typed_project_updates_and_reopens(self):
        run=self.run_report(self.commands());self.assertEqual(run['state'],'completed',run.get('error'))
        self.assertEqual(run['report']['project_result']['state'],'applied')
        self.assertEqual(core.Agent(self.store,SPEC).run(resume=run['id'])['report'],run['report'])
        self.assertEqual(self.store.get_run(run['id'])['steps'][0]['action'],'project_state')
    def test_unread_source_cannot_be_attached_to_project_update(self):
        commands=self.commands();commands[0]['data']['evidence_ids']=['unread-source']
        run=self.run_report(commands);self.assertNotEqual(run['state'],'completed')
        self.assertIn('not read',run['steps'][-1]['observation']['error'])
    def test_operator_only_records_cannot_be_model_updates(self):
        command=copy.deepcopy(self.case['operator_commands'][0]);run=self.run_report([command]);self.assertNotEqual(run['state'],'completed')
        self.assertIn('cannot change operator',run['steps'][-1]['observation']['error'])
    def test_report_survives_concurrent_operator_edit(self):
        initial=self.run_report(self.commands());self.assertEqual(initial['state'],'completed')
        kind='event' if MODULE=='georisk_agent' else 'option';old=self.flow.state(self.project)[kind][0]
        proposed=dict(old['data']);key='impact' if kind=='event' else 'rationale';proposed[key]='Proposed research change'
        command={'kind':kind,'id':old['id'],'expected_revision':old['revision'],'data':proposed}
        parent=self
        class Racing:
            n=0
            def next(self,messages,timeout):
                self.n+=1
                if self.n==1:return {'action':'read_evidence','arguments':{'id':parent.eid}}
                parent.flow.save_command(parent.project,{'kind':kind,'id':old['id'],'expected_revision':old['revision'],'data':dict(old['data'],**{key:'Operator wins'})})
                return {'action':'finish','arguments':{'report':finished(parent.eid,[command])}}
        run=core.Agent(self.store,SPEC,Racing).run(self.mission,'model')
        self.assertEqual(run['state'],'completed',run.get('error'));self.assertEqual(run['report']['project_result']['state'],'needs_rebase')
        self.assertEqual(next(r for r in self.flow.state(self.project)[kind] if r['id']==old['id'])['data'][key],'Operator wins')
    def test_successful_finish_checkpoint_recovers_without_repeat_effect(self):
        original=self.store.finish
        with patch.object(self.store,'finish',side_effect=RuntimeError('fixture interruption')):failed=self.run_report(self.commands())
        self.assertEqual(failed['state'],'failed')
        completed=core.Agent(self.store,SPEC).run(resume=failed['id'])
        self.assertEqual(completed['state'],'completed')
        state=self.flow.state(self.project);kind='event' if MODULE=='georisk_agent' else 'option'
        revisions=[r['revision'] for r in state[kind]]
        self.store.finish(completed['id'],completed['report'])
        self.assertEqual([r['revision'] for r in self.flow.state(self.project)[kind]],revisions)
    def test_frozen_project_record_lookup_and_current_input_precedence(self):
        run=self.run_report();meta=self.store.meta(run['id']);self.assertIn('records',meta['project_state'])
        kind='exposure' if MODULE=='georisk_agent' else 'profile';record=meta['project_state']['records'][kind][0]
        data=core.Agent(self.store,SPEC).execute('project_state',{'kind':kind,'id':record['id']},run,1)
        self.assertEqual(data['project']['record'],record)
        with self.assertRaises(ValueError):core.Agent(self.store,SPEC).execute('project_state',{'kind':kind,'id':'unknown'},run,1)
    def test_historical_mission_does_not_load_current_private_project(self):
        mission=dict(self.mission,as_of=self.source['published_at'])
        class Broken:
            def next(self,messages,timeout):raise RuntimeError('fixture stop')
        run=core.Agent(self.store,SPEC,Broken).run(mission,'model')
        self.assertNotIn('records',self.store.meta(run['id'])['project_state'])
        with self.assertRaisesRegex(ValueError,'Historical reports'):self.flow.validate_report(finished(self.eid,self.commands()),run)
    def test_scheduled_business_task_executes_once_and_saves_project(self):
        app=importlib.import_module(MODULE+'.app');commands=self.commands();eid=self.eid
        actions=[{'action':'read_evidence','arguments':{'id':eid}},{'action':'finish','arguments':{'report':finished(eid,commands)}}]
        class Model:
            def next(self,messages,timeout):return actions.pop(0)
        self.store.add_schedule(self.mission,'model',60)
        with patch.object(app,'Agent',side_effect=lambda store,spec:core.Agent(store,spec,Model)):
            first=app.tick(self.store);second=app.tick(self.store)
        self.assertEqual(len(first),1);self.assertEqual(first[0]['state'],'completed');self.assertEqual(second,[])
        self.assertEqual(self.store.get_run(first[0]['run'])['report']['project_result']['state'],'applied')

    def test_invalid_project_id_and_unknown_field_rejected(self):
        with self.assertRaises(ValueError):self.flow.state('../other')
        with self.assertRaises(ValueError):self.flow.save_command(self.project,[])
        command=copy.deepcopy(self.case['operator_commands'][0]);command['data']['unknown']='bad'
        with self.assertRaises(ValueError):self.flow.save_command(self.project,command)


if MODULE=='georisk_agent':
 class RiskProjects(ProjectBase):
    def event(self):return self.commands()[0]
    def test_normalized_identity_unifies_cross_source_dossier(self):
        first=self.flow.save_command(self.project,self.event());command=self.event();command['data']['subject']='MV RUBYMAR incident';command['expected_revision']=1
        second=self.flow.save_command(self.project,command);self.assertEqual(first['id'],second['id']);self.assertEqual(len(self.flow.state(self.project)['event']),1)
    def test_first_match_and_repeat_checks_are_silent(self):
        self.flow.save_command(self.project,self.event());self.assertEqual(self.flow.check(self.project)['alerts_created'],1)
        self.assertEqual(self.flow.check(self.project)['alerts_created'],0)
        self.assertEqual(self.flow.state(self.project)['alerts'][0]['data']['exposure_id'],'fictional-route')
    def test_summary_or_added_source_does_not_repeat_same_alert(self):
        first=self.flow.save_command(self.project,self.event());self.flow.check(self.project)
        data=dict(first['data'],summary='Reworded source summary')
        self.flow.save_command(self.project,{'kind':'event','id':first['id'],'expected_revision':1,'data':data});self.assertEqual(self.flow.check(self.project)['alerts_created'],0)
    def test_escalation_easing_and_feedback(self):
        first=self.flow.save_command(self.project,self.event());self.flow.check(self.project)
        for revision,status,severity in [(1,'escalated','high'),(2,'easing','low'),(3,'closed','low')]:
            self.flow.save_command(self.project,{'kind':'event','id':first['id'],'expected_revision':revision,'data':dict(first['data'],status=status,severity=severity)})
            self.assertEqual(self.flow.check(self.project)['alerts_created'],1)
        alert=self.flow.state(self.project)['alerts'][-1]
        feedback=self.flow.save_command(self.project,{'kind':'feedback','id':alert['id'],'data':{'alert_id':alert['id'],'state':'handled','note':'Test operator response'}})
        self.assertEqual(feedback['origin'],'operator')
    def test_evidence_country_scope_and_identity_are_protected(self):
        command=self.event();command['data']['countries']=['Vietnam']
        with self.assertRaisesRegex(ValueError,'country scope'):self.flow.save_command(self.project,command)
        first=self.flow.save_command(self.project,self.event());command=self.event();command['id']=first['id'];command['expected_revision']=1;command['data']['subject']='Other vessel'
        with self.assertRaisesRegex(ValueError,'identity is immutable'):self.flow.save_command(self.project,command)
    def test_disabled_exposure_and_severity_threshold(self):
        old=self.flow.state(self.project)['exposure'][0]
        self.flow.save_command(self.project,{'kind':'exposure','id':old['id'],'expected_revision':old['revision'],'data':dict(old['data'],active=False)})
        self.flow.save_command(self.project,self.event());self.assertEqual(self.flow.check(self.project)['alerts_created'],0)
    def test_check_reports_local_scope_and_no_source_refresh(self):
        result=self.flow.check(self.project);self.assertEqual(result['scope'],'saved_project_events_only');self.assertEqual(result['source_refresh'],'not_performed')
else:
 class EntryProjects(ProjectBase):
    def populate(self):
        for c in self.commands():self.flow.save_command(self.project,c)
    def test_options_comparable_and_profile_edit_marks_stale(self):
        self.populate();state=self.flow.state(self.project);self.assertEqual(len(state['comparison']),2)
        old=state['profile'][0];self.flow.save_command(self.project,{'kind':'profile','id':'main','expected_revision':old['revision'],'data':dict(old['data'],constraints='Changed budget and service condition')})
        self.assertTrue(all(o['profile_changed'] for o in self.flow.state(self.project)['comparison']))
    def test_new_public_source_targets_assumption_options_and_stage(self):
        self.populate();self.store.import_evidence({'schema':'field-evidence/v1','records':[self.case['sources'][1]]})
        result=self.flow.check(self.project);self.assertEqual(result['reviews_created'],1);self.assertEqual(self.flow.check(self.project)['reviews_created'],0)
        state=self.flow.state(self.project);self.assertEqual(state['assumption'][0]['data']['status'],'needs_review');self.assertEqual(state['reviews'][0]['data']['stage_ids'],['verify-importer'])
    def test_unrelated_future_and_unknown_date_sources_do_not_trigger(self):
        self.populate()
        for change in ({'countries':['Vietnam']},{'topics':['unrelated']},{'published_at':'2099-01-01'},{'published_at':None},{'published_at':'invalid-date'},{'published_at':123}):
            row=dict(self.case['sources'][1],**change);self.store.import_evidence({'schema':'field-evidence/v1','records':[row]})
        self.assertEqual(self.flow.check(self.project)['reviews_created'],0)
    def test_operator_stage_completion_requires_note(self):
        self.populate();old=self.flow.state(self.project)['stage'][0]
        with self.assertRaisesRegex(ValueError,'completion note'):self.flow.save_command(self.project,{'kind':'stage','id':old['id'],'expected_revision':old['revision'],'data':dict(old['data'],status='done',note='')})
        done=self.flow.save_command(self.project,{'kind':'stage','id':old['id'],'expected_revision':old['revision'],'data':dict(old['data'],status='done',note='Operator fixture declares completion')});self.assertEqual(done['origin'],'operator')
    def test_dependency_cycle_and_unfinished_prerequisite_rejected(self):
        self.populate();old=self.flow.state(self.project)['stage'][0]
        for deps in ([old['id']],['missing']):
            with self.assertRaises(ValueError):self.flow.save_command(self.project,{'kind':'stage','id':old['id'],'expected_revision':old['revision'],'data':dict(old['data'],depends_on=deps)})
        with self.assertRaisesRegex(ValueError,'Finish prerequisite'):self.flow.save_command(self.project,{'kind':'stage','id':'next','data':dict(old['data'],depends_on=[old['id']],status='done',note='Test')})
    def test_agent_cannot_mark_progress_or_select_option(self):
        for kind,status in [('option','selected'),('stage','done')]:
            commands=self.commands();next(c for c in commands if c['kind']==kind)['data']['status']=status
            run=self.run_report(commands);self.assertNotEqual(run['state'],'completed')
            self.assertFalse(self.flow.state(self.project)['option'])
    def test_decisions_keep_reason_and_do_not_rewrite_old_report(self):
        run=self.run_report(self.commands());before=copy.deepcopy(run['report'])
        self.flow.save_command(self.project,{'kind':'decision','id':'first','data':{'title':'Fixture decision','rationale':'Conditional choice with budget constraint','option_ids':['distributor'],'evidence_ids':[self.eid]}})
        self.assertEqual(self.store.get_run(run['id'])['report'],before)
    def test_operator_assumption_reassessment_baselines_known_sources(self):
        self.populate();self.store.import_evidence({'schema':'field-evidence/v1','records':[self.case['sources'][1]]});self.flow.check(self.project)
        old=self.flow.state(self.project)['assumption'][0]
        self.flow.save_command(self.project,{'kind':'assumption','id':old['id'],'expected_revision':old['revision'],'data':dict(old['data'],status='supported',note='Operator examined new announcement; scope still needs checking')})
        self.assertEqual(self.flow.check(self.project)['reviews_created'],0)
