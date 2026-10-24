"""Typed memory and evidence selection, including real persisted run boundaries."""
import copy
import importlib
import json
import shutil
import tempfile
from pathlib import Path
import subprocess
import sys
import unittest

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core');SPEC=importlib.import_module(MODULE+'.product').SPEC
continuity=importlib.import_module(MODULE+'.continuity');notebook=importlib.import_module(MODULE+'.notebook')


def report(eid):
    return {'title':'Synthetic route decision','summary':'Direct export remains a proposal','assessment':'Quote before choosing the route.',
      'findings':[{'claim':'A dated source','evidence_ids':[eid]}],'actions':['Obtain a quotation'],
      'uncertainties':['Quote unknown'],'follow_up':['Check the tariff classification'],'evidence_ids':[eid],'priority':'watch'}


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.store=core.Store(self.root/'workspace');self.memory=continuity.ResearchMemory(self.store,SPEC['id'])
        self.mission={'question':'Vietnam route cost and tariff','countries':['Vietnam'],'topics':['trade'],'project_id':'synthetic','max_steps':10,'deadline_seconds':30}
        self.store.import_evidence({'schema':'field-evidence/v1','records':[{'title':'Synthetic source','body':'Actual source text.',
          'url':'https://example.org/source','countries':['Vietnam'],'topics':['trade'],'published_at':'2024-01-01','status':'synthetic'}]})
        self.eid=self.store.export_evidence()['records'][0]['id']
    def save(self,key='route',revision=0,**kwargs):
        data={'kind':'hypothesis','text':'Vietnam route cost may increase','change_reason':'Initial synthetic premise',**kwargs}
        return self.memory.save('synthetic',key,data,revision)
    def test_operator_decisions_are_explicit_and_corrections_have_reasons(self):
        first=self.save();second=self.save(revision=1,kind='operator_decision',text='Request quotes before selecting a route',change_reason='Decision after discussion')
        self.assertEqual(second['origin'],'operator');self.assertEqual(second['revision'],2)
        self.assertEqual(len(self.memory.history('synthetic','route')),2)
        with self.assertRaisesRegex(ValueError,'conflict'):self.save(revision=1)
        with self.assertRaises(ValueError):self.save(key='bad',change_reason='')
        with self.assertRaises(ValueError):self.save(key='bad',kind='source_fact')
        self.assertEqual(self.memory.list('synthetic')[0]['text'],second['text'])
    def test_historical_recall_does_not_include_future_corrections(self):
        first=self.save();self.save(revision=1,text='Later correction')
        old=self.memory.list('synthetic',first['recorded_at'])
        self.assertEqual(old[0]['revision'],1)
        self.assertEqual(self.memory.list('synthetic','2000-01-01T00:00:00Z'),[])
    def test_scope_isolated_by_project_product_and_workspace(self):
        self.save(countries=['Vietnam'],topics=['trade'])
        self.assertEqual(self.memory.recall(self.mission)[0]['kind'],'hypothesis')
        for update in [{'project_id':'other'},{'countries':['Brazil']},{'topics':['security']}]:self.assertEqual(self.memory.recall(dict(self.mission,**update)),[])
        self.assertEqual(continuity.ResearchMemory(self.store,'other').list('synthetic'),[])
        self.assertEqual(continuity.ResearchMemory(core.Store(self.root/'separate'),SPEC['id']).list('synthetic'),[])
    def test_question_selects_old_relevant_records_and_both_sides(self):
        self.save(key='older',text='Vietnam route cost increases',relation='supports')
        self.save(key='counter',text='Vietnam route cost falls under another quote',relation='opposes')
        for i in range(12):self.save(key='noise'+str(i),text='Unrelated equipment color')
        selected=self.memory.recall(self.mission)
        self.assertEqual({r['key'] for r in selected[:2]},{'older','counter'})
        self.assertLessEqual(len(selected),8)
        self.assertTrue(all('not a source read' in r['citation_notice'] for r in selected))
    def test_finished_research_is_typed_and_not_automatically_approved(self):
        args={'expected_revision':0,'questions':[{'id':'q','text':'What route is cheaper?'}],
          'notes':[{'id':'fact','kind':'source_fact','text':'Actual source text.','evidence_ids':[self.eid],
            'fragments':[{'evidence_id':self.eid,'quote':'Actual source text.','offset':0}],'question_id':'q'},
            {'id':'hyp','kind':'hypothesis','text':'Route cost may change','relation':'opposes','question_id':'q'}]}
        actions=[{'action':'read_evidence','arguments':{'id':self.eid}}, {'action':'update_research','arguments':args},
                 {'action':'finish','arguments':{'report':report(self.eid)}}]
        class Model:
            def next(self,messages,timeout):return actions.pop(0)
        run=core.Agent(self.store,SPEC,Model).run(self.mission,'model')
        self.assertEqual(run['state'],'completed',run['error']);self.assertEqual(len(run['report']['memory_result']['captured_keys']),2)
        recalled=continuity.ResearchMemory(core.Store(self.store.workspace),SPEC['id']).recall(self.mission)
        self.assertEqual({r['kind'] for r in recalled},{'source_fact','hypothesis'})
        fact=next(r for r in recalled if r['kind']=='source_fact')
        self.assertEqual(fact['fragments'][0]['quote'],'Actual source text.')
        self.assertEqual(fact['run_id'],run['id']);self.assertEqual(fact['origin'],'agent_proposal')
        # A completed report cannot recreate a deliberately forgotten record when finish recovers/replays.
        key=fact['key'];self.memory.forget('synthetic',key)
        with self.store.tasks() as db:self.memory.capture(db,run,run['report']['research_state'])
        self.assertNotIn(key,[r['key'] for r in self.memory.list('synthetic')])
        self.assertIn('research_state',self.store.get_run(run['id'])['report'])
    def test_forget_scrubs_all_revisions_and_respects_frozen_contexts(self):
        self.save();self.save(revision=1,text='Corrected route premise')
        self.assertEqual(self.memory.forget('synthetic','route')['removed_revisions'],2)
        self.assertEqual(self.memory.history('synthetic','route'),[])
        self.assertEqual(self.memory.recall(self.mission),[])
        with self.assertRaisesRegex(ValueError,'Forgotten'):self.save()
    def test_frozen_context_survives_correction_between_attempts(self):
        self.save(text='OLD SYNTHETIC MEMORY')
        class Broken:
            def next(self,messages,timeout):raise RuntimeError('test_interruption')
        run=core.Agent(self.store,SPEC,Broken).run(self.mission,'model');self.save(revision=1,text='NEW CORRECTION')
        seen=[];eid=self.eid
        class Finisher:
            def next(self,messages,timeout):
                seen.extend(messages);return {'action':'finish','arguments':{'report':dict(report(eid),evidence_ids=[],findings=[],priority='routine')}}
        done=core.Agent(self.store,SPEC,Finisher).run(resume=run['id'])
        self.assertEqual(done['state'],'completed');context=json.dumps(seen)
        self.assertIn('OLD SYNTHETIC MEMORY',context);self.assertNotIn('NEW CORRECTION',context)
    def test_relevant_context_keeps_constraints_and_bounded_selection(self):
        from_context=importlib.import_module(MODULE+'.context')
        facts=[{'key':'noise'+str(i),'value':'Noise'} for i in range(30)]+[{'key':'budget','value':'Private cap 123'}]
        m={'facts':facts,'previous':[]};focused=continuity.focus(m,'route cost')
        self.assertEqual(focused['facts'][0]['key'],'budget');self.assertEqual(focused['omitted_facts'],19)
        self.assertEqual(len(m['facts']),31)
    def test_cli_save_history_forget_and_old_facts_continue_to_work(self):
        command=self.root/'note.json';command.write_text(json.dumps({'key':'premise','expected_revision':0,'data':{'kind':'judgment','text':'Synthetic route','change_reason':'Test'}}))
        def cli(*args):return json.loads(subprocess.check_output([sys.executable,'-m',MODULE,'--workspace',str(self.store.workspace),*args],text=True))
        self.assertEqual(cli('memory-note-save','synthetic',str(command))['revision'],1)
        self.assertEqual(cli('memory-notes','synthetic')['notes'][0]['kind'],'judgment')
        self.assertEqual(len(cli('memory-note-history','synthetic','premise')['history']),1)
        cli('memory-set','synthetic','budget','123')
        self.assertEqual(cli('memory','synthetic')['facts'][0]['value'],'123')
        cli('memory-note-forget','synthetic','premise')
        self.assertEqual(cli('memory-notes','synthetic')['notes'],[])
    @unittest.skipUnless(shutil.which('node'),'Optional browser script check requires Node')
    def test_shipped_memory_browser_renders_types_and_escapes_source_text(self):
        script=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[1],'utf8');const code=html.slice(html.indexOf('async function loadTyped()'),html.indexOf('async function loadMemory()'));
const elements=new Map(),el=id=>{if(!elements.has(id))elements.set(id,{value:'synthetic',innerHTML:'',textContent:''});return elements.get(id)};
let calls=[];const context=vm.createContext({$:el,document:{querySelectorAll:()=>[]},error:e=>{throw e},esc:v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),api:async(path,body)=>{calls.push({path,body});return {notes:[{key:'safe',revision:2,kind:'hypothesis',text:'<img src=x onerror=alert(1)>',change_reason:'quote unknown'}]}}});
vm.runInContext(code,context);vm.runInContext('loadTyped()',context).then(()=>{assert.ok(el('typed-list').innerHTML.includes('&lt;img'));assert.ok(!el('typed-list').innerHTML.includes('<img'));assert.ok(el('typed-list').innerHTML.includes('safe'));assert.ok(el('typed-list').innerHTML.includes('quote unknown'));assert.equal(calls.length,1)}).catch(e=>{console.error(e);process.exitCode=1});
"""
        path=Path(__file__).resolve().parents[1]/'src'/MODULE/'web.html'
        result=subprocess.run([shutil.which('node'),'-e',script,str(path)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_repeated_read_does_not_break_fragment_validation(self):
        rid=self.store.create_run(SPEC['id'],self.mission,'model');run=self.store.get_run(rid)
        run['steps']=[{'action':'read_evidence','observation':dict(self.store.read(self.eid),body='short',body_offset=0)},
                      {'action':'read_evidence','observation':{'id':self.eid,'reused_step':0}}]
        with self.assertRaises(ValueError):notebook.fragments(self.store,run,[{'evidence_id':self.eid,'offset':8,'quote':'source'}])

if __name__=='__main__':unittest.main()
