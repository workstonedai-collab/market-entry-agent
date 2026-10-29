"""Operator feedback, scope checks and observed skill use without auto-promotion."""
import importlib
from pathlib import Path
import tempfile
import unittest

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core');SPEC=importlib.import_module(MODULE+'.product').SPEC
Feedback=importlib.import_module(MODULE+'.feedback').Feedback
Learning=importlib.import_module(MODULE+'.learning').Learning
Monitors=importlib.import_module(MODULE+'.monitoring').Monitors


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=core.Store(Path(self.tmp.name)/'feedback');self.service=Feedback(self.store,SPEC['id'])

    def mission(self,**more):return dict(question='Synthetic feedback case.',countries=['Vietnam'],topics=['trade'],project_id='alpha',max_steps=8,**more)
    def run_report(self,**more):
        run=core.Agent(self.store,SPEC).run(self.mission(**more),'demo');self.assertEqual(run['state'],'completed',run['error']);return run

    def test_report_vote_is_scoped_and_does_not_rewrite_report(self):
        run=self.run_report();before=self.store.get_run(run['id'])['report']
        result=self.service.save('alpha','report',run['id'],'adopted','Useful next checks.')
        self.assertFalse(result['settings_changed']);self.assertEqual(self.service.list('alpha')[0]['rating'],'adopted')
        self.assertEqual(self.store.get_run(run['id'])['report'],before)
        with self.assertRaises(ValueError):self.service.save('beta','report',run['id'],'useful')
        with self.assertRaises(ValueError):Feedback(self.store,'other-product').save('alpha','report',run['id'],'useful')
        queued=self.store.create_run(SPEC['id'],self.mission(),'model')
        with self.assertRaises(ValueError):self.service.save('alpha','report',queued,'useful')

    def watch(self):
        mon=Monitors(self.store,SPEC['id'])
        config=dict(name='Synthetic watch',mission=self.mission(),kind='theme',source_ids=[],criteria='New source material.',include_terms=[],exclude_terms=[],min_sources=1,check_interval=60,digest_interval=60,timezone='UTC+00:00',quiet_hours=[],engine='rules',notify_first_run=True)
        row=mon.save('alpha',config);row=mon.confirm('alpha',row['id'],row['hash'])
        self.store.import_evidence({'schema':'field-evidence/v1','records':[dict(title='Synthetic source',body='A new rule.',url='https://example.org/rule',countries=['Vietnam'],topics=['trade'])]})
        mon.check('alpha',row['id'],row['next_due']+1,False);mon.deliver('alpha',row['id'],row['next_due']+1)
        return mon,row,mon.history('alpha',row['id'])['inbox'][0]['id']

    def test_monitor_feedback_suggests_but_never_changes_confirmed_settings(self):
        mon,row,did=self.watch();before=mon.get('alpha',row['id'])
        vote=self.service.save('alpha','monitor',did,'duplicate',context=row['id'])
        again=self.service.save('alpha','monitor',did,'duplicate',context=row['id']);self.assertEqual(vote['id'],again['id'])
        advice=self.service.suggestions('alpha',row['id']);self.assertEqual(advice['counts']['duplicate'],1);self.assertTrue(advice['suggestions']);self.assertTrue(advice['requires_confirmation'])
        after=mon.get('alpha',row['id']);self.assertEqual(before['config'],after['config']);self.assertEqual(before['confirmed'],after['confirmed'])
        self.service.save('alpha','monitor',did,'irrelevant',context=row['id']);self.service.save('alpha','monitor',did,'useful',context=row['id'])
        self.assertEqual(self.service.suggestions('alpha',row['id'])['counts']['useful'],1)
        self.assertEqual(self.service.suggestions('alpha',row['id'])['counts']['duplicate'],0)
        with self.assertRaises(ValueError):self.service.save('alpha','monitor','unknown','useful',context=row['id'])
        with self.assertRaises(ValueError):self.service.suggestions('beta',row['id'])

    def test_invalid_notes_and_ratings_are_rejected(self):
        run=self.run_report()
        with self.assertRaises(ValueError):self.service.save('alpha','report',run['id'],'five-stars')
        with self.assertRaises(ValueError):self.service.save('alpha','report',run['id'],'useful','x'*2001)

    def test_skill_catalog_presence_is_not_counted_as_loaded_context(self):
        learn=Learning(self.store,SPEC['id']);learn.policy('alpha',dict(mode='local',auto_activate=False,max_calls_per_day=0))
        source=self.run_report();job=learn.jobs('alpha')[0];learn.process(job['id']);skill=learn.versions('alpha')[0];learn.activate('alpha',skill['name'],skill['version'])
        self.run_report()
        metrics=self.service.skill_usage('alpha')['versions'][0];self.assertEqual(metrics['loaded_contexts'],0)
        used=self.run_report(skill_ids=[skill['name']]);self.service.save('alpha','report',used['id'],'needs_correction','Separate source and interpretation.')
        metrics=self.service.skill_usage('alpha')['versions'][0];self.assertEqual(metrics['loaded_contexts'],1);self.assertEqual(metrics['completed_reports'],1);self.assertEqual(metrics['related_feedback']['needs_correction'],1)
        self.assertIn(used['id'],metrics['run_ids']);self.assertEqual(learn.active('alpha')[0]['version'],skill['version'])
        self.assertFalse(self.service.skill_usage('beta')['versions'])

if __name__=='__main__':unittest.main()
