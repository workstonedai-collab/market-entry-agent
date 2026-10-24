"""Minimal document-only skill catalog; explicit private directory, frozen content hashes."""
import hashlib
import json
import os
from pathlib import Path
import re

BUILTINS = [
    {"name":"report-writing", "description":"报告默认启用：自然表达，保留依据、分析深度和确定程度。",
     "instructions":'写给需要作出判断的人。先回答本次问题，再用连贯段落说明依据、影响和取舍。段落围绕一个具体判断展开；该展开的机制、比较和条件要写清，不用缩短篇幅代替分析。\n保留来源归属、数字、日期、单位、否定、适用范围和确定程度。把来源内容、你的推断、建议计划和已完成事项说清；不为使文字生动添加事实，不把可能写成必然。证据不足时说明缺的是什么，以及它为什么会改变判断。\n按语境修改空话、同义重复、层叠定语、生硬直译和内部过程词。避免用口号、假对比、客服式收尾或“矩阵”“闭环”等标签代替解释；术语有实际含义时保留。不要给每句都加“来源陈述”“业务推断”等前缀；确有必要的来源限定在相应判断处说明，同一限制不必在每节重复。\n建议要落到要检查的资料、要比较的条件和下一步选择。可以作有理由的商业判断，交代推理和条件，不把整份报告写成缺口清单。中文用词与标点自然；只有信息确实并列或有先后时才用列表。直接在首次写作中应用，不增加独立审稿、润色调用、禁词评分或自动改写旧报告。\n来源发现只写引文真正支持的内容。题设企业的条件放入分析并说明来自题设，不用外部引文为它背书。保留每个时间和数值的对象：装运、过境、到港、合同截止日彼此不同；批准、刊登、生效、开始适用也分别说明。未知日期不自行换算为具体截止日。阈值的适用主体、合并口径、包含关系和边界比较符按资料原意保留；摘要未给出细则时列为待核事项，不自行补出规则。承担额外合规义务不等于商业路径不可行，要比较费用、责任能力和订单收益再建议继续或暂缓。\n围绕题设约束展开因果：事件或政策怎样影响成本、时间、履约、客户或合规，再比较可行方案的实际取舍。满足某一条件通常只说明方案可行；推荐优先方案还需比较替代选择，缺少报价时给出条件判断，不预设哪条更优。建议写清由什么职能的人向谁取得什么资料、在什么业务节点作决定，以及不同结果如何改变选择；没有给定时限时可提议安排，但不能冒称既有截止日。\n让各节各有用途：摘要给结论，分析解释机制和取舍，建议给有先后的工作，不确定性只留影响判断的缺口，后续观察写会改变判断的新信号。不要在每节复述同一批资料缺口或完整重写建议。路线图、观察条件和方案表按用户要求或实际需要选用，避免为填满模板重复正文。区分销售目标国、生产地、中转地和进口主体注册地；某方案涉及一个国家，不等于企业准备向该国客户销售，不另加题设没有的目标市场。预算建议优先按验证节点分批释放。若提出试投金额或比例，明确它是建议上限并解释依据，核对全文各处的金额、比例、加总和余款一致；没有费用依据时，不编看似精确的预算分配。'},
    {"name":"project-continuity", "description":"回看项目已有情况、记录和报告，接着研究本次问题。",
     "instructions":"Read project_state when project_id is present. Treat profile/exposure as private operator data. Link source-backed proposals to read evidence and stable business IDs, preserving revisions. Risk: group normalized subject/place/day, explain impact and next checks; a new URL is not independent corroboration. Entry: compare demand/access/channel/delivery/economics/risks under current constraints, preserve unknown values, propose stages and assumptions without asserting completion. Save the research report directly; project-update conflicts must not discard it."},
    {"name": "country-comparison", "description": "比较国区指标，同时说明数据期次、覆盖范围和缺失项。",
     "instructions": "Use country_baseline for mission countries. Read the returned evidence before citing. Compare source periods, component units and coverage. Keep annual structural background separate from current events. Use research_plan for the product's public outline; preserve missing values and different comparison bases."},
    {"name": "evidence-brief", "description": "围绕具体问题整理来源、分析影响，说明缺口和下一步。",
     "instructions": "Use only the current task's permitted queries and sources. Read selected evidence excerpts, preserving dates and source identity. Distinguish source claims, analysis, uncertainty and proposed actions. Current user input takes precedence over project memory. Form and save the requested report directly; technical citation checks do not imply independent factual review."},
]


def snapshot(store=None, product=None, project=None):
    entries = [dict(x, origin="bundled") for x in BUILTINS]
    configured = os.environ.get("AGENT_SKILLS_DIR", "")
    if configured:
        root = Path(configured).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("Configured skills directory is unavailable")
        candidates = sorted(root.glob("*/SKILL.md"))
        if len(candidates) > 8:
            raise ValueError("Configure at most 8 private document skills")
        for path in candidates:
            if not path.resolve().is_relative_to(root) or path.stat().st_size > 8000:
                raise ValueError("Skill must stay inside configured directory and be at most 8000 UTF-8 bytes")
            text = path.read_text(encoding="utf-8")
            parts = text.split("---", 2)
            if len(parts) != 3 or parts[0].strip():
                raise ValueError("Skill requires YAML frontmatter with one-line name and description")
            metadata = {}
            for line in parts[1].splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                key, separator, value = line.partition(":")
                if not separator or key not in ("name", "description", "inputs", "outputs", "requires_tools"):
                    raise ValueError("Skill loader supports one-line name, description, inputs, outputs and requires_tools")
                value = value.strip()
                if value.startswith('"'):
                    try:
                        value = json.loads(value)
                    except ValueError:
                        raise ValueError("Quoted skill metadata must be a JSON string") from None
                elif value.startswith("'"):
                    if not value.endswith("'"):
                        raise ValueError("Invalid quoted skill metadata")
                    value = value[1:-1].replace("''", "'")
                if key in metadata:
                    raise ValueError("Duplicate skill metadata")
                metadata[key] = value
            entries.append({**metadata, "instructions": parts[2].strip(), "origin": "operator_directory"})
    if store is not None and product and project:
        from .learning import Learning
        entries.extend({k:v for k,v in r.items() if k in ("name","description","instructions","requires_tools","inputs","outputs","origin")} for r in Learning(store,product).active(project))
    return normalize(entries)


def normalize(entries):
    result = {}
    for entry in entries:
        name, description = entry.get("name"), entry.get("description")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64 or name in result:
            raise ValueError("Invalid or duplicate skill name")
        if not isinstance(description, str) or not 1 <= len(description) <= 500 or not entry["instructions"]:
            raise ValueError("Skill requires a description and nonempty instructions")
        required=entry.get('requires_tools','')
        if not isinstance(required,str) or len(required)>500:raise ValueError('Skill requires_tools must be bounded comma-separated names')
        names=[x.strip() for x in required.split(',') if x.strip()]
        if len(names)>12 or any(not re.fullmatch(r'[a-z_]{1,64}',x) for x in names):raise ValueError('Invalid skill required tool names')
        for key in ('inputs','outputs'):
            if key in entry and (not isinstance(entry[key],str) or len(entry[key])>1000):raise ValueError('Skill contract text must be bounded')
        entry['contract']={'inputs':entry.get('inputs','Current mission and permitted source data'),
                           'outputs':entry.get('outputs','Task-appropriate analysis with sources, uncertainty and next checks'),
                           'requires_tools':names,'permission_note':'Documentation only; this does not enable tools, execute scripts or approve decisions.'}
        entry["version"] = hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        result[name] = entry
    return result


def catalog(entries):
    return [{k: entry[k] for k in ("name", "description", "version", "origin", "contract")} for entry in entries.values()]
