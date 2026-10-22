"""Minimal document-only skill catalog; explicit private directory, frozen content hashes."""
import hashlib
import json
import os
from pathlib import Path
import re

BUILTINS = [
    {"name":"report-writing", "description":"报告默认启用：自然表达，保留依据、分析深度和确定程度。",
     "instructions":'写给需要作出判断的人。先回答本次问题，再用连贯段落说明依据、影响和取舍。段落围绕一个具体判断展开；该展开的机制、比较和条件要写清，不用缩短篇幅代替分析。\n保留来源归属、数字、日期、单位、否定、适用范围和确定程度。把来源内容、你的推断、建议计划和已完成事项说清；不为使文字生动添加事实，不把可能写成必然。证据不足时说明缺的是什么，以及它为什么会改变判断。\n按语境修改空话、同义重复、层叠定语、生硬直译和内部过程词。避免用口号、假对比、客服式收尾或“矩阵”“闭环”等标签代替解释；术语有实际含义时保留。不要给每句都加“来源陈述”“业务推断”等前缀；确有必要的来源限定在相应判断处说明，同一限制不必在每节重复。\n建议要落到要检查的资料、要比较的条件和下一步选择。可以作有理由的商业判断，交代推理和条件，不把整份报告写成缺口清单。中文用词与标点自然；只有信息确实并列或有先后时才用列表。直接在首次写作中应用，不增加独立审稿、润色调用、禁词评分或自动改写旧报告。'},
    {"name":"project-continuity", "description":"回看项目已有情况、记录和报告，接着研究本次问题。",
     "instructions":"Read project_state when project_id is present. Treat profile/exposure as private operator data. Link source-backed proposals to read evidence and stable business IDs, preserving revisions. Risk: group normalized subject/place/day, explain impact and next checks; a new URL is not independent corroboration. Entry: compare demand/access/channel/delivery/economics/risks under current constraints, preserve unknown values, propose stages and assumptions without asserting completion. Save the research report directly; project-update conflicts must not discard it."},
    {"name": "country-comparison", "description": "比较国区指标，同时说明数据期次、覆盖范围和缺失项。",
     "instructions": "Use country_baseline for mission countries. Read the returned evidence before citing. Compare source periods, component units and coverage. Keep annual structural background separate from current events. Use research_plan for the product's public outline; preserve missing values and different comparison bases."},
    {"name": "evidence-brief", "description": "围绕具体问题整理来源、分析影响，说明缺口和下一步。",
     "instructions": "Use only the current task's permitted queries and sources. Read selected evidence excerpts, preserving dates and source identity. Distinguish source claims, analysis, uncertainty and proposed actions. Current user input takes precedence over project memory. Form and save the requested report directly; technical citation checks do not imply independent factual review."},
]


def snapshot():
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
                if not separator or key not in ("name", "description"):
                    raise ValueError("Minimal skill loader supports only one-line name and description")
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
    result = {}
    for entry in entries:
        name, description = entry.get("name"), entry.get("description")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64 or name in result:
            raise ValueError("Invalid or duplicate skill name")
        if not isinstance(description, str) or not 1 <= len(description) <= 500 or not entry["instructions"]:
            raise ValueError("Skill requires a description and nonempty instructions")
        entry["version"] = hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        result[name] = entry
    return result


def catalog(entries):
    return [{k: entry[k] for k in ("name", "description", "version", "origin")} for entry in entries.values()]
