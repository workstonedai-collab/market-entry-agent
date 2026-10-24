"""Real private-state, model-contract and HTTP paths for the three lifecycle capabilities."""
import base64
import importlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core');SPEC=importlib.import_module(MODULE+'.product').SPEC
Knowledge=importlib.import_module(MODULE+'.knowledge').Knowledge
Learning=importlib.import_module(MODULE+'.learning').Learning
Monitors=importlib.import_module(MODULE+'.monitoring').Monitors
Lifecycle=importlib.import_module(MODULE+'.lifecycle').Lifecycle


def report(ids=None,decision=None):
    ids=ids or []
    value=dict(title='Synthetic test report',summary='Synthetic source-based result.',assessment='A changed condition can affect the decision; check applicability before action.',findings=[{'claim':'The supplied source describes a change.','evidence_ids':ids}] if ids else [],actions=['Check the applicable date.'],uncertainties=['Applicability needs context.'],follow_up=['Check for implementation guidance.'],evidence_ids=ids,priority='routine')
    if decision is not None:value['monitor_decision']=decision
    return value


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=core.Store(Path(self.tmp.name)/'客户 项目');self.kb=Knowledge(self.store,SPEC['id']);self.learn=Learning(self.store,SPEC['id']);self.mon=Monitors(self.store,SPEC['id'])
        self.collection=self.kb.create('alpha','Synthetic source collection')

    def ingest(self,body='原始规则：2027 年开始适用。',name='材料.md',metadata=None,did=None):
        j=self.kb.queue('alpha',self.collection['id'],name,body.encode(),metadata or dict(title='Synthetic rule',countries=['Vietnam'],topics=['trade']),did)
        value=self.kb.process('alpha',j['id']);self.assertEqual(value['state'],'completed',value)
        return self.kb.documents('alpha',self.collection['id'])[-1]

    def mission(self,**extra):return dict(question='Analyze the synthetic rule.',countries=['Vietnam'],topics=['trade'],project_id='alpha',max_steps=12,**extra)

    def config(self,**extra):return dict(name='Synthetic watch',mission=self.mission(),kind='theme',source_ids=[],criteria='New implementation guidance that changes applicability; exclude rhetoric.',include_terms=[],exclude_terms=[],min_sources=1,check_interval=60,digest_interval=60,timezone='UTC+00:00',quiet_hours=[],engine='rules',notify_first_run=False,**extra)

    def evidence(self,body='A new operating rule.',url='https://example.org/rule',title='Synthetic rule'):
        self.store.import_evidence({'schema':'field-evidence/v1','records':[dict(title=title,body=body,url=url,countries=['Vietnam'],topics=['trade'],published_at='2026-10-20',status='source_claim',retrieval_kind='page_text')]})

    def test_private_collection_never_enters_shared_evidence(self):
        store=core.Store(Path(self.tmp.name)/'other',Path(self.tmp.name)/'shared.sqlite3');kb=Knowledge(store,SPEC['id']);c=kb.create('alpha','Private')
        job=kb.queue('alpha',c['id'],'文档.txt','PRIVATE SENTINEL'.encode(),dict(countries=['Vietnam'],topics=['trade']))
        self.assertEqual(kb.process('alpha',job['id'])['state'],'completed')
        self.assertEqual(store.export_evidence()['records'],[])
        self.assertEqual(kb.search(kb.pin('alpha',[c['id']]),'SENTINEL')[0]['visibility'],'private')
        with self.assertRaises(ValueError):kb.pin('beta',[c['id']])
        with self.assertRaises(ValueError):Knowledge(store,'another-product').pin('alpha',[c['id']])

    def test_duplicate_version_update_snapshot_and_metadata(self):
        first=self.ingest();pin=self.kb.pin('alpha',[self.collection['id']]);old=self.kb.search(pin,'规则')[0]
        same=self.ingest();self.assertEqual(first['version_id'],same['version_id'])
        self.ingest('新版规则：2028 年适用。',metadata=dict(title='New title',countries=['Vietnam'],topics=['trade']),did=first['id'])
        frozen=self.kb.read(pin,old['id']);self.assertIn('2027',frozen['body']);self.assertEqual(frozen['title'],'Synthetic rule')
        latest=self.kb.search(self.kb.pin('alpha',[self.collection['id']]),'规则')[0];self.assertIn('2028',latest['body'])
        self.assertEqual(latest['title'],'New title');self.assertEqual(self.kb.original('alpha',self.collection['id'],first['version_id']),'原始规则：2027 年开始适用。'.encode())

    def test_delete_revokes_frozen_reads_and_originals(self):
        doc=self.ingest();pin=self.kb.pin('alpha',[self.collection['id']]);eid=self.kb.search(pin)[0]['id']
        self.kb.delete('alpha',self.collection['id'],doc['id'])
        self.assertEqual(self.kb.search(pin),[])
        with self.assertRaises(ValueError):self.kb.read(pin,eid)
        with self.assertRaises(ValueError):self.kb.original('alpha',self.collection['id'],doc['version_id'])
        self.assertFalse(list((self.store.workspace/'knowledge'/'originals').iterdir()))

    def test_invalid_parse_saved_as_retryable_job(self):
        job=self.kb.queue('alpha',self.collection['id'],'bad.csv',b'a,b\n1\n',dict(countries=['Vietnam'],topics=['trade']))
        value=self.kb.process('alpha',job['id']);self.assertEqual(value['state'],'failed');self.assertIn('row width',value['error'])
        self.assertEqual(self.kb.documents('alpha',self.collection['id']),[])
        value=self.kb.process('alpha',job['id']);self.assertEqual(value['state'],'failed')

    def test_index_rebuild_and_no_fts_fallback(self):
        self.ingest();self.assertGreater(self.kb.rebuild('alpha')['indexed_chunks'],0)
        with self.store.tasks() as db:db.execute('DROP TABLE IF EXISTS kb_fts')
        # SQLite without FTS still retrieves scoped Chinese terms.
        self.assertTrue(self.kb.search(self.kb.pin('alpha',[self.collection['id']]),'原始规则'))

    def test_agent_reads_selected_collection_and_exports_locator(self):
        self.ingest();eid=self.kb.search(self.kb.pin('alpha',[self.collection['id']]))[0]['id']
        actions=iter([{'action':'search_evidence','arguments':{'query':'规则'}},{'action':'read_evidence','arguments':{'id':eid}},{'action':'finish','arguments':{'report':report([eid])}}])
        class Model:
            def next(self,*args,**kwargs):return next(actions)
        run=core.Agent(self.store,SPEC,Model).run(self.mission(knowledge_ids=[self.collection['id']]),'model')
        self.assertEqual(run['state'],'completed',run['error']);self.assertTrue(run['report']['sources'][0]['document_location'])
        self.assertIn('Document location:',core.markdown(run['report']))
        self.assertTrue(core.Store(self.store.workspace).get_run(run['id'])['report'])
        other=core.Agent(self.store,SPEC,Model);rid=self.store.create_run(SPEC['id'],self.mission(),'model')
        with self.assertRaises(ValueError):other.execute('read_evidence',{'id':eid},self.store.get_run(rid),10)

    def completed(self):return core.Agent(self.store,SPEC).run(self.mission(),'demo')

    def test_learning_default_off_then_local_auto_candidate(self):
        first=self.completed();self.assertEqual(self.learn.jobs('alpha'),[])
        self.learn.policy('alpha',{'mode':'local','auto_activate':False,'max_calls_per_day':0})
        run=self.completed();jobs=self.learn.jobs('alpha');self.assertEqual(len(jobs),1)
        result=self.learn.process(jobs[0]['id']);self.assertEqual(result['state'],'completed',result)
        skill=self.learn.versions('alpha')[0];self.assertFalse(skill['active']);self.assertEqual(skill['source_run_ids'],[run['id']])
        self.assertNotIn(run['mission']['question'],skill['instructions'])
        self.learn.activate('alpha',skill['name'],skill['version'])
        snap=importlib.import_module(MODULE+'.skills').snapshot(self.store,SPEC['id'],'alpha')
        self.assertEqual(snap[skill['name']]['version'],skill['version'])
        with self.assertRaises(ValueError):self.learn.activate('beta',skill['name'],skill['version'])

    def test_feedback_version_export_and_rollback(self):
        self.learn.policy('alpha',{'mode':'local','auto_activate':True,'max_calls_per_day':0});run=self.completed()
        j=self.learn.enqueue(run['id'],'分别写明公告日、生效日和实际适用日。','alpha');self.learn.process(j['id'])
        first=self.learn.versions('alpha')[0];self.assertTrue(first['active']);self.assertIn('实际适用日',first['instructions'])
        j=self.learn.enqueue(run['id'],'遇到相互矛盾的资料要保留分歧。','alpha');self.learn.process(j['id']);second=self.learn.versions('alpha')[0]
        self.assertIn('实际适用日',second['instructions']);self.assertIn('保留分歧',second['instructions'])
        self.assertNotEqual(first['version'],second['version']);self.learn.activate('alpha',first['name'],first['version'])
        self.assertEqual(self.learn.active('alpha')[0]['version'],first['version'])
        exported=self.learn.export('alpha',first['name'],first['version']);self.assertIn('requires_tools:',exported);self.assertNotIn(run['id'],exported)
        self.learn.activate('alpha',first['name']);self.assertEqual(self.learn.active('alpha'),[])
        self.assertEqual(self.store.get_run(run['id'])['state'],'completed')

    def test_model_learning_budget_and_no_silent_retry(self):
        self.learn.policy('alpha',{'mode':'model','auto_activate':False,'max_calls_per_day':1});run=self.completed();calls=[]
        class Model:
            def next(self,*args,**kwargs):calls.append(1);return {'action':'propose_skill','arguments':{'description':'Preserve dates','instructions':'Read the applicable rule before comparing options.','pitfalls':'A proposal is not enacted law.'}}
        j=self.learn.jobs('alpha')[0];self.assertEqual(self.learn.process(j['id'],Model)['state'],'completed')
        self.learn.process(j['id'],Model);self.assertEqual(len(calls),1)
        second=self.learn.enqueue(run['id'],'New correction','alpha');self.assertEqual(self.learn.process(second['id'],Model)['state'],'daily_budget_wait')
        self.learn.policy('alpha',{'mode':'off','auto_activate':False,'max_calls_per_day':0});self.assertEqual(self.learn.process(second['id'],Model)['state'],'disabled');self.assertEqual(len(calls),1)

    def test_unknown_skill_tools_rejected(self):
        run=self.completed();draft=self.learn._draft(run,'');draft['requires_tools']='send_email'
        with self.assertRaises(ValueError):self.learn.save('alpha',draft,[run['id']])

    def test_draft_preview_confirmation_and_scope_revision(self):
        self.evidence();m=self.mon.save('alpha',self.config());self.assertEqual(self.mon.check('alpha',m['id'],refresh=False)['state'],'not_due_or_not_confirmed')
        preview=self.mon.preview('alpha',m['id']);self.assertEqual(preview['matching_records'],1)
        self.assertEqual(self.mon.history('alpha',m['id'])['receipts'],[])
        active=self.mon.confirm('alpha',m['id'],preview['hash']);self.assertEqual(active['state'],'active')
        changed=self.mon.save('alpha',dict(m['config'],check_interval=120,digest_interval=120),m['id'],m['revision'])
        with self.assertRaises(ValueError):self.mon.confirm('alpha',m['id'],preview['hash'])
        self.assertEqual(changed['state'],'draft');self.assertEqual(self.mon.check('alpha',m['id'],refresh=False)['state'],'not_due_or_not_confirmed')

    def test_baseline_dedup_new_revision_and_quiet_no_change(self):
        self.evidence();m=self.mon.save('alpha',self.config());m=self.mon.confirm('alpha',m['id'],m['hash']);stamp=m['next_due']+1
        self.assertEqual(self.mon.check('alpha',m['id'],stamp,False)['state'],'baseline_saved')
        self.assertEqual(self.mon.check('alpha',m['id'],stamp+61,False)['state'],'no_change');self.assertEqual(self.mon.history('alpha',m['id'])['inbox'],[])
        self.evidence('A new operating rule.',url='https://example.net/repost')
        self.assertEqual(self.mon.check('alpha',m['id'],stamp+122,False)['state'],'no_change')
        self.evidence('The operating rule now applies to a new category.')
        result=self.mon.check('alpha',m['id'],stamp+183,False);self.assertEqual(len(result['items']),1)
        history=self.mon.history('alpha',m['id']);self.assertEqual(len(history['inbox']),1)
        self.assertEqual(self.mon.check('alpha',m['id'],stamp+244,False)['state'],'no_change');self.assertEqual(len(self.mon.history('alpha',m['id'])['inbox']),1)

    def test_failure_backoff_no_change_is_not_failure(self):
        m=self.mon.save('alpha',self.config());m=self.mon.confirm('alpha',m['id'],m['hash'])
        with patch.object(self.mon,'refresh_sources',side_effect=ValueError('network_unavailable')):result=self.mon.check('alpha',m['id'],m['next_due']+1)
        self.assertEqual(result['state'],'failed');h=self.mon.history('alpha',m['id']);self.assertEqual(h['receipts'][0]['error'],'network_unavailable');self.assertEqual(self.mon.get('alpha',m['id'])['failures'],1)
        self.assertEqual(h['inbox'],[])

    def test_quiet_hours_save_then_later_digest(self):
        self.evidence();m=self.mon.save('alpha',dict(self.config(),quiet_hours=[0,23],notify_first_run=True));m=self.mon.confirm('alpha',m['id'],m['hash'])
        stamp=(int(m['next_due'])//86400+1)*86400+3600
        result=self.mon.check('alpha',m['id'],stamp,False);self.assertEqual(result['state'],'changes_saved');self.assertEqual(self.mon.history('alpha',m['id'])['inbox'],[])
        self.mon.deliver('alpha',m['id'],stamp+22*3600);self.assertEqual(len(self.mon.history('alpha',m['id'])['inbox']),1)
        self.mon.deliver('alpha',m['id'],stamp+22*3600+61);self.assertEqual(len(self.mon.history('alpha',m['id'])['inbox']),1)

    def test_source_binding_change_requires_reconfirmation(self):
        source=dict(id='rule',title='Synthetic',kind='page',url='https://example.org/rule',allowed_hosts=['example.org'],countries=['Vietnam'],topics=['trade'])
        self.store.register_sources({'sources':[source]});m=self.mon.save('alpha',dict(self.config(),source_ids=['rule']));self.mon.confirm('alpha',m['id'],m['hash'])
        self.store.register_sources({'sources':[dict(source,url='https://example.org/changed')]})
        with self.assertRaises(ValueError):self.mon.confirm('alpha',m['id'],m['hash'])
        with patch.object(self.mon,'refresh_sources') as refresh:self.mon.check('alpha',m['id'],time.time()+1)
        refresh.assert_not_called()

    def test_scoped_knowledge_watch_and_no_external_call(self):
        self.ingest();c=self.config();c['mission']['knowledge_ids']=[self.collection['id']];c['notify_first_run']=True
        m=self.mon.save('alpha',c);m=self.mon.confirm('alpha',m['id'],m['hash'])
        with patch('subprocess.run',side_effect=AssertionError('no external send')):r=self.mon.check('alpha',m['id'],m['next_due']+1,False)
        self.assertEqual(r['state'],'changes_saved');self.assertTrue(r['items'][0]['evidence_ids'][0].startswith('kb-'))
        with self.assertRaises(ValueError):self.mon.history('beta',m['id'])

    def test_model_monitor_contract_and_recovered_receipt(self):
        self.evidence();eid=self.store.export_evidence()['records'][0]['id'];c=self.config();c.update(engine='model',notify_first_run=True)
        m=self.mon.save('alpha',c);m=self.mon.confirm('alpha',m['id'],m['hash']);calls=[]
        actions=iter([{'action':'read_evidence','arguments':{'id':eid}},{'action':'finish','arguments':{'report':report([eid],{'notify':True,'reason':'New applicability is material.'})}}])
        class Model:
            def next(self,messages,timeout):calls.append(messages);return next(actions)
        class Agent(core.Agent):
            def __init__(self,store,spec):super().__init__(store,spec,Model)
        result=self.mon.check('alpha',m['id'],m['next_due']+1,False,Agent)
        self.assertEqual(result['state'],'changes_saved',result);self.assertEqual(len(calls),2)
        self.assertIn('MONITOR_DECISION_CONTRACT',calls[0][0]['content'])
        self.assertTrue(self.store.get_run(result['items'][0]['run_id'])['report'])

    def test_monitor_minimum_sources_does_not_mix_unrelated_events(self):
        self.evidence('First unrelated change.',url='https://one.example/a',title='First event')
        self.evidence('Second unrelated change.',url='https://two.example/b',title='Second event')
        m=self.mon.save('alpha',dict(self.config(),min_sources=2,notify_first_run=True));m=self.mon.confirm('alpha',m['id'],m['hash'])
        r=self.mon.check('alpha',m['id'],m['next_due']+1,False)
        self.assertEqual(r['items'],[],'Two unrelated events cannot corroborate one another')

    def test_interrupted_completed_analysis_recovers_without_model_replay(self):
        self.evidence();eid=self.store.export_evidence()['records'][0]['id'];c=self.config();c.update(engine='model',notify_first_run=True)
        m=self.mon.save('alpha',c);m=self.mon.confirm('alpha',m['id'],m['hash']);calls=[]
        actions=iter([{'action':'read_evidence','arguments':{'id':eid}},{'action':'finish','arguments':{'report':report([eid],{'notify':True,'reason':'A relevant change.'})}}])
        class Model:
            def next(self,*args,**kwargs):calls.append(1);return next(actions)
        class Agent(core.Agent):
            def __init__(self,store,spec):super().__init__(store,spec,Model)
        with patch.object(self.mon,'_complete',side_effect=RuntimeError('simulated host interruption')):
            with self.assertRaises(RuntimeError):self.mon.check('alpha',m['id'],m['next_due']+1,False,Agent)
        with self.store.tasks() as db:db.execute('UPDATE monitors SET lease=0 WHERE id=?',(m['id'],))
        class NoReplay:
            def __init__(self,*args):raise AssertionError('Completed analysis must not repeat')
        r=self.mon.check('alpha',m['id'],m['next_due']+2,False,NoReplay)
        self.assertEqual(r['state'],'changes_saved',r);self.assertEqual(len(calls),2)
        self.assertEqual(len(self.mon.history('alpha',m['id'])['inbox']),1)

    def test_active_skill_updates_do_not_change_failed_run_snapshot(self):
        self.learn.policy('alpha',{'mode':'local','auto_activate':True,'max_calls_per_day':0});source=self.completed()
        first=self.learn.process(self.learn.enqueue(source['id'],'Preserve applicable dates.','alpha')['id'])
        skill=self.learn.active('alpha')[0]
        class Fail:
            def next(self,*args,**kwargs):raise RuntimeError('synthetic model interruption')
        run=core.Agent(self.store,SPEC,Fail).run(self.mission(skill_ids=[skill['name']]),'model')
        self.assertEqual(run['state'],'failed')
        self.learn.process(self.learn.enqueue(source['id'],'Compare contradictory evidence.','alpha')['id'])
        captured=[]
        class Finish:
            def next(self,messages,timeout):captured.extend(messages);return {'action':'finish','arguments':{'report':report()}}
        done=core.Agent(self.store,SPEC,Finish).run(resume=run['id'])
        self.assertEqual(done['state'],'completed',done['error'])
        self.assertEqual(done['runtime']['skill_versions'][skill['name']],skill['version'])
        self.assertTrue(any('Preserve applicable dates.' in m['content'] for m in captured))
        self.assertFalse(any('Compare contradictory evidence.' in m['content'] for m in captured))

    def test_external_delivery_receipt_unknown_and_target_binding(self):
        import sys
        from types import SimpleNamespace
        notifications=importlib.import_module(MODULE+'.notifications')
        config_file=Path(self.tmp.name)/'delivery.json'
        config_file.write_text(json.dumps({'test':{'label':'Synthetic destination','target':'feishu:synthetic-only','executable':sys.executable}}))
        self.evidence();c=dict(self.config(),delivery='hermes',delivery_profile='test',notify_first_run=True)
        calls=[]
        def sent(command,**kwargs):calls.append(command);kwargs['stdout'].write(b'{"data":{"message_id":"synthetic-receipt"}}');return SimpleNamespace(returncode=0)
        with patch.dict(os.environ,{'AGENT_MONITOR_DELIVERY_CONFIG':str(config_file)}),patch('subprocess.run',side_effect=sent):
            m=self.mon.save('alpha',c);m=self.mon.confirm('alpha',m['id'],m['hash']);self.mon.check('alpha',m['id'],m['next_due']+1,False)
            inbox=self.mon.history('alpha',m['id'])['inbox'];self.assertEqual(inbox[0]['state'],'sent');self.assertEqual(inbox[0]['payload']['external_receipt']['message_id'],'synthetic-receipt')
            notifications.send(self.store,m['config'],inbox[0]['id']);self.assertEqual(len(calls),1)
            config_file.write_text(json.dumps({'test':{'label':'Different destination','target':'feishu:changed','executable':sys.executable}}))
            with self.assertRaises(ValueError):self.mon.confirm('alpha',m['id'],m['hash'])
        config_file.write_text(json.dumps({'test':{'label':'Synthetic destination','target':'feishu:synthetic-only','executable':sys.executable}}))
        with patch.dict(os.environ,{'AGENT_MONITOR_DELIVERY_CONFIG':str(config_file)}),patch('subprocess.run',side_effect=__import__('subprocess').TimeoutExpired('hermes',60)) as send:
            self.evidence('A different rule now applies.')
            self.mon.check('alpha',m['id'],m['next_due']+62,False)
            unknown=next(x for x in self.mon.history('alpha',m['id'])['inbox'] if x['state']=='unknown')
            notifications.send(self.store,m['config'],unknown['id']);self.assertEqual(send.call_count,1)

    def test_private_external_digest_requires_explicit_setting(self):
        import sys
        p=Path(self.tmp.name)/'profiles.json';p.write_text(json.dumps({'test':{'label':'Synthetic destination','target':'feishu:synthetic','executable':sys.executable}}))
        c=dict(self.config(),delivery='hermes',delivery_profile='test');c['mission']['knowledge_ids']=[self.collection['id']]
        with patch.dict(os.environ,{'AGENT_MONITOR_DELIVERY_CONFIG':str(p)}):
            with self.assertRaises(ValueError):self.mon.save('alpha',c)
            self.assertEqual(self.mon.save('alpha',dict(c,allow_private_delivery=True))['state'],'draft')

    def test_confirmed_watch_bypasses_stale_page_cache(self):
        net=importlib.import_module(MODULE+'.net')
        source=dict(id='rule',kind='page',url='https://example.org/rule',allowed_hosts=['example.org'],countries=['Vietnam'],topics=['trade'],title='Synthetic')
        self.store.register_sources({'sources':[source]});calls=[]
        def fetch(*args,**kwargs):calls.append(1);return ('<html><p>Synthetic change '+str(len(calls))+' with sufficient source text for extraction. '*12+'</p></html>').encode()
        with patch.object(core,'fetch_public_https',side_effect=fetch):
            net.fetch_page(self.store,source_id='rule');net.fetch_page(self.store,source_id='rule');self.assertEqual(len(calls),1)
            net.fetch_page(self.store,source_id='rule',fresh=True);self.assertEqual(len(calls),2)

    def test_worker_receipts_do_not_log_private_content(self):
        lifecycle=importlib.import_module(MODULE+'.lifecycle')
        self.learn.policy('alpha',{'mode':'local','auto_activate':False,'max_calls_per_day':0});run=self.completed()
        self.learn.enqueue(run['id'],'PRIVATE_CORRECTION_SENTINEL','alpha')
        self.evidence('PRIVATE_SOURCE_SENTINEL')
        m=self.mon.save('alpha',dict(self.config(),notify_first_run=True));self.mon.confirm('alpha',m['id'],m['hash'])
        result=lifecycle.worker_tick(self.store,SPEC['id']);raw=json.dumps(result)
        self.assertNotIn('PRIVATE_CORRECTION_SENTINEL',raw);self.assertNotIn('PRIVATE_SOURCE_SENTINEL',raw)
        self.assertTrue(result['learning']);self.assertTrue(result['monitors'])

    def test_missing_delivery_configuration_is_explained(self):
        notifications=importlib.import_module(MODULE+'.notifications')
        with patch.dict(os.environ,{'AGENT_MONITOR_DELIVERY_CONFIG':str(Path(self.tmp.name)/'not-present.json')}):
            with self.assertRaisesRegex(ValueError,'unavailable or invalid'):notifications.profile('test')

    def test_http_upload_scope_and_post_only_management(self):
        from urllib.request import Request,build_opener,ProxyHandler
        from urllib.error import HTTPError
        app=importlib.import_module(MODULE+'.app');ready=threading.Event();servers=[];original=app.AgentHTTPServer;http=build_opener(ProxyHandler({}))
        def server(*args,**kwargs):
            value=original(*args,**kwargs);servers.append(value);ready.set();return value
        token='synthetic-workspace-token-1234567890'
        with patch.object(app,'AgentHTTPServer',side_effect=server),patch.dict(os.environ,{'AGENT_UI_TOKEN':token}),patch('sys.stdout',io.StringIO()):
            t=threading.Thread(target=app.serve,args=(self.store,'127.0.0.1',0),daemon=True);t.start()
            try:
                self.assertTrue(ready.wait(5));base='http://127.0.0.1:'+str(servers[0].server_port)
                def post(path,body):
                    request=Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
                    with http.open(request,timeout=10) as response:return json.load(response)
                data=post('/api/knowledge/import',dict(project_id='alpha',collection_id=self.collection['id'],filename='用户.txt',content_base64=base64.b64encode('知识库自动化'.encode()).decode(),metadata=dict(countries=['Vietnam'],topics=['trade'])))
                deadline=time.monotonic()+10
                while self.kb.job('alpha',data['id'])['state'] in ('queued','processing') and time.monotonic()<deadline:time.sleep(.02)
                self.assertEqual(self.kb.job('alpha',data['id'])['state'],'completed')
                self.assertEqual(len(post('/api/knowledge/search',dict(project_id='alpha',collection_ids=[self.collection['id']],query='自动化'))['results']),1)
                with self.assertRaises(HTTPError):post('/api/knowledge/search',dict(project_id='beta',collection_ids=[self.collection['id']],query='自动化'))
                request=Request(base+'/api/learning/policy?project_id=alpha',headers={'Authorization':'Bearer '+token})
                with self.assertRaises(HTTPError):http.open(request,timeout=5)
                request=Request(base+'/api/skills?project_id=alpha',headers={'Authorization':'Bearer '+token})
                with http.open(request,timeout=5) as response:self.assertIn('skills',json.load(response))
                with http.open(base,timeout=5) as response:page=response.read().decode()
                self.assertIn('monitor-confirm',page);self.assertIn('knowledge-choice',page);self.assertIn('learning-desk',page)
            finally:
                if servers:servers[0].shutdown();servers[0].server_close()
                t.join(5)


if __name__=='__main__':unittest.main()
