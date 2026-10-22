"""Run one explicitly selected historical case; preserve the agent's direct output privately."""
import argparse
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_cases(path):
    suite = json.loads(path.read_text(encoding='utf-8'))
    if suite.get('schema') != 'report-cases/v1' or suite.get('retrieval_mode') != 'fixed_public_corpus':
        raise ValueError('Expected report-cases/v1 with fixed_public_corpus')
    cases = suite.get('cases')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 12:
        raise ValueError('Supply 1–12 cases')
    seen = set()
    for case in cases:
        cid = case.get('id')
        if not isinstance(cid, str) or not cid or cid in seen:
            raise ValueError('Case IDs must be nonempty and unique')
        seen.add(cid)
        m = case['mission']
        if m.get('search_queries') != [] or m.get('project_id') or not m.get('as_of'):
            raise ValueError('Cases use only the supplied historical corpus, without search or project memory')
        if not 4 <= m.get('max_steps', 0) <= 12 or not 1 <= m.get('max_model_calls', 0) <= 13 or not 10 <= m.get('deadline_seconds', 0) <= 600:
            raise ValueError('Case budget exceeds the bounded evaluation limits')
        if not isinstance(case.get('sources'), list) or not 1 <= len(case['sources']) <= 8:
            raise ValueError('Supply 1–8 attributed sources per case')
        # Runtime validation handles exact timestamp parsing, scope and citation rules.
        for source in case['sources']:
            if source.get('synthetic') or source.get('status') != 'source_claim' or not source.get('published_at') or source['published_at'] > m['as_of']:
                raise ValueError('Historical cases require dated public source claims on/before as_of')
    return cases


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, default=ROOT/'examples/report-cases.json')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--list', action='store_true', help='List cases without model calls')
    mode.add_argument('--case', help='Explicit case ID to run with the configured provider')
    parser.add_argument('--output', type=Path, help='New empty private directory outside the repository')
    args = parser.parse_args(argv)
    cases = load_cases(args.suite)
    if args.list:
        print(json.dumps([{'id': c['id'], 'question': c['mission']['question']} for c in cases], ensure_ascii=False, indent=2))
        return
    selected = next((c for c in cases if c['id'] == args.case), None)
    if selected is None:
        parser.error('Unknown case ID; use --list')
    if not args.output:
        parser.error('--output is required for a live case')
    output = args.output.expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error('Keep live reports and receipts outside the public repository')
    if output.exists() and any(output.iterdir()):
        parser.error('Choose an empty directory; earlier raw reports will not be overwritten')
    if not os.environ.get('AGENT_MODEL_BASE_URL') or not os.environ.get('AGENT_MODEL_NAME'):
        parser.error('Configure the intended provider and model explicitly')
    module = json.loads((ROOT/'agent.json').read_text(encoding='utf-8'))['python_module']
    core = importlib.import_module(module+'.core')
    spec = importlib.import_module(module+'.product').SPEC
    version = importlib.import_module(module).__version__
    output.mkdir(parents=True, exist_ok=True)
    (output/'input.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    store = core.Store(output/'workspace')
    store.import_evidence({'schema': 'field-evidence/v1', 'records': selected['sources']})
    class RecordedModel(core.Model):
        def next(self, messages, timeout):
            action = super().next(messages, timeout)
            # Only the returned JSON action, never provider reasoning or auth headers.
            with (output/'actions.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(action, ensure_ascii=False)+'\n')
            return action
    run = core.Agent(store, spec, RecordedModel).run(selected['mission'], 'model')
    receipt = {'case': selected['id'], 'version': version, 'run_id': run['id'], 'state': run['state'],
               'error': run['error'], 'runtime': run['runtime'], 'model': os.environ['AGENT_MODEL_NAME'],
               'reasoning_effort': os.environ.get('AGENT_MODEL_REASONING_EFFORT'),
               'max_tokens': os.environ.get('AGENT_MODEL_MAX_TOKENS'),
               'input_fingerprint': fingerprint(selected['mission']), 'corpus_sha256': fingerprint(selected['sources']),
               'manual_edits': False, 'raw_agent_output': True,
               'actions': [s['action'] for s in run['steps']]}
    if run.get('report'):
        raw = json.dumps(run['report'], ensure_ascii=False, indent=2)+'\n'
        (output/'report.json').write_text(raw, encoding='utf-8')
        (output/'report.md').write_text(core.markdown(run['report']), encoding='utf-8')
        receipt['report_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    (output/'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    review = {'scope': 'Manual semantic review of unchanged agent output; no automatic quality grade.',
              'focus': selected.get('review_focus', []),
              'questions': ['是否先回答了题设中的决策问题？', '关键依据是否保留日期、适用对象和来源的确定程度？',
                            '分析是否解释事件如何影响题设业务，并比较实质取舍？',
                            '建议是否说明谁先取得什么资料、根据什么条件继续或改变选择？',
                            '正文是否连贯自然，各节是否在增加信息而非重复同一限制？'],
              'limits': 'Historical public summaries and fictional business conditions; not current advice or proof of broad quality.'}
    (output/'review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'case': selected['id'], 'state': run['state'], 'report_saved': bool(run.get('report')), 'model_calls': run['runtime'].get('model_calls')}))
    if run['state'] != 'completed':
        raise SystemExit('Incomplete run retained with run_id and workspace for inspection/recovery')


if __name__ == '__main__':
    main()
