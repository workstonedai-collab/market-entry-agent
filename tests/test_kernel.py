"""Cross-run product behavior, budgets and compatibility; synthetic data only."""
import copy
import contextlib
import io
import importlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

MODULE = "market_entry_agent"
core = importlib.import_module(MODULE + ".core")
product = importlib.import_module(MODULE + ".product")
memory = importlib.import_module(MODULE + ".memory")
skills = importlib.import_module(MODULE + ".skills")


def report(eid=None):
    return {"title": "Synthetic kernel case", "summary": "Synthetic saved research", "assessment": "Synthetic analysis",
            "findings": [{"claim": "Synthetic source claim", "evidence_ids": [eid]}] if eid else [],
            "actions": [], "uncertainties": ["Synthetic fixture"], "follow_up": [], "evidence_ids": [eid] if eid else [], "priority": "routine"}


class KernelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = core.Store(Path(self.temp.name) / "研究 workspace")
        self.agent = core.Agent(self.store, product.SPEC)
        self.mission = {"project_id": "demo-project", "question": "研究越南贸易", "countries": ["越南"],
                        "topics": ["trade"], "max_steps": 12, "deadline_seconds": 30}
        self.memory = memory.ProjectMemory(self.store, product.SPEC["id"])

    def seed(self, body="Synthetic trade evidence"):
        self.store.import_evidence({"schema": "field-evidence/v1", "records": [{"title": "越南贸易资料", "body": body,
            "url": "https://example.org/synthetic-kernel", "countries": ["Vietnam"], "topics": ["trade"], "synthetic": True}]})
        return self.store.export_evidence()["records"][0]["id"]

    def run_actions(self, actions, mission=None):
        class Model:
            def next(self, messages, timeout):
                return actions.pop(0)
        return core.Agent(self.store, product.SPEC, Model).run(mission or self.mission, "model")

    def test_cli_skill_catalog_and_project_fact_roundtrip(self):
        app = importlib.import_module(MODULE + ".app")
        def command(*args):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(app.main(["--workspace", str(self.store.workspace), *args]), 0)
            return json.loads(output.getvalue())
        self.assertGreaterEqual(len(command("skills")["skills"]), 2)
        self.assertTrue(any(t["name"] == "read_result" for t in command("tools")["tools"]))
        command("memory-set", "cli-case", "产品", "虚构设备")
        self.assertEqual(command("memory", "cli-case")["facts"][0]["value"], "虚构设备")
        command("memory-forget", "cli-case", "产品")
        self.assertEqual(command("memory", "cli-case")["facts"], [])

    def test_related_project_recall_changed_question_and_isolation(self):
        first = self.agent.run(self.mission)
        changed = dict(self.mission, question="What changed in Vietnam?")
        self.assertEqual(self.memory.recall(changed)["previous"][0]["id"], first["id"])
        self.assertEqual(self.memory.recall(dict(changed, project_id="other-company"))["previous"], [])
        other = memory.ProjectMemory(self.store, "another-product")
        self.assertEqual(other.recall(changed)["previous"], [])
        separate = memory.ProjectMemory(core.Store(Path(self.temp.name)/"other"), product.SPEC["id"])
        self.assertEqual(separate.recall(changed)["previous"], [])

    def test_legacy_recall_punctuation_without_project_guessing(self):
        mission = dict(self.mission); mission.pop("project_id")
        first = self.agent.run(mission)
        self.assertEqual(self.memory.recall(dict(mission, question=mission["question"]+"?"))["previous"][0]["id"], first["id"])
        self.assertEqual(self.memory.recall(dict(mission, question="Different research question"))["previous"], [])

    def test_memory_correction_expiry_history_and_forget(self):
        first = self.memory.set("demo-project", "budget", "Synthetic 10")
        second = self.memory.set("demo-project", "budget", "Synthetic 20")
        self.assertEqual(second["supersedes"], first["id"])
        self.assertEqual(self.memory.facts("demo-project")[0]["value"], "Synthetic 20")
        self.memory.set("demo-project", "old", "Expired synthetic note", "2000-01-01T00:00:00Z")
        self.assertEqual(len(self.memory.facts("demo-project")), 1)
        self.assertEqual(self.memory.facts("demo-project", "2000-01-01T00:00:00Z"), [])
        self.assertEqual(self.memory.forget("demo-project", "budget")["removed_fact_revisions"], 2)
        self.assertEqual(self.memory.facts("demo-project"), [])

    def test_memory_future_report_excluded_from_historical_replay(self):
        self.agent.run(self.mission)
        self.assertEqual(self.memory.recall(dict(self.mission, as_of="2000-01-01T23:59:59Z"))["previous"], [])

    def test_current_input_and_frozen_memory_reused_after_failure(self):
        self.memory.set("demo-project", "budget", "old synthetic budget")
        class Broken:
            def next(self, messages, timeout):
                raise RuntimeError("model_http_429")
        mission = dict(self.mission, context="Current input: NEW synthetic budget")
        failed = core.Agent(self.store, product.SPEC, Broken).run(mission, "model")
        self.memory.set("demo-project", "budget", "edited after failure")
        seen = []
        class Recovered:
            def next(self, messages, timeout):
                seen.extend(messages)
                return {"action": "finish", "arguments": {"report": report()}}
        done = core.Agent(self.store, product.SPEC, Recovered).run(resume=failed["id"])
        self.assertEqual(done["state"], "completed")
        text = json.dumps(seen, ensure_ascii=False)
        self.assertIn("NEW synthetic budget", text)
        self.assertIn("old synthetic budget", text)
        self.assertNotIn("edited after failure", text)
        self.assertIn("current mission takes precedence", text)

    def test_country_aliases_search_and_read_without_rewriting_ids(self):
        eid = self.seed()
        results = self.store.search("越南贸易", ["越南"], ["trade"])
        self.assertEqual(results[0]["id"], eid)
        rid = self.store.create_run(product.SPEC["id"], self.mission, "model")
        read = self.agent.execute("read_evidence", {"id": eid}, self.store.get_run(rid), 5)
        self.assertEqual(read["id"], eid)
        self.assertEqual(self.store.export_evidence()["records"][0]["countries"], ["Vietnam"])
        self.assertEqual(self.store.search("zzzz_no_match", ["越南"], ["trade"]), [])

    def test_result_paging_preserves_complete_source_and_citation_scope(self):
        eid = self.seed("A"*6000 + "TAIL-SOURCE-DETAIL")
        run = self.store.get_run(self.store.create_run(product.SPEC["id"], self.mission, "model"))
        first = self.agent.execute("read_evidence", {"id": eid}, run, 10)
        tail = self.agent.execute("read_evidence", {"id": eid, "offset": 6000, "limit": 100}, run, 10)
        self.assertTrue(first["body_excerpt_truncated"])
        self.assertEqual(tail["body"], "TAIL-SOURCE-DETAIL")
        self.assertEqual(len(self.store.read(eid)["body"]), 6018)
        with self.assertRaises(ValueError):
            self.agent.execute("finish", {"report": report(eid)}, run, 10)

    def test_repeated_long_reads_reuse_checkpoint_and_stay_bounded(self):
        eid = self.seed("A"*28000)
        lengths = []
        class Repeater:
            n = 0
            def next(self, messages, timeout):
                lengths.append(sum(len(m["content"]) for m in messages)); self.n += 1
                if self.n <= 3:
                    return {"action": "read_evidence", "arguments": {"id": eid}}
                return {"action": "finish", "arguments": {"report": report(eid)}}
        run = core.Agent(self.store, product.SPEC, Repeater).run(self.mission, "model")
        self.assertEqual(run["state"], "completed")
        self.assertLessEqual(max(lengths), 48000)
        self.assertEqual(sum("reused_step" in s["observation"] for s in run["steps"]), 2)
        self.assertEqual(len(run["messages"]), 2)
        self.assertEqual(self.store.read(eid)["body"], "A"*28000)

    def test_no_progress_stops_and_saved_data_is_resumable(self):
        eid = self.seed()
        class Repeater:
            def next(self, messages, timeout):
                return {"action": "read_evidence", "arguments": {"id": eid}}
        failed = core.Agent(self.store, product.SPEC, Repeater).run(self.mission, "model")
        self.assertEqual(failed["error"], "no_progress_detected")
        self.assertEqual(len(failed["steps"]), 5)
        class Finisher:
            def next(self, messages, timeout):
                return {"action": "finish", "arguments": {"report": report(eid)}}
        done = core.Agent(self.store, product.SPEC, Finisher).run(resume=failed["id"])
        self.assertEqual(done["state"], "completed")
        self.assertEqual(done["steps"][:5], failed["steps"])

    def test_model_time_is_recomputed_before_new_tool(self):
        clock = [0.0]
        class Late:
            def next(self, messages, timeout):
                clock[0] = 11
                return {"action": "fetch_feed", "arguments": {"id": "never-fetch"}}
        with patch.object(core.time, "monotonic", side_effect=lambda: clock[0]), patch.object(core, "fetch_feed") as fetch:
            run = core.Agent(self.store, product.SPEC, Late).run(dict(self.mission, deadline_seconds=10), "model")
        self.assertEqual(run["error"], "run_deadline_exceeded_before_tool")
        fetch.assert_not_called()

    def test_late_completed_content_is_saved_with_budget_status(self):
        clock = [0.0]
        class Late:
            def next(self, messages, timeout):
                clock[0] = 11
                return {"action": "finish", "arguments": {"report": report()}}
        with patch.object(core.time, "monotonic", side_effect=lambda: clock[0]):
            run = core.Agent(self.store, product.SPEC, Late).run(dict(self.mission, deadline_seconds=10), "model")
        self.assertEqual(run["state"], "completed")
        self.assertEqual(run["report"]["runtime"]["budget_status"], "finish_returned_after_attempt_deadline")

    def test_failed_calls_count_across_explicit_resume(self):
        class Broken:
            def next(self, messages, timeout):
                raise RuntimeError("model_http_429")
        agent = core.Agent(self.store, product.SPEC, Broken)
        run = agent.run(dict(self.mission, max_model_calls=2), "model")
        run = agent.run(resume=run["id"])
        run = agent.run(resume=run["id"])
        self.assertEqual(run["error"], "model_call_budget_exhausted")
        self.assertEqual(run["runtime"]["model_calls"], 2)
        self.assertFalse(run["runtime"]["usage_complete"])

    def test_context_never_silently_truncates_fixed_input(self):
        class Never:
            def next(self, messages, timeout):
                raise AssertionError("Provider should not be called")
        run = core.Agent(self.store, product.SPEC, Never).run(dict(self.mission, context="X"*24000, context_budget_chars=16000), "model")
        self.assertIn("context_fixed_inputs_exceed_budget", run["error"])
        self.assertEqual(run["runtime"]["model_calls"], 0)

    def test_tool_contracts_reject_wrong_types_extra_args_and_ambiguous_fetch(self):
        run = {"mission": self.mission, "steps": [], "engine": "model"}
        for name, args in [("read_evidence", {"id": "x", "offset": True}), ("fetch_page", {"source_id": "x", "evidence_id": "y"}),
                           ("recall", {"shell": "anything"}), ("web_search", {"query_index": "0"})]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.agent.execute(name, args, run, 10)

    def test_document_skill_loading_snapshot_and_resume_without_private_files(self):
        root = Path(self.temp.name)/"private-skills"; folder = root/"synthetic-review";folder.mkdir(parents=True)
        file = folder/"SKILL.md"
        file.write_text('---\nname: synthetic-review\ndescription: Synthetic test procedure\n---\nPRIVATE-DOCUMENT-FIXTURE. Never execute scripts.', encoding="utf-8")
        seen = []
        class First:
            n = 0
            def next(self, messages, timeout):
                self.n += 1
                if self.n == 1:
                    return {"action": "load_skill", "arguments": {"name": "synthetic-review"}}
                raise RuntimeError("model_http_429")
        with patch.dict(os.environ, {"AGENT_SKILLS_DIR": str(root)}):
            failed = core.Agent(self.store, product.SPEC, First).run(self.mission, "model")
        self.assertNotIn("PRIVATE-DOCUMENT-FIXTURE", json.dumps(failed["steps"]))
        file.unlink()
        class Finish:
            def next(self, messages, timeout):
                seen.extend(messages)
                return {"action": "finish", "arguments": {"report": report()}}
        done = core.Agent(self.store, product.SPEC, Finish).run(resume=failed["id"])
        self.assertEqual(done["state"], "completed")
        self.assertIn("PRIVATE-DOCUMENT-FIXTURE", json.dumps(seen))
        self.assertIn("synthetic-review", done["runtime"]["skill_versions"])

    def test_skill_configuration_cannot_override_builtins(self):
        root = Path(self.temp.name)/"skills"; folder=root/"duplicate";folder.mkdir(parents=True)
        (folder/"SKILL.md").write_text('---\nname: evidence-brief\ndescription: Duplicate\n---\nText', encoding="utf-8")
        with patch.dict(os.environ, {"AGENT_SKILLS_DIR": str(root)}), self.assertRaisesRegex(ValueError, "duplicate"):
            skills.snapshot()

    def test_cancel_during_model_does_not_execute_returned_action(self):
        store = self.store
        class Cancelling:
            def next(self, messages, timeout):
                rid = store.list_runs()[0]["id"]
                store.control(rid, "cancelled")
                return {"action": "finish", "arguments": {"report": report()}}
        run = core.Agent(self.store, product.SPEC, Cancelling).run(self.mission, "model")
        self.assertEqual(run["state"], "cancelled")
        self.assertIsNone(run["report"])
        self.assertEqual(self.agent.run(resume=run["id"])["state"], "cancelled")

    def test_pause_and_resume_preserve_completed_tools(self):
        eid = self.seed();store=self.store
        class Pausing:
            n = 0
            def next(self, messages, timeout):
                self.n += 1
                if self.n == 1:
                    return {"action": "read_evidence", "arguments": {"id": eid}}
                store.control(store.list_runs()[0]["id"], "paused")
                return {"action": "finish", "arguments": {"report": report(eid)}}
        paused = core.Agent(self.store, product.SPEC, Pausing).run(self.mission, "model")
        self.assertEqual(paused["state"], "paused")
        class Finish:
            def next(self, messages, timeout):
                return {"action": "finish", "arguments": {"report": report(eid)}}
        done = core.Agent(self.store, product.SPEC, Finish).run(resume=paused["id"])
        self.assertEqual(done["state"], "completed")
        self.assertEqual(done["steps"][0], paused["steps"][0])

    def test_queued_pause_is_not_an_implicit_resume(self):
        rid = self.store.create_run(product.SPEC["id"], self.mission, "demo")
        self.store.control(rid, "paused")
        held = self.agent.run(resume=rid, allow_paused=False)
        self.assertEqual(held["state"], "paused")
        self.assertFalse(self.store.claim(rid, 30, "worker", allow_paused=False))
        self.assertEqual(self.agent.run(resume=rid)["state"], "completed")

    def test_expired_facts_do_not_consume_active_project_capacity(self):
        for i in range(40):
            self.memory.set("demo-project", "old_"+str(i), "Expired synthetic fact", "2000-01-01T00:00:00Z")
        self.memory.set("demo-project", "current", "Current synthetic fact")
        self.assertEqual([f["key"] for f in self.memory.facts("demo-project")], ["current"])

    def test_control_prevents_a_new_model_call_at_dispatch_boundary(self):
        rid = self.store.create_run(product.SPEC["id"], self.mission, "model")
        self.store.claim(rid, 30, "owner")
        self.store.control(rid, "paused")
        with self.assertRaisesRegex(RuntimeError, "run_paused"):
            self.store.start_call(rid, "attempt", 0, {"context_characters": 100}, "owner")
        self.assertEqual(self.store.runtime_summary(rid)["model_calls"], 0)

    def test_old_owner_release_does_not_clear_new_lease(self):
        rid = self.store.create_run(product.SPEC["id"], self.mission, "model")
        self.store.claim(rid, 30, "new")
        before = self.store.get_run(rid)["lease_until"]
        self.store.release(rid, "old")
        self.assertEqual(self.store.get_run(rid)["lease_until"], before)

    def test_expired_owner_cannot_overwrite_new_owner(self):
        rid = self.store.create_run(product.SPEC["id"], self.mission, "model")
        self.store.claim(rid, 30, "first")
        with self.store.tasks() as db:
            db.execute("UPDATE runs SET lease_until=0 WHERE id=?", (rid,))
        self.assertTrue(self.store.claim(rid, 30, "second"))
        with self.assertRaisesRegex(RuntimeError, "owner_changed"):
            self.store.finish(rid, report(), "first")
        self.store.fail(rid, "old-error", "first")
        self.assertEqual(self.store.get_run(rid)["state"], "running")

    def test_usage_is_provider_reported_and_partial_values_stay_unknown(self):
        class Used:
            last_usage = {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20, "secret": "ignore"}
            def next(self, messages, timeout):
                return {"action": "finish", "arguments": {"report": report()}}
        run = core.Agent(self.store, product.SPEC, Used).run(self.mission, "model")
        self.assertEqual(run["runtime"]["reported_usage"]["total_tokens"], 20)
        self.assertTrue(run["runtime"]["usage_complete"])
        self.assertNotIn("secret", json.dumps(self.store.call_receipts(run["id"])))

    def test_old_database_and_finish_checkpoint_upgrade_without_a_model(self):
        rid = self.store.create_run(product.SPEC["id"], self.mission, "model")
        old_report = report()
        self.store.checkpoint(rid, 0, "finish", {"report": old_report}, [])
        with self.store.tasks() as db:
            for table in ("project_facts", "project_runs", "run_meta", "run_owners", "step_inputs", "model_calls"):
                db.execute("DROP TABLE " + table)
        reopened = core.Store(self.store.workspace)
        class Never:
            def __init__(self):
                raise AssertionError("Do not call a provider to recover a saved finish")
        done = core.Agent(reopened, product.SPEC, Never).run(resume=rid)
        self.assertEqual(done["state"], "completed")
        self.assertEqual(done["report"]["summary"], old_report["summary"])
        self.assertEqual(len(done["steps"]), 1)
        self.assertFalse(done["runtime"]["tracking_available"])


if __name__ == "__main__":
    unittest.main()
