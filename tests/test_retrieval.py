"""Cross-language retrieval, exact locators and saved-version compatibility."""
import importlib
import json
from pathlib import Path
import tempfile
import unittest

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core')
SPEC=importlib.import_module(MODULE+'.product').SPEC
Knowledge=importlib.import_module(MODULE+'.knowledge').Knowledge
retrieval=importlib.import_module(MODULE+'.retrieval')
Lifecycle=importlib.import_module(MODULE+'.lifecycle').Lifecycle


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=core.Store(Path(self.tmp.name)/'研究 资料')
        self.kb=Knowledge(self.store,SPEC['id']);self.c=self.kb.create('study','Research')

    def add(self,body,title='Study',published=None,did=None):
        job=self.kb.queue('study',self.c['id'],'study.md',body.encode(),dict(title=title,countries=['EU'],topics=['trade'],published_at=published),did)
        result=self.kb.process('study',job['id']);self.assertEqual(result['state'],'completed',result)
        return self.kb.documents('study',self.c['id'])[0]

    def pin(self):return self.kb.pin('study',[self.c['id']])

    def test_cross_language_aliases_without_fts(self):
        self.add('The European Union adopted a carbon border adjustment mechanism.')
        with self.store.tasks() as db:db.execute('DROP TABLE kb_fts')
        hit=self.kb.search(self.pin(),'欧盟 碳边境调节机制')[0]
        self.assertIn('European Union',hit['body']);self.assertEqual(hit['visibility'],'private')
        self.assertEqual(hit['retrieval_method'],'local-lexical-aliases')

    def test_unicode_mixed_text_and_word_boundaries(self):
        self.assertIn('cbam',retrieval.tokens('适用ＣＢＡＭ要求'))
        self.assertEqual(retrieval.alias_groups('community reunion'),[])
        self.assertTrue(retrieval.alias_groups('UN statement'))
        self.assertIn('欧盟',retrieval.expanded_tokens('European Union'))

    def test_legacy_token_rows_work_and_scope_still_applies(self):
        self.add('United Nations statement on mediation.')
        with self.store.tasks() as db:db.execute("UPDATE kb_chunks SET tokens='legacy-token'")
        self.assertTrue(self.kb.search(self.pin(),'联合国'))
        with self.assertRaises(ValueError):self.kb.search(dict(self.pin(),project='other'),'联合国')
        self.assertFalse(Knowledge(self.store,'other-product').search({'project':'study','collections':[],'versions':[]},'联合国'))

    def test_dates_are_publication_dates_and_unknown_is_explicit(self):
        doc=self.add('EU trade policy.',published='2024-01-01')
        self.assertFalse(self.kb.search(self.pin(),'EU',filters={'published_after':'2025-01-01'}))
        self.assertTrue(self.kb.search(self.pin(),'EU',filters={'published_before':'2024-01-02'}))
        self.add('EU updated trade policy.',did=doc['id'])
        self.assertFalse(self.kb.search(self.pin(),'EU',filters={'published_after':'2025-01-01'}))
        self.assertTrue(self.kb.search(self.pin(),'EU',filters={'published_after':'2025-01-01','include_undated':True}))
        with self.assertRaises(ValueError):self.kb.search(self.pin(),filters={'published_after':'2025-01-01','published_before':'2024-01-01'})

    def test_filters_via_management_and_country_topic_scope(self):
        self.add('EU trade policy.')
        lc=Lifecycle(self.store,SPEC['id']);body=dict(project_id='study',collection_ids=[self.c['id']],query='EU')
        self.assertFalse(lc.dispatch('knowledge','search',dict(body,filters={'countries':['Japan']}))['results'])
        self.assertTrue(lc.dispatch('knowledge','search',dict(body,filters={'topics':['TRADE']}))['results'])
        with self.assertRaises(ValueError):self.kb.search(self.pin(),filters={'include_undated':'true'})
        with self.assertRaises(ValueError):self.kb.search(self.pin(),filters={'private_path':'somewhere'})

    def test_structured_chunks_keep_original_offsets_and_boundary_phrase(self):
        body='# Background\n'+'background '*130+'\n\n## EU obligations\n'+('technical details '*75)+'carbon border adjustment mechanism'+'\nTail.'
        self.add(body)
        hit=self.kb.search(self.pin(),'碳边境调节机制')[0]
        full=self.kb.read(self.pin(),hit['id']);loc=full['document_location']
        self.assertEqual(full['body'],body[loc['chunk_offset']:loc['chunk_end']])
        self.assertIn('section_heading',loc)
        self.assertEqual(hit['body'],full['body'][hit['snippet_offset']:hit['snippet_offset']+400])
        self.assertIn('carbon border',hit['body'])

    def test_new_chunking_does_not_change_frozen_versions(self):
        doc=self.add('Old EU statement.');pin=self.pin();hit=self.kb.search(pin,'EU')[0]
        self.add('New EU statement.',did=doc['id'])
        self.assertIn('Old EU',self.kb.read(pin,hit['id'])['body'])
        self.assertIn('New EU',self.kb.search(self.pin(),'EU')[0]['body'])
        self.kb.delete('study',self.c['id'],doc['id'])
        self.assertFalse(self.kb.search(pin,'EU'))

    def test_matching_excerpt_is_not_always_the_document_start(self):
        body='intro '*120+'European Union rules apply.'
        self.add(body)
        hit=self.kb.search(self.pin(),'欧盟')[0]
        self.assertGreater(hit['snippet_offset'],0)
        self.assertIn('European Union',hit['body'])


    def test_saved_report_reads_cited_version_and_deletion_revokes_it(self):
        doc=self.add('Old EU statement.');eid=self.kb.search(self.pin(),'EU')[0]['id']
        value=dict(title='Synthetic report',summary='Historical source.',assessment='A source claim with conditions.',findings=[{'claim':'Old EU statement.','evidence_ids':[eid]}],actions=['Check the scope.'],uncertainties=['A source claim.'],follow_up=['Read the next source.'],evidence_ids=[eid],priority='routine')
        actions=iter([{'action':'read_evidence','arguments':{'id':eid}},{'action':'finish','arguments':{'report':value}}])
        class Model:
            def next(self,*args,**kwargs):return next(actions)
        mission=dict(question='Read selected synthetic material.',countries=['EU'],topics=['trade'],project_id='study',knowledge_ids=[self.c['id']],max_steps=5)
        run=core.Agent(self.store,SPEC,Model).run(mission,'model');self.assertEqual(run['state'],'completed',run['error'])
        self.add('New EU statement.',did=doc['id']);lc=Lifecycle(self.store,SPEC['id'])
        args=dict(project_id='study',run_id=run['id'],id=eid)
        self.assertEqual(lc.dispatch('knowledge','cited',args)['body'],'Old EU statement.')
        adapter=importlib.import_module(MODULE+'.mcp').Adapter(self.store,SPEC,project='study')
        cited=adapter.call('knowledge_citation',{'id':run['id'],'evidence_id':eid,'limit':6000})
        self.assertIn('Old EU statement.',cited['text'])
        with self.assertRaises(ValueError):importlib.import_module(MODULE+'.mcp').Adapter(self.store,SPEC,project='other').call('knowledge_citation',{'id':run['id'],'evidence_id':eid})
        with self.assertRaises(ValueError):lc.dispatch('knowledge','cited',dict(args,project_id='other'))
        with self.assertRaises(ValueError):lc.dispatch('knowledge','cited',dict(args,id='not-cited'))
        self.kb.delete('study',self.c['id'],doc['id'])
        with self.assertRaises(ValueError):lc.dispatch('knowledge','cited',args)
        with self.assertRaises(ValueError):adapter.call('knowledge_citation',{'id':run['id'],'evidence_id':eid})

if __name__=='__main__':unittest.main()
