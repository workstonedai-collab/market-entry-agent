"""Minimal document-only skill catalog; explicit private directory, frozen content hashes."""
import hashlib
import json
import os
from pathlib import Path
import re

BUILTINS = [
    {"name":"project-continuity", "description":"Continue an event-monitoring or enterprise-entry project with typed state.",
     "instructions":"Read project_state when project_id is present. Treat profile/exposure as private operator data. Link source-backed proposals to read evidence and stable business IDs, preserving revisions. Risk: group normalized subject/place/day, explain impact and next checks; a new URL is not independent corroboration. Entry: compare demand/access/channel/delivery/economics/risks under current constraints, preserve unknown values, propose stages and assumptions without asserting completion. Save the research report directly; project-update conflicts must not discard it."},
    {"name": "country-comparison", "description": "Compare the source periods and coverage of public country observations.",
     "instructions": "Use country_baseline for mission countries. Read the returned evidence before citing. Compare source periods, component units and coverage. Keep annual structural background separate from current events. Use research_plan for the product's public outline; preserve missing values and different comparison bases."},
    {"name": "evidence-brief", "description": "Organize a sourced research brief and explain gaps and proposed follow-up.",
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
