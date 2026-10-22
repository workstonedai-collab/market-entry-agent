from __future__ import annotations

SPEC = {'id': 'market-entry-agent',
 'name': '企业出海咨询/国区营商环境监测智能体',
 'port': 8712,
 'accent': '#325f9e',
 'tagline': '从产品、客户和经营条件出发，比较目标市场与进入方式，把下一步需要验证和推进的事说清楚。',
 'system': 'Write a market-entry research brief for the supplied question. Use the provided public sources. '
           'Cite read evidence, state uncertainty and keep proposed actions separate from facts. Start from '
           'the actual product, buyer and constraints. Compare feasible market-entry options, explain '
           'tradeoffs and testable assumptions, and propose concrete next steps. Do not replace '
           'enterprise-specific reasoning with generic country summaries.',
 'starter': {'question': '一家设备出口企业考虑越南与印度尼西亚。结合现有资料，比较需求、准入、渠道与售后条件，说明选择市场前还需要验证什么。',
             'countries': ['Vietnam', 'Indonesia'],
             'topics': ['trade', 'investment', 'logistics'],
             'context': '虚构演示：设备出口团队正在收集公开资料。',
             'max_steps': 12,
             'deadline_seconds': 180},
 'demo_summary': '规则演示已整理导入的虚构资料，并保留来源与日期。',
 'demo_assessment': '这是虚构资料的规则演示。请检查来源及适用范围，补充资料后再形成实际业务判断。',
 'demo_actions': ['查看各项资料的来源与日期。', '补充与本次问题相关的资料。'],
 'demo_follow': ['下次运行时比较资料是否有更新。']}


def demo_report(mission, evidence, previous):
    ids = [e["id"] for e in evidence]
    return {
        "title": SPEC["name"] + " · " + ("虚构情景演示" if evidence else "证据缺口说明"),
        "summary": SPEC["demo_summary"] if evidence else "任务范围内没有可用证据。请导入资料或注册信息源后再开展研究。",
        "findings": [{"claim": e["title"] + "：" + e["body"], "evidence_ids": [e["id"]]} for e in evidence],
        "assessment": SPEC["demo_assessment"] if evidence else "没有证据支持事实判断、选国排名或预警升级。",
        "priority": "watch" if evidence else "routine",
        "actions": SPEC["demo_actions"] if evidence else ["导入与任务国区、主题相符的证据包。"],
        "uncertainties": ["此运行由确定性规则生成，未调用大模型。", "资料是虚构演练数据，没有覆盖真实环境。"] if evidence else ["当前证据缺失。"],
        "follow_up": SPEC["demo_follow"] + (["已找到同一任务的历史报告；本轮保留独立版本。"] if previous else []),
        "evidence_ids": ids,
    }


SPEC["demo_report"] = demo_report
