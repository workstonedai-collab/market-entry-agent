"""Durable research, public-query isolation and document provenance behavior."""
import copy
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core')
SPEC=importlib.import_module(MODULE+'.product').SPEC
notes=importlib.import_module(MODULE+'.notebook')
adaptive=importlib.import_module(MODULE+'.adaptive')
documents=importlib.import_module(MODULE+'.documents')
net=importlib.import_module(MODULE+'.net')
ROOT=Path(__file__).resolve().parents[1]


def report(eid):
    return {'title':'Synthetic research','summary':'Synthetic test','assessment':'A reasoned conditional proposal.','findings':[{'claim':'Test quotation','evidence_ids':[eid]}],'actions':['Obtain a quote'],'uncertainties':['Cost unknown'],'follow_up':['Check changed conditions'],'evidence_ids':[eid],'priority':'watch'}


class ResearchStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=core.Store(self.root/'workspace');self.agent=core.Agent(self.store,SPEC)
        self.mission={'question':'Synthetic trade decision','context':'PRIVATE CUSTOMER AND INTERNAL QUOTE','countries':['Vietnam'],'topics':['trade'],'max_steps':12,'deadline_seconds':30}
        self.store.import_evidence({'schema':'field-evidence/v1','records':[{'title':'Synthetic source','url':'https://example.org/source','body':'First statement. Second statement.','countries':['Vietnam'],'topics':['trade'],'published_at':'2024-01-01','status':'synthetic'}]})
        self.eid=self.store.export_evidence()['records'][0]['id']
        self.rid=self.store.create_run(SPEC['id'],self.mission,'model');self.run=self.store.get_run(self.rid)
        self.run['steps']=[{'seq':0,'action':'read_evidence','observation':dict(self.store.read(self.eid),body='Second statement.',body_offset=17)}]
    def command(self):
        return {'expected_revision':0,'questions':[{'id':'q1','text':'What changes the choice?','status':'investigating','why':'Changes delivery'}],
                'notes':[{'id':'n1','text':'Second statement.','kind':'source_fact','evidence_ids':[self.eid],'fragments':[{'evidence_id':self.eid,'offset':17,'quote':'Second statement.'}],'question_id':'q1','relation':'supports','change_reason':'New dated source'}], 'next_step':'Compare the alternative quote','stop_reason':''}
    def test_fragments_are_exact_and_inside_read_span(self):
        for offset,quote in [(0,'First statement.'),(17,'Invented statement.'),(17,'Second statement. extra')]:
            args=self.command();args['notes'][0]['fragments'][0].update(offset=offset,quote=quote)
            with self.assertRaises(ValueError):notes.update(self.store,self.run,args)
        result=notes.update(self.store,self.run,self.command());self.assertEqual(result['notes'][0]['fragments'][0]['offset'],17)
    def test_revisions_survive_reopen_and_cannot_be_overwritten_from_stale_state(self):
        notes.update(self.store,self.run,self.command())
        reopened=core.Store(self.store.workspace);self.assertEqual(notes.snapshot(reopened,self.rid)['revision'],1)
        stale=self.command();stale['next_step']='Different stale write'
        with self.assertRaisesRegex(ValueError,'conflict'):notes.update(reopened,self.run,stale)
        current=dict(stale,expected_revision=1);notes.update(reopened,self.run,current)
        with reopened.tasks() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM research_revisions').fetchone()[0],2)
    def test_update_replayed_after_interruption_is_idempotent(self):
        first=notes.update(self.store,self.run,self.command())
        second=notes.update(core.Store(self.store.workspace),self.run,self.command())
        self.assertEqual(first,second)
        with self.store.tasks() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM research_revisions').fetchone()[0],1)

    def test_notebook_scope_is_per_run_and_no_operator_approval_can_be_created(self):
        notes.update(self.store,self.run,self.command())
        other=self.store.create_run(SPEC['id'],self.mission,'model');self.assertEqual(notes.snapshot(self.store,other)['notes'],[])
        bad=self.command();bad['expected_revision']=1;bad['notes'][0]['kind']='approved_decision'
        with self.assertRaises(ValueError):notes.update(self.store,self.run,bad)
    def test_agent_receives_notebook_and_saved_report_keeps_raw_narrative(self):
        seen=[];actions=[{'action':'read_evidence','arguments':{'id':self.eid}},{'action':'update_research','arguments':self.command()},{'action':'finish','arguments':{'report':report(self.eid)}}]
        class Model:
            def next(_,messages,timeout):seen.append(messages);return actions.pop(0)
        run=core.Agent(self.store,SPEC,Model).run(self.mission,'model');self.assertEqual(run['state'],'completed',run['error'])
        saved=core.Store(self.store.workspace).get_run(run['id'])['report']
        self.assertEqual(saved['assessment'],report(self.eid)['assessment']);self.assertEqual(saved['research_state']['revision'],1)
        self.assertTrue(any('RESEARCH_WORKING_STATE' in m['content'] for m in seen[-1]));self.assertIn('Second statement.',core.markdown(saved))
    def test_adaptive_search_sends_only_composed_public_terms_and_budget_survives_reopen(self):
        mission=dict(self.mission,public_search={'terms':['Vietnam','pumps'],'facets':['import rules','service network'],'max_queries':1})
        self.run['mission']=mission
        response={'query':'Vietnam pumps import rules','results':[]}
        with patch.object(net,'search_query',return_value=response.copy()) as search:
            args={'term_ids':[0,1],'facet_id':0,'reason':'PRIVATE reasoning stays local'}
            result=adaptive.search(self.store,self.run,args,20)
            self.assertEqual(search.call_args.args[2],'Vietnam pumps import rules');self.assertEqual(result['query_budget']['used'],1)
            self.assertNotIn('PRIVATE',search.call_args.args[2])
            reopened=core.Store(self.store.workspace)
            with self.assertRaisesRegex(ValueError,'budget'):adaptive.search(reopened,self.run,dict(args,facet_id=1),20)
            self.assertEqual(search.call_count,1)
    def test_adaptive_search_cannot_use_unapproved_free_text_or_invalid_indices(self):
        self.run['mission']=dict(self.mission,public_search={'terms':['Vietnam'],'facets':['trade'],'max_queries':2})
        for args in [{'term_ids':[999],'facet_id':0,'reason':'test'},{'term_ids':[True],'facet_id':0,'reason':'test'},{'term_ids':[0],'facet_id':999,'reason':'test'}]:
            with self.assertRaises(ValueError):adaptive.search(self.store,self.run,args,20)
        with self.assertRaises(ValueError):core.REGISTRY.validate('adaptive_search',{'term_ids':[0],'facet_id':0,'reason':'test','query':'PRIVATE'})
    def test_search_snippet_cannot_be_promoted_to_fact_or_report_citation(self):
        source=dict(self.store.read(self.eid),retrieval_kind='search_snippet',status='source_claim',synthetic=False)
        source.pop('id');self.store.import_evidence({'schema':'field-evidence/v1','records':[source]})
        eid=next(r['id'] for r in self.store.export_evidence()['records'] if r.get('retrieval_kind')=='search_snippet')
        run=dict(self.run,steps=[{'seq':0,'action':'read_evidence','observation':self.store.read(eid)}])
        args=self.command();args['notes'][0]['evidence_ids']=[eid];args['notes'][0]['fragments']=[{'evidence_id':eid,'offset':0,'quote':'First statement.'}]
        with self.assertRaisesRegex(ValueError,'discovery'):notes.update(self.store,run,args)
        with self.assertRaisesRegex(ValueError,'discovery'):self.agent.execute('finish',{'report':report(eid)},run,20)

    def test_query_scope_is_opt_in_and_validated_before_run_creation(self):
        self.assertNotIn('adaptive_search',{t['name'] for t in self.agent.task_tools(self.mission)})
        m=dict(self.mission,public_search={'terms':['Vietnam'],'facets':['trade'],'max_queries':2});core.validate_mission(m)
        self.assertIn('adaptive_search',{t['name'] for t in self.agent.task_tools(m)});self.assertIn('fetch_page',{t['name'] for t in self.agent.task_tools(m)})
        for cap in [0,13,False]:
            with self.assertRaises(ValueError):core.validate_mission(dict(m,public_search=dict(m['public_search'],max_queries=cap)))
    def test_table_values_locations_and_document_identity_survive_reimport(self):
        path=self.root/'报价.csv';path.write_text('product,price,currency\npump,1250,USD\npump-B,,USD\n',encoding='utf-8')
        meta={'title':'Operator supplied fictional quote','url':'https://example.org/private-quote','countries':['Vietnam'],'topics':['trade']}
        first=documents.ingest(self.store,path,meta);second=documents.ingest(self.store,path,meta);self.assertEqual(first['evidence_ids'],second['evidence_ids'])
        row=self.store.read(first['evidence_ids'][0]);self.assertIn('price: 1250 | currency: USD',row['body']);self.assertEqual(row['document_location']['row_start'],2);self.assertEqual(row['document_location']['row_end'],3)
        self.assertNotIn(str(path),json.dumps(row));self.assertEqual(row['visibility'],'private')
    def test_private_document_cannot_enter_shared_public_database(self):
        store=core.Store(self.root/'other',self.root/'shared.sqlite3');file=self.root/'note.md';file.write_text('Private note',encoding='utf-8');meta={'title':'Private','url':'https://example.org/note','countries':['Vietnam'],'topics':['trade']}
        with self.assertRaisesRegex(ValueError,'shared'):documents.ingest(store,file,meta)
        documents.ingest(store,file,dict(meta,public=True))
    def test_invalid_table_and_file_type_are_rejected(self):
        path=self.root/'bad.csv';path.write_text('a,b\n1,2,3\n',encoding='utf-8')
        with self.assertRaises(ValueError):documents.extract(path)
        path=self.root/'secret.env';path.write_text('x',encoding='utf-8')
        with self.assertRaises(ValueError):documents.extract(path)
    def test_operator_cli_document_import_and_notebook_read_without_provider(self):
        source=self.root/'small.md';source.write_text('A synthetic source text.',encoding='utf-8');meta=self.root/'metadata.json';meta.write_text(json.dumps({'title':'Synthetic document','url':'https://example.org/md','countries':['Vietnam'],'topics':['trade']}),encoding='utf-8')
        env=dict(os.environ);env['PYTHONPATH']=str(ROOT/'src')
        cmd=[sys.executable,'-m',MODULE,'--workspace',str(self.store.workspace)]
        r=subprocess.run(cmd+['import-document',str(source),str(meta)],env=env,capture_output=True,timeout=20);self.assertEqual(r.returncode,0,r.stderr.decode());self.assertEqual(json.loads(r.stdout)['model_calls'],0)
        r=subprocess.run(cmd+['research-state',self.rid],env=env,capture_output=True,timeout=20);self.assertEqual(r.returncode,0,r.stderr.decode());self.assertEqual(json.loads(r.stdout)['revision'],0)
    @unittest.skipUnless(shutil.which('node'),'Optional Node checks shipped browser helpers')
    def test_browser_shows_escaped_fragments_and_public_query_scope(self):
        script="""const fs=require('fs'),vm=require('vm'),assert=require('assert');const html=fs.readFileSync(process.argv[1],'utf8');const values={'public-terms':{value:'Vietnam\\npumps'},'public-facets':{value:'import rules'}};const ctx=vm.createContext({assert,$:id=>values[id],esc:v=>String(v??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])),itemText:x=>String(x)});for(const name of ['list','publicSearchConfig','branchesHTML','branchesText','notebookHTML','notebookText']){const line=html.split('\\n').find(x=>x.startsWith('function '+name+'('));vm.runInContext(line,ctx)}vm.runInContext(`const scope=publicSearchConfig();assert.equal(scope.public_search.terms[1],'pumps');assert.equal(scope.public_search.max_queries,6);const n={revision:1,questions:[{text:'<script>bad</script>',status:'open'}],notes:[{kind:'source_fact',text:'<img src=x>',fragments:[{quote:'<script>quote</script>',title:'Title',offset:0,evidence_id:'e1',retrieval_kind:'attributed_public_summary'}]}],next_step:'next',stop_reason:''};const rendered=notebookHTML(n);assert.ok(!rendered.includes('<script>'));assert.ok(!rendered.includes('<img'));assert.ok(rendered.includes('公开资料摘要'));assert.ok(notebookText(n).includes('e1 @ 0'));`,ctx);"""
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'src'/MODULE/'web.html')],capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))

    def test_optional_pdf_adapter_extracts_actual_page_and_network_fetch_preserves_cache(self):
        try:from pypdf import PdfWriter
        except ImportError:self.skipTest('Optional pypdf parser installed only in document-adapter test environment')
        from pypdf.generic import DictionaryObject,NameObject,ArrayObject,NumberObject,DecodedStreamObject
        writer=PdfWriter();page=writer.add_blank_page(300,200)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 100 Td (Official synthetic PDF statement.) Tj ET');page[NameObject('/Contents')]=writer._add_object(stream)
        pdf=self.root/'synthetic.pdf';writer.write(pdf)
        with patch.dict(os.environ,{'AGENT_PDF_ADAPTER_PYTHON':sys.executable}):
            raw,chunks=documents.extract(pdf);self.assertIn('Official synthetic PDF statement.',chunks[0][0]);self.assertEqual(chunks[0][1]['page'],1)
            self.store.register_sources({'sources':[{'id':'pdf','kind':'page','title':'Synthetic PDF','url':'https://example.org/test.pdf','allowed_hosts':['example.org'],'countries':['Vietnam'],'topics':['trade'],'published_at':'2024-01-01'}]})
            with patch.object(core,'fetch_public_https',return_value=raw) as fetch:
                first=net.fetch_page(self.store,source_id='pdf');second=net.fetch_page(self.store,source_id='pdf')
            self.assertEqual(first['retrieval_kind'],'document_text');self.assertTrue(first['evidence_ids']);self.assertTrue(second['cached']);self.assertEqual(fetch.call_count,1)
            self.assertEqual(self.store.read(first['id'])['document_location']['page'],1)

if __name__=='__main__':unittest.main()
