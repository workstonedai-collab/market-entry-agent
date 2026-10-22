"""Public research outlines and reusable output schemas."""
import hashlib,json
MARKET_LENSES=[
 {'id':'macro','name':'看宏观','questions':['市场基本面、经营确定性与对外连接分别有什么证据？','统计期、单位、历史值与预测值是否区分？']},
 {'id':'industry','name':'看行业','questions':['具体产品需求来自客户、产量还是进口代理指标？','供给、认证、关税与交付条件适用哪些产品？']},
 {'id':'competition','name':'看竞对','questions':['哪些企业在当地实际经营，来源和时间是什么？','是否有同地域、产品和时期的可靠份额？无则不给占比。']},
 {'id':'entry','name':'进入路径','questions':['经销、直销或本地实体分别需要哪些前置条件？','伙伴仅为线索还是已核实实体？官方联系入口不等于合作意愿。']}]
RISK_LENSES=[
 {'id':'change','name':'事件与演变','questions':['发生了什么，何时、何地，来源间是否存在冲突？','历史事件与当前进展如何区分？']},
 {'id':'exposure','name':'经营暴露','questions':['涉及哪些人员、资产、航线、供应链或订单？','什么机制可能把事件传导到企业？哪些只是分析假设？']},
 {'id':'baseline','name':'国区结构背景','questions':['治理与营商分项能解释什么长期背景？','年度基线不能替代即时预警；不由事件数生成风险分。']},
 {'id':'watch','name':'观察与应对','questions':['什么可观察条件会改变判断？','下一次检查什么来源，触发后谁需要决定什么？']}]

def plan(product, mission):
    return {'schema':'research-plan/v1','input_fingerprint':hashlib.sha256(json.dumps(mission,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'lenses':MARKET_LENSES if product=='market-entry-agent' else RISK_LENSES,
            'boundaries':['当前任务输入优先，不补企业未知能力或把行业分类当产品。','区分来源陈述、商业推断、拟议方案和待验证问题。','缺失数值为null；进口额不等于直接需求，平均关税不等于具体产品税率。','没有三个可比较时期不编趋势，没有可靠份额不画占比。'],
            'roadmap_contract':{'stages':[{'id':'research','goal':'阶段目标','actions':['计划工作'],'deliverables':['交付物'],'depends_on':[],'completion_signal':'可观察完成条件','evidence_ids':[]}],'note':'路线图为拟议计划，不代表已有合作方、项目完成或服务成交。'},
            'watchpoint_contract':{'condition':'可观察触发条件','exposure':'影响的经营对象','next_check':'接下来核查的来源/事项','evidence_ids':[]}}

def validate_extensions(report, read_ids):
    stages=report.get('roadmap',[]); watch=report.get('watchpoints',[])
    if not isinstance(stages,list) or len(stages)>12 or not isinstance(watch,list) or len(watch)>20: raise ValueError('Bounded roadmap/watchpoints lists required')
    seen=set()
    for s in stages:
        if not isinstance(s,dict):raise ValueError('Roadmap stage must be an object')
        if any(not isinstance(s.get(k),str) or not s[k].strip() or len(s[k])>3000 for k in ('id','goal','completion_signal')): raise ValueError('Roadmap stage requires id, goal, completion_signal')
        if s['id'] in seen:raise ValueError('Roadmap stage IDs must be unique')
        for key in ('actions','deliverables'):
            if not isinstance(s.get(key),list) or not s[key] or len(s[key])>15 or any(not isinstance(x,str) or not x or len(x)>3000 for x in s[key]):raise ValueError('Roadmap requires actions and deliverables')
        deps=s.get('depends_on',[])
        if not isinstance(deps,list) or any(not isinstance(x,str) or x not in seen for x in deps):raise ValueError('Roadmap dependencies must refer to preceding stages')
        refs=s.get('evidence_ids',[])
        if not isinstance(refs,list) or any(not isinstance(x,str) or x not in read_ids for x in refs):raise ValueError('Roadmap cites unread or unlisted evidence')
        seen.add(s['id'])
    for w in watch:
        if not isinstance(w,dict) or any(not isinstance(w.get(k),str) or not w[k].strip() or len(w[k])>3000 for k in ('condition','exposure','next_check')):raise ValueError('Watchpoint requires condition, exposure and next_check')
        refs=w.get('evidence_ids',[])
        if not isinstance(refs,list) or any(not isinstance(x,str) or x not in read_ids for x in refs):raise ValueError('Watchpoint cites unread or unlisted evidence')

def extension_markdown(report):
    lines=[]
    if report.get('roadmap'):
        lines+=['','## 进入路径与行动路线图 / Proposed roadmap','']
        for s in report['roadmap']:
            lines += ['### '+s['id']+' · '+s['goal'],'','前置阶段：'+(', '.join(s.get('depends_on',[])) or '无'),'','工作：'+'；'.join(s['actions']),'','交付物：'+'；'.join(s['deliverables']),'','完成条件：'+s['completion_signal'],'','依据：'+(', '.join(s.get('evidence_ids',[])) or '建议安排，无事实性引用')]
    if report.get('watchpoints'):
        lines+=['','## 观察条件 / Watchpoints','']
        lines += ['- '+w['condition']+' → '+w['exposure']+'；下一步：'+w['next_check']+' ['+', '.join(w.get('evidence_ids',[]))+']' for w in report['watchpoints']]
    return lines
