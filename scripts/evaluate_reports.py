"""Review a saved report, or explicitly run a bounded live public case. No AI-detection scores."""
import argparse
import importlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def worksheet(report):
    sources={s['id'] for s in report.get('sources',[])}
    cited=set(report.get('evidence_ids',[]))
    return {'checks_scope':'Structure and receipts only; semantic and writing review is manual.',
      'engine':report.get('engine'),'historical_replay':report.get('historical_replay',False),
      'writing_skill':report.get('writing_skill'),
      'references_present_in_source_list':cited.issubset(sources),
      'all_findings_have_listed_references':all(bool(f.get('evidence_ids')) and set(f['evidence_ids']).issubset(cited) for f in report.get('findings',[])),
      'human_review':[
       'Does the report answer the actual question before providing background?',
       'Do the cited sources support the nearby claim, including its date and scope?',
       'Are business implications reasoned from the supplied conditions rather than invented?',
       'Are facts, attributed claims, uncertainty and proposed work kept distinct?',
       'Does the prose avoid empty framing, repeated caveats and process narration without losing useful reasoning?',
       'Are options compared on meaningful tradeoffs and the next check that would change the decision?',
       'For risk: what changed, which exposure matters, and what observable development changes the assessment?',
       'Are historical examples clearly distinguished from current conditions?']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--report',type=Path,help='Inspect an existing saved report without model calls')
    group.add_argument('--live',action='store_true',help='Call the configured provider for one fictional project with attributed historical sources')
    parser.add_argument('--output',type=Path,required=True,help='New empty private output directory outside the repository')
    args=parser.parse_args();output=args.output.expanduser().resolve()
    if output==ROOT or ROOT in output.parents:parser.error('Keep reports and private evaluation receipts outside the public repository')
    if output.exists() and any(output.iterdir()):parser.error('Choose an empty output directory to preserve prior results')
    output.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((ROOT/'agent.json').read_text(encoding='utf-8'));module=metadata['python_module'];core=importlib.import_module(module+'.core')
    spec=importlib.import_module(module+'.product').SPEC
    if args.live:
        if not os.environ.get('AGENT_MODEL_BASE_URL') or not os.environ.get('AGENT_MODEL_NAME'):parser.error('Configure the intended model explicitly before --live')
        case=json.loads((ROOT/'examples/public-project-case.json').read_text(encoding='utf-8'))
        countries=sorted({c for s in case['sources'] for c in s['countries']});topics=sorted({t for s in case['sources'] for t in s['topics']})
        cutoff=max(s['published_at'] for s in case['sources'])[:10]+'T23:59:59Z'
        risk=metadata['id']=='georisk-agent'
        mission={'question':'根据已保存的两份历史资料，说明事件进展、对题设业务的可能影响和下一次观察条件。' if risk else '根据已保存的两份历史资料，比较进入方案的取舍，并说明应先验证什么、不同结果将怎样改变选择。',
          'context':'虚构演示：一家设备出口商正在研究相关国区，尚无具体船期、客户订单和报价。不要补造经营数据。',
          'countries':countries,'topics':topics,'as_of':cutoff,'max_steps':10,'max_model_calls':12,'deadline_seconds':600,'search_queries':[]}
        if not risk:mission['output_sections']=['decision_options','validation_priorities']
        store=core.Store(output/'workspace');store.import_evidence({'schema':'field-evidence/v1','records':case['sources']})
        run=core.Agent(store,spec).run(mission,'model')
        (output/'runtime.json').write_text(json.dumps({'run_id':run['id'],'state':run['state'],'error':run['error'],'runtime':run['runtime'],'model':os.environ['AGENT_MODEL_NAME'],'model_base_not_exported':True},ensure_ascii=False,indent=2),encoding='utf-8')
        if run['state']!='completed':raise RuntimeError('Live evaluation did not complete; inspect the private runtime receipt')
        report=run['report']
    else:report=json.loads(args.report.read_text(encoding='utf-8'))
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'report.md').write_text(core.markdown(report),encoding='utf-8')
    (output/'review.json').write_text(json.dumps(worksheet(report),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output_files':['report.json','report.md','review.json'],'live_model_called':args.live,'quality_grade':'not_automatically_assigned'}))


if __name__=='__main__':main()
