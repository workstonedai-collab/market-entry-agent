"""Product task contracts. No extra agents, permissions or model calls."""
import hashlib
import json

PROFILES = {
 'topic-research': ('georisk-agent','专题研究与问题解释','研究者、咨询人员与国际问题爱好者',
   '围绕本次研究问题说明背景、行为体及其立场，比较有材料支持的解释与分歧。交代机制、时间顺序和替代解释，区分事件事实与分析观点。企业暴露不是必填项；没有企业资料时不要虚构公司、订单或经营建议。成果可用于研究讨论，不能把文献线索称作已经读过的文献。'),
 'event-tracking': ('georisk-agent','事件跟踪与报道准备','记者、研究者与地区关注者',
   '按资料日期与事件发生日期整理变化，保留原始声明、转述与不同说法的归属。优先说明新增了什么、哪些仍未确认、下一步向什么主体核实；采访问题只能作为建议，不能编造采访或独立核实。没有上一轮资料时明确这是首次梳理。'),
 'interest-watch': ('georisk-agent','利益影响与风险观察','有海外利益的企业、个人及顾问',
   '从用户明确提供的人员、资产、业务或其他利益分析影响路径，说明关联依据、关键条件及会改变判断的信号。关联不明时保留条件，不推断实际损失或替用户决定停工、撤离。优先说明下一项可操作的核查。'),
 'market-options': ('market-entry-agent','选市场与进入方式','企业业务团队、战略部门与咨询人员',
   '从产品、目标客户、企业阶段和约束比较市场与进入方式。说明选项的适用条件、代价、替代选择及下一步验证；缺失信息用条件判断，不编造市场规模、渠道名单或企业能力。摘要回答当前选择，正文保留比较推理。'),
 'transaction-review': ('market-entry-agent','交易责任与业务测算','业务、财务、风控与出海顾问',
   '分清生产方、出口方、卖方、进口主体和客户。引用项目已保存的同口径计算，区分报价与假设、贡献额与净利润、费用与现金占用。缺项保持未知，不从贸易术语自动推定税率或法律责任；解释哪些变量改变方案及应取得的报价。'),
 'operating-watch': ('market-entry-agent','经营前提与方案跟踪','高管、战略、风控及海外业务部门',
   '围绕已保存方案和关键假设解释新资料影响了什么，按决策影响和阻断条件安排核查。区分政策发布、生效和适用，说明适用主体与企业条件。保留已有选择，由操作者决定是否调整；行动可建议责任职能与验证节点，不冒称已批准或已执行。'),
}

def contract(product, name):
    if not name:
        return None
    if not isinstance(name,str) or name not in PROFILES or PROFILES[name][0] != product:
        raise ValueError('Task mode is not available for this product')
    owner,title,audience,instructions=PROFILES[name]
    value=dict(id=name,product=owner,title=title,audience=audience,instructions=instructions,
               inputs='Current question, optional private context and permitted sources',
               outputs='Saved report with read sources, reasoning, conditions and next steps',
               execution='Existing loop and budgets; no mandatory review or rewrite')
    value['version']=hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return value

def catalog(product):
    return [contract(product,k) for k,v in PROFILES.items() if v[0]==product]
