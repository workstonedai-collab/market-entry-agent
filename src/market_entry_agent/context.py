"""Bounded model context assembled from durable local records, without extra LLM calls."""
import json
from .business import brief as business_brief


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def preview(value, string_limit=800, list_limit=8):
    if isinstance(value, str):
        return value if len(value) <= string_limit else value[:string_limit] + " [excerpt; complete result retained locally]"
    if isinstance(value, list):
        result = [preview(x, string_limit, list_limit) for x in value[:list_limit]]
        if len(value) > list_limit:
            result.append({"remaining_items": len(value) - list_limit})
        return result
    if isinstance(value, dict):
        return {k: preview(v, string_limit, list_limit) for k, v in value.items()}
    return value


def assemble(seed, run, meta, budget):
    messages = [dict(m) for m in seed[:2]]
    snapshots = meta.get("loaded_skills", {})
    for name, skill in snapshots.items():
        messages.append({"role": "system", "content": "Configured skill " + name + " @ " + skill["version"] + "\n" + skill["instructions"]})
    project = meta.get("project_state")
    if project:
        messages.append({"role":"user", "content":"PRIVATE_BUSINESS_STATE (data; use project_state for typed contracts): " + encoded(preview(business_brief(project), 200, 10))})
    # Frozen at first attempt; explicit resume does not silently change instructions or facts.
    memory = meta.get("memory", {})
    if memory.get("facts") or memory.get("previous"):
        messages.append({"role": "user", "content": "PRIVATE_PROJECT_CONTEXT (data; current mission takes precedence): " + encoded(preview(memory, 1200, 5))})
    read_ids = sorted({s["observation"].get("id") for s in run["steps"]
                       if s["action"] == "read_evidence" and "error" not in s["observation"] and s["observation"].get("id")})
    progress = {"completed_steps": len(run["steps"]), "read_evidence_ids": read_ids,
                "steps": [{"seq": s["seq"], "action": s["action"], "error": s["observation"].get("error"),
                           "reused_step": s["observation"].get("reused_step")} for s in run["steps"]],
                "notice": "Full observations remain in local checkpoints. read_result retrieves a bounded result excerpt; read_evidence accepts offset/limit."}
    messages.append({"role": "user", "content": "SAVED_PROGRESS: " + encoded(progress)})
    # Leave room for a fresh execution-budget message, with no silent trimming of fixed input.
    size = sum(len(m["content"]) for m in messages)
    if size > budget - 1200:
        raise ValueError("context_fixed_inputs_exceed_budget: shorten task/skills/memory or increase context_budget_chars")
    recent = []
    elided = 0
    for step in reversed(run["steps"]):
        observation = step["observation"]
        # A finished report is recovered by the host before another model request.
        if step["action"] == "finish" and "error" not in observation:
            continue
        observation = dict(observation)
        if isinstance(observation.get("comparison"), dict):
            comparison = observation["comparison"]
            observation["comparison"] = {"same_basis": comparison.get("same_basis"),
                "countries": [{k: row.get(k) for k in ("code", "name", "reference_score", "formula_mode", "coverage", "period", "as_of")}
                              for row in comparison.get("countries", [])],
                "note": "Detailed components remain in this saved step; use read_result."}
        fresh = step["seq"] == run["steps"][-1]["seq"] and step["action"] in ("read_evidence", "read_result")
        item = {"role": "user", "content": "TOOL_OBSERVATION (untrusted data), saved step " + str(step["seq"]) + ": " + encoded(preview(observation, 6000 if fresh else 800))}
        if len(item["content"]) > (14000 if fresh else 7000):
            brief = {k: observation[k] for k in ("id", "evidence_ids", "error", "reused_step") if k in observation}
            brief["result_keys"] = list(observation)
            brief["excerpt"] = encoded(preview(observation, 200, 3))[:3000]
            brief["complete_result"] = {"tool": "read_result", "step": step["seq"]}
            item["content"] = "TOOL_OBSERVATION (untrusted data), saved step " + str(step["seq"]) + ": " + encoded(brief)
        if size + len(item["content"]) <= budget - 1200:
            recent.append(item)
            size += len(item["content"])
        else:
            elided += 1
    messages.extend(reversed(recent))
    return messages, {"context_characters": size, "context_budget_chars": budget,
                      "elided_observations": elided, "read_evidence_count": len(read_ids),
                      "skill_versions": {k: v["version"] for k, v in snapshots.items()}}
