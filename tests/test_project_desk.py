"""Project desk isolation and reopening saved research without another model call."""
import importlib
from pathlib import Path
import tempfile
import unittest

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core')
SPEC=importlib.import_module(MODULE+'.product').SPEC
overview=importlib.import_module(MODULE+'.project_desk').overview
Lifecycle=importlib.import_module(MODULE+'.lifecycle').Lifecycle
Knowledge=importlib.import_module(MODULE+'.knowledge').Knowledge


class ProjectDeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=core.Store(Path(self.tmp.name)/'项目')

    def mission(self,p):return dict(question='Synthetic project question',countries=['Vietnam'],topics=['trade'],project_id=p,max_steps=6)

    def test_recent_reports_are_scoped_to_product_and_project(self):
        run=core.Agent(self.store,SPEC).run(self.mission('alpha'),'demo')
        self.assertEqual(run['state'],'completed',run['error'])
        core.Agent(self.store,SPEC).run(self.mission('beta'),'demo')
        self.store.create_run('other-product',self.mission('alpha'),'demo')
        desk=overview(self.store,SPEC['id'],'alpha')
        self.assertEqual([x['id'] for x in desk['recent']],[run['id']])
        self.assertEqual(desk['recent'][0]['summary'],run['report']['summary'])
        self.assertFalse(desk['has_more_runs'])
        self.assertEqual(self.store.get_run(desk['recent'][0]['id'])['report'],run['report'])

    def test_collection_isolation_and_management_surface(self):
        kb=Knowledge(self.store,SPEC['id']);kb.create('alpha','Alpha');kb.create('beta','Beta')
        desk=Lifecycle(self.store,SPEC['id']).dispatch('desk','overview',{'project_id':'alpha'})
        self.assertEqual([c['name'] for c in desk['collections']],['Alpha'])
        self.assertFalse(desk['recent']);self.assertFalse(desk['monitors'])
        self.assertEqual(set(desk['memory']),{'source_fact','hypothesis','judgment','decision_proposal','operator_decision'})
        with self.assertRaises(ValueError):overview(self.store,SPEC['id'],'../other')

    def test_more_runs_are_explicit_and_old_projects_are_not_hidden_by_other_runs(self):
        first=core.Agent(self.store,SPEC).run(self.mission('alpha'),'demo')
        for _ in range(21):self.store.create_run(SPEC['id'],self.mission('beta'),'demo')
        self.assertEqual(overview(self.store,SPEC['id'],'alpha')['recent'][0]['id'],first['id'])
        desk=overview(self.store,SPEC['id'],'beta',limit=2)
        self.assertEqual(len(desk['recent']),2);self.assertTrue(desk['has_more_runs'])

    def test_mcp_overview_is_read_only_bounded_and_scoped(self):
        Adapter=importlib.import_module(MODULE+'.mcp').Adapter
        adapter=Adapter(self.store,SPEC,project='alpha')
        tool=next(x for x in adapter.tools() if x['name']=='project_overview')
        self.assertTrue(tool['annotations']['readOnlyHint'])
        result=adapter.call('project_overview',{'project_id':'alpha','limit':100})
        self.assertLessEqual(len(result['text']),100)
        with self.assertRaises(ValueError):adapter.call('project_overview',{'project_id':'beta'})
        with self.assertRaises(ValueError):adapter.call('run_create',{'client_key':'test','engine':'demo','mission':self.mission('alpha')})

if __name__=='__main__':unittest.main()
