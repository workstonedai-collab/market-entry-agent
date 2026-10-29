"""Configuration is distinct from a provider request; secrets never appear in status."""
import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core');setup=importlib.import_module(MODULE+'.setup')
SPEC=importlib.import_module(MODULE+'.product').SPEC
health=importlib.import_module(MODULE+'.worker_health')


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=core.Store(Path(self.tmp.name)/'私有 设置')
        self.env=patch.dict(os.environ,{},clear=True);self.env.start();self.addCleanup(self.env.stop)

    def settings(self,**more):return dict(base_url='https://first.example/v1',model='example-model',api_key='unit-test-secret',remember_key=False,max_tokens=6000,reasoning_effort='low',**more)

    def test_session_key_is_not_persisted_or_exposed(self):
        result=setup.save_model(self.store,self.settings());self.assertEqual(result['credential_storage'],'current_process_only')
        self.assertNotIn('unit-test-secret',(self.store.workspace/'model-profile.json').read_text())
        self.assertEqual(core.Agent(self.store,SPEC).model_factory().key,'unit-test-secret')
        status=setup.status(self.store,SPEC['id']);self.assertTrue(status['model']['configured']);self.assertIsNone(status['model']['last_connection_test'])
        self.assertNotIn('unit-test-secret',json.dumps(status));self.assertEqual(status['model_calls'],0)

    def test_persistence_requires_explicit_choice_and_survives_new_session(self):
        settings=self.settings();settings['remember_key']=True
        setup.save_model(self.store,settings);path=self.store.workspace/'model-profile.json'
        self.assertEqual(json.loads(path.read_text())['AGENT_MODEL_API_KEY'],'unit-test-secret')
        if os.name!='nt':self.assertEqual(path.stat().st_mode&0o777,0o600)
        with setup._lock:setup._sessions.pop(str(self.store.workspace),None)
        self.assertEqual(setup.environment(self.store)['AGENT_MODEL_API_KEY'],'unit-test-secret')
        settings['remember_key']=False;settings['api_key']='';setup.save_model(self.store,settings)
        self.assertNotIn('AGENT_MODEL_API_KEY',json.loads(path.read_text()))

    def test_endpoint_change_does_not_reuse_another_endpoints_key(self):
        with patch.dict(os.environ,{'AGENT_MODEL_BASE_URL':'https://old.example/v1','AGENT_MODEL_NAME':'old','AGENT_MODEL_API_KEY':'old-provider-secret'}):
            settings=self.settings();settings['api_key']='';setup.save_model(self.store,settings)
            self.assertFalse(setup.environment(self.store).get('AGENT_MODEL_API_KEY'))
        setup.save_model(self.store,self.settings());new=self.settings();new.update(base_url='https://second.example/v1',api_key='');setup.save_model(self.store,new)
        self.assertFalse(setup.environment(self.store).get('AGENT_MODEL_API_KEY'))

    def test_invalid_settings_preserve_previous_profile(self):
        setup.save_model(self.store,self.settings());before=(self.store.workspace/'model-profile.json').read_bytes()
        bad=self.settings();bad['base_url']='https://user:password@second.example/v1'
        with self.assertRaises(ValueError):setup.save_model(self.store,bad)
        self.assertEqual((self.store.workspace/'model-profile.json').read_bytes(),before)
        bad=self.settings();bad['remember_key']='yes'
        with self.assertRaises(ValueError):setup.save_model(self.store,bad)

    def test_status_does_not_call_model_and_explicit_test_records_one_request(self):
        setup.save_model(self.store,self.settings());calls=[]
        with patch.object(core.Model,'next',side_effect=lambda *a,**kw:calls.append(1) or {'action':'diagnostic','arguments':{'ok':True}}):
            setup.status(self.store,SPEC['id']);self.assertFalse(calls)
            result=setup.connection_test(self.store,SPEC['id']);self.assertEqual(result['state'],'success');self.assertEqual(len(calls),1)
        self.assertEqual(setup.status(self.store,SPEC['id'])['model']['last_connection_test']['state'],'success')
        setup.save_model(self.store,self.settings());self.assertIsNone(setup.status(self.store,SPEC['id'])['model']['last_connection_test'])

    def test_source_choice_registers_only_selected_sources_without_fetching(self):
        pack=setup.source_pack()['sources'];self.assertEqual(len(pack),2)
        with patch.object(core,'fetch_public_https',side_effect=AssertionError('No network')):
            result=setup.register_sources(self.store,[pack[0]['id']]);self.assertFalse(result['network_called'])
        self.assertEqual([s['id'] for s in self.store.sources()],[pack[0]['id']])
        with self.assertRaises(ValueError):setup.register_sources(self.store,['unknown'])

    def test_worker_heartbeat_distinguishes_progress_stale_and_stopped(self):
        with health.WorkerSession(self.store,SPEC['id'],interval=.02) as worker:
            worker.begin();status=health.status(self.store,SPEC['id']);self.assertTrue(status['recently_active']);self.assertEqual(status['sessions'][0]['observed_state'],'working')
            future=status['sessions'][0]['heartbeat']+50;self.assertEqual(health.status(self.store,SPEC['id'],future)['sessions'][0]['observed_state'],'stale')
            worker.finish();self.assertIsNotNone(health.status(self.store,SPEC['id'])['sessions'][0]['tick_finished'])
        self.assertEqual(health.status(self.store,SPEC['id'])['sessions'][0]['observed_state'],'stopped')
        self.assertFalse(health.status(self.store,'other-product')['sessions'])

    def test_changed_source_config_is_preserved_and_bad_profile_can_be_repaired(self):
        source=dict(setup.source_pack()['sources'][0],refresh_hours=48)
        self.store.register_sources({'sources':[source]})
        with self.assertRaises(ValueError):setup.register_sources(self.store,[source['id']])
        self.assertEqual(self.store.sources()[0]['refresh_hours'],48)
        (self.store.workspace/'model-profile.json').write_text('not JSON')
        self.assertFalse(setup.status(self.store,SPEC['id'])['model']['configured'])
        setup.save_model(self.store,self.settings())
        self.assertTrue(setup.status(self.store,SPEC['id'])['model']['configured'])

if __name__=='__main__':unittest.main()
