"""Product decisions, actor boundaries and arithmetic with attributed case fixtures."""
import copy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import importlib
import json
import unittest
from test_projects import ProjectBase

MODULE='market_entry_agent'
economics=importlib.import_module(MODULE+'.economics')


def scenario(option='distributor'):
    values={'quantity':'100','unit_price':'20','unit_cost':'10','freight':'100','insurance':'20','customs_value':'1000','duty_rate':'0.05','channel_fee':'50','fixed_cost':'100','recoverable_tax':'60'}
    return {'option_id':option,'name':'Explicit fictional quotation','currency':'USD','unit':'units','values':{k:{'value':v,'basis':'assumption','note':'Fictional acceptance input, not an actual quote'} for k,v in values.items()}}


class Arithmetic(unittest.TestCase):
    def test_comparable_total_and_recoverable_tax_separate_from_contribution(self):
        result=economics.calculate(economics.normalize(scenario()))
        self.assertEqual(result['metrics']['revenue'],'2000')
        self.assertEqual(result['metrics']['operating_cost'],'1320.00')
        self.assertEqual(result['metrics']['contribution_before_other_costs'],'680.00')
        self.assertEqual(result['metrics']['cash_outlay_including_recoverable_tax'],'1380.00')
        self.assertEqual(result['metrics']['contribution_margin'],'0.34')
    def test_unknown_values_do_not_silently_become_zero(self):
        data=scenario();data['values']['freight']=None
        result=economics.calculate(economics.normalize(data))
        self.assertIsNone(result['metrics']['operating_cost']);self.assertIsNone(result['metrics']['contribution_before_other_costs'])
        self.assertEqual(result['metrics']['revenue'],'2000');self.assertIn('freight',result['missing'])
    def test_invalid_money_rate_and_provenance_rejected(self):
        for key,value in [('duty_rate','5'),('unit_price','NaN'),('quantity','0'),('freight','-1'),('insurance','Infinity')]:
            data=scenario();data['values'][key]['value']=value
            with self.assertRaises(ValueError):economics.normalize(data)
        for update in [{'basis':'verified_by_agent'},{'note':''}]:
            data=scenario();data['values']['freight'].update(update)
            with self.assertRaises(ValueError):economics.normalize(data)
    def test_decimal_arithmetic_does_not_use_binary_float_rounding(self):
        data=scenario();data['values']['unit_price']['value']='0.1';data['values']['quantity']['value']='3'
        self.assertEqual(economics.calculate(economics.normalize(data))['metrics']['revenue'],'0.3')


if MODULE=='market_entry_agent':
 class EntryPaths(ProjectBase):
    def populate(self):
        for command in self.commands():self.flow.save_command(self.project,command)
    def test_transaction_roles_do_not_turn_transit_into_origin(self):
        self.populate()
        data={'name':'Fictional transaction','option_id':'distributor','manufacturer':'Factory in China','exporter':'Chinese exporter','seller':'British reseller','importer':'German distributor','buyer':'German industrial buyer','incoterm':'Not yet agreed','responsibility_note':'Origin, transit and importer duties require separate confirmation'}
        row=self.flow.save_command(self.project,{'kind':'transaction','id':'roles','data':data})
        reopened=type(self.flow)(type(self.store)(self.store.workspace)).state(self.project)
        self.assertEqual(reopened['transaction'][0]['data']['manufacturer'],'Factory in China')
        with self.assertRaises(ValueError):self.flow.save_command(self.project,{'kind':'transaction','id':'model-roles','data':data},'agent_proposal')
        self.assertEqual(row['origin'],'operator')
    def test_revised_quote_leaves_selection_and_before_after_evidence(self):
        self.populate();data=scenario();self.flow.save_command(self.project,{'kind':'economics','id':'base','data':data})
        data['values']['freight']['value']='200'
        self.flow.save_command(self.project,{'kind':'economics','id':'base','expected_revision':1,'data':data})
        state=self.flow.state(self.project);review=next(r['data'] for r in state['reviews'] if r['data'].get('kind')=='economics_changed')
        self.assertEqual(review['before']['metrics']['contribution_before_other_costs'],'680.00')
        self.assertEqual(review['after']['metrics']['contribution_before_other_costs'],'580.00')
        self.assertEqual(review['changed_inputs'],['freight'])
        self.assertEqual(state['option'][0]['data']['status'],'candidate')
        self.assertEqual(len(self.flow.history(self.project,'economics','base')),2)
        frozen=self.flow.snapshot(self.project)
        self.assertEqual(frozen['records']['economics'][0]['data']['calculation']['metrics']['contribution_before_other_costs'],'580.00')
    def test_validation_queue_orders_blockers_before_high_impact_nonblockers(self):
        self.populate();base=copy.deepcopy(self.flow.state(self.project)['assumption'][0]['data'])
        for key,blocking,impact,effort in [('blocker',True,'medium','high'),('cheap',False,'high','low')]:
            data=dict(base,blocking=blocking,decision_impact=impact,effort=effort,next_test='Obtain product classification',if_supported='Compare quotes',if_not='Pause route')
            self.flow.save_command(self.project,{'kind':'assumption','id':key,'data':data})
        queue=self.flow.state(self.project)['validation_queue']
        self.assertEqual(queue[0]['id'],'blocker');self.assertEqual(queue[0]['if_not'],'Pause route')
    def test_new_source_identifies_affected_decision_without_replacing_it(self):
        self.populate();self.flow.save_command(self.project,{'kind':'decision','id':'chosen','data':{'title':'Fictional condition','rationale':'Need further validation','option_ids':['distributor'],'evidence_ids':[self.eid]}})
        self.store.import_evidence({'schema':'field-evidence/v1','records':[self.case['sources'][1]]});self.flow.check(self.project)
        state=self.flow.state(self.project);review=state['reviews'][0]['data']
        self.assertEqual(review['affected_decision_ids'],['chosen'])
        self.assertEqual(review['before']['assumption_status'],'unchecked');self.assertEqual(review['after']['assumption_status'],'needs_review')
        self.assertEqual(state['decision'][0]['revision'],1)
else:
 class RiskPaths(ProjectBase):
    def event(self):return self.commands()[0]
    def test_operator_alias_retains_canonical_identity_and_original_history(self):
        original=self.flow.save_command(self.project,self.event());data=original['data']
        alias={'subject':'Alternative vessel name','location':data['location'],'occurred_at':data['occurred_at'],'target_event_id':original['id'],'reason':'Operator matched the same incident and date'}
        self.flow.save_command(self.project,{'kind':'event_alias','id':'vessel-name','data':alias})
        update=self.event();update['expected_revision']=1;update['data']['subject']='Alternative vessel name'
        result=self.flow.save_command(self.project,update)
        self.assertEqual(result['id'],original['id']);self.assertEqual(result['data']['subject'],data['subject'])
        with self.assertRaises(ValueError):self.flow.save_command(self.project,{'kind':'event_alias','id':'agent-alias','data':alias},'agent_proposal')
    def test_explicit_dossier_merge_keeps_sources_history_and_no_duplicate_alert(self):
        first=self.flow.save_command(self.project,self.event());second=self.event();second['data']['subject']='Differently named incident'
        second=self.flow.save_command(self.project,second)
        merged=self.flow.save_command(self.project,{'kind':'event_merge','id':second['id'],'data':{'source_id':second['id'],'target_id':first['id'],'reason':'Confirmed same incident'}})
        self.assertEqual(merged['origin'],'operator');self.assertEqual(self.flow.check(self.project)['alerts_created'],1)
        self.assertEqual(len(self.flow.history(self.project,'event',second['id'])),1)
        with self.assertRaises(ValueError):self.flow.save_command(self.project,{'kind':'event_merge','id':first['id'],'data':{'source_id':first['id'],'target_id':second['id'],'reason':'Invalid cycle'}})
        update=self.event();update['data']['subject']='Differently named incident';update['expected_revision']=self.flow.state(self.project)['event'][0]['revision']
        with self.store.tasks() as db:target=self.flow.get(db,self.project,'event',first['id'])
        update['expected_revision']=target['revision'];self.assertEqual(self.flow.save_command(self.project,update)['id'],first['id'])
    def test_explicit_entities_filter_and_deadline_explains_attention(self):
        exposure=self.flow.state(self.project)['exposure'][0]
        data=dict(exposure['data'],entity_keys=['route-A'],object_type='route',importance='high',deadline=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat())
        self.flow.save_command(self.project,{'kind':'exposure','id':exposure['id'],'expected_revision':1,'data':data})
        event=self.event();event['data'].update(entity_keys=['route-B'],severity='high');saved=self.flow.save_command(self.project,event)
        self.assertEqual(self.flow.check(self.project)['alerts_created'],0)
        event['data']['entity_keys']=['route-A'];event['expected_revision']=1;self.flow.save_command(self.project,event)
        self.assertEqual(self.flow.check(self.project)['alerts_created'],1)
        alert=self.flow.state(self.project)['alerts'][0]['data']
        self.assertEqual(alert['priority']['band'],'urgent');self.assertEqual(alert['entity_match']['matched_keys'],['route-A'])
        self.assertTrue(any('seven days' in r for r in alert['priority']['reasons']))
    def test_changed_exposure_reassesses_without_rewriting_event(self):
        event=self.flow.save_command(self.project,self.event());self.flow.check(self.project)
        exposure=self.flow.state(self.project)['exposure'][0]
        self.flow.save_command(self.project,{'kind':'exposure','id':exposure['id'],'expected_revision':exposure['revision'],'data':dict(exposure['data'],importance='high')})
        self.assertEqual(self.flow.check(self.project)['alerts_created'],1)
        with self.store.tasks() as db:self.assertEqual(self.flow.get(db,self.project,'event',event['id'])['revision'],1)
        self.assertEqual(self.flow.check(self.project)['alerts_created'],0)

if __name__=='__main__':unittest.main()
