"""Readable project changes and optional report decision aids; no model calls."""
import copy

ASSESSMENT_FIELDS=('severity','status','confidence','impact','next_check')
VALUE_LABELS={'low':'低','moderate':'中','high':'高','critical':'严重','unconfirmed':'尚待确认','source_statement':'来源有说明，待交叉核实','corroborated':'多份资料相互支持','tracking':'跟踪中','escalated':'升级','easing':'缓和','closed':'结束'}

def display(value):
    return VALUE_LABELS.get(value,value) if value else '首次记录'


def evidence_details(store, ids):
    result=[]
    for eid in ids[:20]:
        try:row=store.read(eid)
        except ValueError:continue
        result.append({k:row.get(k) for k in ('id','title','url','published_at','retrieval_kind')})
        result[-1]['saved_excerpt']=row['body'][:500]
    return result


def alert_details(store, alerts):
    values=[];previous={}
    for item in alerts:
        row=copy.deepcopy(item);data=row['data'];old=data.get('previous') or {};current=data['assessment']
        data['changes']=[{'field':k,'before':old.get(k),'after':current[k]} for k in ASSESSMENT_FIELDS if old.get(k)!=current[k]]
        pair=(data['event_id'],data['exposure_id']);seen=previous.get(pair,[])
        data['new_evidence_ids']=[eid for eid in data['evidence_ids'] if eid not in seen]
        data['source_details']=evidence_details(store,data['evidence_ids']);previous[pair]=data['evidence_ids']
        values.append(row)
    return values


def validate(report, read_ids):
    for key, fields in [('decision_options',('name','fit','tradeoff','requirements','next_check')),('validation_priorities',('question','why_first','next_step','if_supported','if_not'))]:
        if key not in report:continue
        values=report[key]
        if not isinstance(values,list) or len(values)>8:raise ValueError('Bounded decision aids required')
        for value in values:
            if not isinstance(value,dict) or any(not isinstance(value.get(k),str) or not value[k].strip() or len(value[k])>3000 for k in fields):raise ValueError('Decision aid needs bounded text fields')
            refs=value.get('evidence_ids',[])
            if not isinstance(refs,list) or any(not isinstance(e,str) or e not in read_ids for e in refs):raise ValueError('Decision aid cites unread evidence')


def markdown(report):
    lines=[]
    for change in report.get('project_changes',[]):
        data=change['data'];lines+=['','## 本次变化与业务影响','',data['title']+' · '+data['exposure']]
        labels={'severity':'严重程度','status':'事件状态','confidence':'信息依据','impact':'业务影响','next_check':'接下来关注'}
        for diff in data['changes']:lines+=['','- '+labels[diff['field']]+'：'+str(display(diff['before']))+' → '+str(display(diff['after']))]
        lines+=['','变化说明：'+data.get('change_note','')]
        for source in data.get('source_details',[]):lines+=['','- 来源：'+source['title']+' '+source['url']+' ['+source['id']+']']
    if report.get('decision_options'):lines+=['','## 方案取舍','']
    for option in report.get('decision_options',[]):
        lines+=['### '+option['name'],'','适合的条件：'+option['fit'],'','主要取舍：'+option['tradeoff'],'','需要具备：'+option['requirements'],'','先验证：'+option['next_check'],'','依据：'+', '.join(option.get('evidence_ids',[])),'']
    if report.get('validation_priorities'):lines+=['','## 先验证什么','']
    for point in report.get('validation_priorities',[]):
        lines+=['### '+point['question'],'','为什么先做：'+point['why_first'],'','下一步：'+point['next_step'],'','若得到支持：'+point['if_supported'],'','若不成立：'+point['if_not'],'','依据：'+', '.join(point.get('evidence_ids',[])),'']
    return lines
