"""Evaluation boundaries and real saved-output behavior; no paid provider in unit tests."""
import copy
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = 'market_entry_agent'
ROOT = Path(__file__).resolve().parents[1]
core = importlib.import_module(MODULE+'.core')
SPEC = importlib.import_module(MODULE+'.product').SPEC
countries = importlib.import_module(MODULE+'.countries')
spec = importlib.util.spec_from_file_location('evaluate_cases', ROOT/'scripts/evaluate_cases.py')
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


class ReportCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cases = evaluate.load_cases(ROOT/'examples/report-cases.json')

    def test_all_public_cases_run_through_runtime_scope_and_source_reading(self):
        for case in self.cases:
            store = core.Store(self.root/case['id'])
            store.import_evidence({'schema': 'field-evidence/v1', 'records': case['sources']})
            mission = case['mission']
            run_id = store.create_run(SPEC['id'], mission, 'model')
            run = store.get_run(run_id)
            agent = core.Agent(store, SPEC)
            rows = agent.execute('search_evidence', {'query': ''}, run, 30)['results']
            self.assertEqual(len(rows), len(case['sources']))
            for row in rows:
                read = agent.execute('read_evidence', {'id': row['id']}, run, 30)
                self.assertEqual(read['body'], next(s['body'] for s in case['sources'] if s['url'] == row['url']))
            names = {t['name'] for t in agent.task_tools(mission)}
            self.assertFalse(names.intersection({'web_search', 'fetch_page', 'fetch_feed', 'list_sources', 'country_baseline'}))
            with self.assertRaises(ValueError):
                countries.evidence(store, mission['countries'][:1], mission)

    def test_baseline_cutoff_and_registered_source_advertising(self):
        store = core.Store(self.root/'scope')
        mission = dict(self.cases[0]['mission'], countries=['Vietnam'], topics=['trade'])
        agent = core.Agent(store, SPEC)
        self.assertFalse(countries.available_at(mission))
        with self.assertRaisesRegex(ValueError, 'historical as_of'):
            countries.evidence(store, ['Vietnam'], mission)
        stamp = countries.dataset()['available_from']
        current = dict(mission, as_of=stamp)
        self.assertTrue(countries.available_at(current))
        self.assertIn('country_baseline', {t['name'] for t in agent.task_tools(current)})
        store.register_sources({'sources': [{'id': 'public', 'url': 'https://example.org/rss', 'allowed_hosts': ['example.org'], 'countries': ['Vietnam'], 'topics': ['trade']}]})
        self.assertIn('list_sources', {t['name'] for t in agent.task_tools(mission)})
        self.assertNotIn('list_sources', {t['name'] for t in agent.task_tools(dict(mission, countries=['Germany']))})

    def test_reject_search_enabled_undated_future_or_unbounded_cases(self):
        original = json.loads((ROOT/'examples/report-cases.json').read_text(encoding='utf-8'))
        mutations = [lambda c: c['mission'].update(search_queries=['new search']),
                     lambda c: c['mission'].update(max_model_calls=999),
                     lambda c: c['sources'][0].pop('published_at'),
                     lambda c: c['sources'][0].update(published_at='2099-01-01T00:00:00Z')]
        for mutate in mutations:
            suite = copy.deepcopy(original)
            mutate(suite['cases'][0])
            path = self.root/'invalid.json'
            path.write_text(json.dumps(suite), encoding='utf-8')
            with self.assertRaises(ValueError):
                evaluate.load_cases(path)

    def test_live_command_preserves_exact_agent_report_and_rejects_overwrite(self):
        case = self.cases[0]
        store = core.Store(self.root/'seed')
        store.import_evidence({'schema': 'field-evidence/v1', 'records': case['sources']})
        eid = store.export_evidence()['records'][0]['id']
        report = {'title': 'Direct output fixture', 'summary': 'Supplied scenario', 'findings': [{'claim': 'Attribution fixture', 'evidence_ids': [eid]}],
                  'assessment': 'A first paragraph.\n\nA second paragraph.', 'actions': ['Request a written quotation'], 'uncertainties': ['Cost unknown'], 'follow_up': ['Check the response'], 'evidence_ids': [eid], 'priority': 'watch'}
        if 'decision_options' in case['mission'].get('output_sections', []):
            report['decision_options'] = [{'name': 'Conditional route', 'fit': 'Needs buyer confirmation', 'tradeoff': 'Service responsibility', 'requirements': 'Written quotation', 'next_check': 'Request offer', 'evidence_ids': [eid]}]
            report['validation_priorities'] = [{'question': 'Buyer requirements', 'why_first': 'Changes feasibility', 'next_step': 'Request details', 'if_supported': 'Compare offers', 'if_not': 'Defer spending', 'evidence_ids': [eid]}]
        actions = [{'action': 'read_evidence', 'arguments': {'id': eid}}, {'action': 'finish', 'arguments': {'report': report}}]
        class Model:
            def next(self, messages, timeout):
                return actions.pop(0)
        real_agent = core.Agent
        saved = []
        class CaptureAgent(real_agent):
            def __init__(self, store, spec, model_factory=None):
                super().__init__(store, spec, Model)
            def run(self, *args, **kwargs):
                result = super().run(*args, **kwargs)
                saved.append(result['report'])
                return result
        output = self.root/'raw'
        argv = ['--case', case['id'], '--output', str(output)]
        with patch.dict('os.environ', {'AGENT_MODEL_BASE_URL': 'https://example.org/v1', 'AGENT_MODEL_NAME': 'test-double'}), patch.object(core, 'Agent', CaptureAgent):
            evaluate.main(argv)
            self.assertEqual(json.loads((output/'report.json').read_text(encoding='utf-8')), saved[0])
            self.assertEqual((output/'report.md').read_text(encoding='utf-8'), core.markdown(saved[0]))
            self.assertFalse(json.loads((output/'receipt.json').read_text(encoding='utf-8'))['manual_edits'])
            with self.assertRaises(SystemExit):
                evaluate.main(argv)
        self.assertFalse(actions)


if __name__ == '__main__':
    unittest.main()
