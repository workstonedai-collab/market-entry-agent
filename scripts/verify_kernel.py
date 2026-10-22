"""Reproduce shared-kernel behavior with an installed package and synthetic substitute model."""
import argparse
import importlib
import json
import os
from pathlib import Path
import platform
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def verify():
    metadata = json.loads((ROOT / "agent.json").read_text(encoding="utf-8"))
    module = metadata["python_module"]
    core = importlib.import_module(module + ".core")
    spec = importlib.import_module(module + ".product").SPEC
    memory_module = importlib.import_module(module + ".memory")
    seen = []
    checks = []
    clean = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_")}
    with patch.dict(os.environ, clean, clear=True), tempfile.TemporaryDirectory(prefix="kernel-check-") as temporary:
        workspace = Path(temporary) / "研究 project workspace"
        store = core.Store(workspace)
        memory = memory_module.ProjectMemory(store, spec["id"])
        memory.set("fictional-project", "budget", "Synthetic budget: 10")
        store.import_evidence({"schema": "field-evidence/v1", "records": [{"title": "越南虚构资料", "body": "A" * 26000 + "SYNTHETIC-TAIL-DETAIL",
            "url": "https://example.org/synthetic-kernel-case", "countries": ["Vietnam"], "topics": ["trade"], "synthetic": True}]})
        eid = store.export_evidence()["records"][0]["id"]
        mission = {"project_id": "fictional-project", "question": "研究越南贸易与后续观察", "countries": ["越南"], "topics": ["trade"],
                   "context": "Synthetic task only; current input overrides old project data.", "max_steps": 12, "deadline_seconds": 30, "context_budget_chars": 32000}
        report = {"title": "Synthetic kernel result", "summary": "Synthetic local case completed", "assessment": "This is a scripted verification, not model research.",
                  "findings": [{"claim": "SYNTHETIC-TAIL-DETAIL", "evidence_ids": [eid]}], "actions": [], "uncertainties": ["Synthetic case"],
                  "follow_up": [], "evidence_ids": [eid], "priority": "routine"}
        actions = [{"action": "load_skill", "arguments": {"name": "evidence-brief"}}, {"action": "recall", "arguments": {}},
                   {"action": "search_evidence", "arguments": {"query": "越南"}},
                   {"action": "read_evidence", "arguments": {"id": eid}}, {"action": "read_evidence", "arguments": {"id": eid}},
                   {"action": "read_evidence", "arguments": {"id": eid, "offset": 26000, "limit": 1000}},
                   {"action": "finish", "arguments": {"report": report}}]

        class Scripted:
            def next(self, messages, timeout):
                seen.append(messages)
                return actions.pop(0)

        run = core.Agent(store, spec, Scripted).run(mission, "model")
        assert run["state"] == "completed", run.get("error")
        assert run["report"]["synthetic"]
        assert max(sum(len(m["content"]) for m in messages) for messages in seen) <= 32000
        assert any("SYNTHETIC-TAIL-DETAIL" in json.dumps(messages) for messages in seen)
        assert any("reused_step" in step["observation"] for step in run["steps"])
        assert "evidence-brief" in run["runtime"]["skill_versions"]
        checks += ["chinese_country_identity", "paged_source_and_citation", "bounded_context_and_duplicate_reuse", "document_skill_version"]
        reopened = core.Store(workspace)
        assert reopened.get_run(run["id"])["report"] == run["report"]
        assert core.Agent(reopened, spec).run(resume=run["id"])["steps"] == run["steps"]
        assert memory.recall(dict(mission, question="A new question about the same project"))["previous"][0]["id"] == run["id"]
        assert memory.recall(dict(mission, project_id="another-project"))["previous"] == []
        memory.set("fictional-project", "budget", "Synthetic budget: 20")
        assert memory.facts("fictional-project")[0]["value"] == "Synthetic budget: 20"
        memory.forget("fictional-project", "budget")
        assert memory.facts("fictional-project") == []
        assert run["runtime"]["model_calls"] == 7 and not run["runtime"]["usage_complete"]
        checks += ["saved_result_reopen_and_resume", "project_recall_and_isolation", "operator_memory_correction_and_forget", "unknown_usage_stays_unknown"]
    return {"product": metadata["id"], "version": metadata["version"], "platform": platform.system(), "python": platform.python_version(),
            "checks": checks, "model_backend": "scripted_substitute", "external_requests": 0, "paid_model_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
