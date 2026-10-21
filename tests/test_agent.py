import contextlib
import importlib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

MODULE = "market_entry_agent"
core = importlib.import_module(MODULE + ".core")
app = importlib.import_module(MODULE + ".app")
product = importlib.import_module(MODULE + ".product")
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = core.load_json(ROOT / "examples/demo-evidence.json")


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = core.Store(self.temp.name)
        self.mission = dict(product.SPEC["starter"])
        self.agent = core.Agent(self.store, product.SPEC)

    def seed(self):
        self.store.import_evidence(FIXTURES)

    def test_demo_saved_reopened_and_exportable(self):
        self.seed()
        run = self.agent.run(self.mission)
        self.assertEqual(run["state"], "completed")
        self.assertTrue(run["report"]["synthetic"])
        self.assertIn("SYNTHETIC DEMONSTRATION", core.markdown(run["report"]))
        reopened = core.Store(self.temp.name).get_run(run["id"])
        self.assertEqual(reopened["report"], run["report"])
        self.assertGreaterEqual(len(run["steps"]), 5)
        self.assertEqual(self.agent.run(resume=run["id"])["steps"], run["steps"])

    def test_evidence_roundtrip_and_exact_duplicate(self):
        first = self.store.import_evidence(FIXTURES)
        again = self.store.import_evidence(FIXTURES)
        self.assertEqual(first["added"], 5)
        self.assertEqual(again["added"], 0)
        other = core.Store(Path(self.temp.name)/"other")
        bundle = self.store.export_evidence()
        other.import_evidence(bundle)
        self.assertEqual(other.export_evidence(), bundle)

    def test_default_event_key_roundtrip_stable(self):
        record = dict(FIXTURES["records"][0])
        record.pop("event_key")
        self.store.import_evidence({"schema":"field-evidence/v1","records":[record]})
        self.assertEqual(self.store.import_evidence(self.store.export_evidence())["added"], 0)

    def test_revisions_preserve_event_identity(self):
        self.seed()
        changed = dict(FIXTURES["records"][0])
        changed["body"] += " Additional revision."
        self.store.import_evidence({"schema":"field-evidence/v1","records":[changed]})
        event = [r for r in self.store.export_evidence()["records"] if r["event_key"] == changed["event_key"]]
        self.assertEqual(len(event), 3)
        self.assertEqual(len({r["id"] for r in event}), 3)

    def test_mission_scope_excludes_unrelated_country(self):
        self.seed()
        run = self.agent.run(self.mission)
        for source in run["report"]["sources"]:
            self.assertNotIn("法国", source["title"])

    def test_empty_evidence_does_not_invent_findings(self):
        run = self.agent.run(self.mission)
        self.assertEqual(run["state"], "completed")
        self.assertEqual(run["report"]["priority"], "routine")
        self.assertEqual(run["report"]["findings"], [])

    def test_demo_does_not_turn_live_evidence_into_synthetic_analysis(self):
        record = dict(FIXTURES["records"][0], status="source_claim")
        self.store.import_evidence({"schema":"field-evidence/v1","records":[record]})
        self.assertEqual(self.agent.run(self.mission)["report"]["findings"], [])

    def test_unread_citation_is_rejected(self):
        self.seed()
        rid = self.store.create_run(product.SPEC["id"], self.mission, "model")
        report = product.demo_report(self.mission,self.store.search(countries=self.mission["countries"],topics=self.mission["topics"]),[])
        with self.assertRaisesRegex(ValueError,"actually|read"):
            self.agent.execute("finish", {"report":report}, self.store.get_run(rid), 30)

    def test_out_of_scope_read_is_rejected(self):
        self.seed()
        eid = next(r["id"] for r in self.store.export_evidence()["records"] if r["countries"] == ["France"])
        rid = self.store.create_run(product.SPEC["id"], self.mission,"model")
        with self.assertRaisesRegex(ValueError,"scope"):
            self.agent.execute("read_evidence", {"id":eid}, self.store.get_run(rid),30)

    def test_repeat_mission_keeps_reports_deduplicates_outbox(self):
        self.seed()
        a,b = self.agent.run(self.mission),self.agent.run(self.mission)
        self.assertNotEqual(a["id"],b["id"])
        self.assertEqual(len(self.store.outbox()),1)
        self.assertEqual(len(self.store.list_runs()),2)
        self.assertTrue(b["steps"][0]["observation"]["previous"])
        self.store.approve(self.store.outbox()[0]["id"])
        self.assertEqual(self.store.outbox()[0]["state"],"approved")

    def test_separate_private_workspaces_share_only_evidence(self):
        shared=Path(self.temp.name)/"shared.sqlite3"
        a=core.Store(Path(self.temp.name)/"a",shared)
        b=core.Store(Path(self.temp.name)/"b",shared)
        a.import_evidence(FIXTURES)
        mission=dict(self.mission,context="PRIVATE-COMPANY-CONTEXT")
        core.Agent(a,product.SPEC).run(mission)
        self.assertEqual(len(b.export_evidence()["records"]),5)
        self.assertEqual(b.list_runs(),[])
        self.assertNotIn("PRIVATE-COMPANY-CONTEXT",json.dumps(a.export_evidence()))

    def test_atomic_run_lease(self):
        rid=self.store.create_run(product.SPEC["id"],self.mission,"demo")
        self.assertTrue(self.store.claim(rid,30))
        self.assertFalse(self.store.claim(rid,30))

    def test_model_failure_resume_preserves_saved_steps(self):
        self.seed()
        outer=self
        class Failing:
            n=0
            def next(self,messages,timeout):
                self.n+=1
                if self.n==1:
                    return {"action":"search_evidence","arguments":{}}
                raise RuntimeError("model_http_429")
        run=core.Agent(self.store,product.SPEC,Failing).run(self.mission,"model")
        self.assertEqual(run["state"],"failed")
        first_step=run["steps"][0]
        class Recovered:
            def next(self,messages,timeout):
                return outer.agent.demo_action(outer.store.get_run(run["id"]))
        # demo_action expects recall first; provide a recovery model with explicit read/finish.
        class Recovered:
            def next(self,messages,timeout):
                current=outer.store.get_run(run["id"])
                rows=current["steps"][0]["observation"]["results"][:4]
                seen={s["observation"].get("id") for s in current["steps"] if s["action"]=="read_evidence"}
                for row in rows:
                    if row["id"] not in seen:
                        return {"action":"read_evidence","arguments":{"id":row["id"]}}
                return {"action":"finish","arguments":{"report":product.demo_report(outer.mission,rows,[])}}
        done=core.Agent(self.store,product.SPEC,Recovered).run(resume=run["id"])
        self.assertEqual(done["state"],"completed")
        self.assertEqual(done["steps"][0],first_step)
        self.assertEqual(sum(s["action"]=="search_evidence" for s in done["steps"]),1)

    def test_budget_limits_repeated_bad_tools(self):
        class Bad:
            def next(self,messages,timeout):
                return {"action":"execute_shell","arguments":{}}
        run=core.Agent(self.store,product.SPEC,Bad).run(dict(self.mission,max_steps=4),"model")
        self.assertEqual(run["error"],"step_budget_exhausted")
        self.assertEqual(len(run["steps"]),4)
        self.assertTrue(all("error" in s["observation"] for s in run["steps"]))

    def test_recover_finish_checkpoint_before_result_commit(self):
        rid=self.store.create_run(product.SPEC["id"],self.mission,"demo")
        report=product.demo_report(self.mission,[],[])
        self.store.checkpoint(rid,0,"finish",{"report":report},[])
        done=self.agent.run(resume=rid)
        self.assertEqual(done["state"],"completed")
        self.assertEqual(len(done["steps"]),1)

    def test_worker_due_task_is_claimed_once(self):
        self.seed()
        sid=self.store.add_schedule(self.mission,"demo",60)
        self.assertEqual(sid,self.store.add_schedule(self.mission,"demo",60))
        claimed=self.store.due()
        self.assertEqual(len(claimed),1)
        self.assertEqual(self.store.due(),[])
        self.store.schedule_complete(sid)
        self.assertEqual(app.tick(self.store),[])
        with self.store.tasks() as db:
            db.execute("UPDATE schedule SET next_due=0")
        self.assertEqual(app.tick(self.store)[0]["state"],"completed")

    def test_feed_parser_imports_source_claim(self):
        config={"sources":[{"id":"public","url":"https://publisher.example/feed","allowed_hosts":["publisher.example"],"countries":["Vietnam"],"topics":["trade"]}]}
        self.store.register_sources(config)
        xml=b'<rss><channel><item><title>Claim</title><description>A source claim</description><link>https://publisher.example/1</link></item></channel></rss>'
        with patch.object(core,"fetch_public_https",return_value=xml):
            self.assertEqual(core.fetch_feed(self.store,"public")["added"],1)
        self.assertEqual(self.store.export_evidence()["records"][0]["status"],"source_claim")
        with patch.object(core,"fetch_public_https",return_value=b'<!DOCTYPE x><rss/>'):
            with self.assertRaisesRegex(ValueError,"DTD"):
                core.fetch_feed(self.store,"public")

    def test_feed_fetch_blocks_private_and_unlisted_hosts(self):
        with self.assertRaisesRegex(ValueError,"allowlist"):
            core.fetch_public_https("https://evil.example/",["good.example"])
        with patch.object(core.socket,"getaddrinfo",return_value=[(2,1,6,"",("127.0.0.1",443))]):
            with self.assertRaisesRegex(ValueError,"Private"):
                core.fetch_public_https("https://publisher.example/",["publisher.example"])

    def test_invalid_mission_rejected(self):
        with self.assertRaises(ValueError):
            self.agent.run({"question":"x"})
        with self.assertRaises(ValueError):
            self.agent.run(dict(self.mission,max_steps=100))

    def test_model_http_contract_and_full_loop(self):
        self.seed()
        actions=[{"action":"search_evidence","arguments":{}}]
        rows=self.store.search(self.mission["question"],self.mission["countries"],self.mission["topics"])[:4]
        actions += [{"action":"read_evidence","arguments":{"id":r["id"]}} for r in rows]
        actions += [{"action":"finish","arguments":{"report":product.demo_report(self.mission,rows,[])}}]
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_POST(self):
                received.append((self.path,json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                data=json.dumps({"choices":[{"message":{"content":json.dumps(actions.pop(0),ensure_ascii=False)}}]}).encode()
                self.send_response(200);self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        env={"AGENT_MODEL_BASE_URL":f"http://127.0.0.1:{server.server_port}/v1","AGENT_MODEL_NAME":"contract-test"}
        run=core.Agent(self.store,product.SPEC,lambda:core.Model(env)).run(self.mission,"model")
        self.assertEqual(run["state"],"completed")
        self.assertEqual(run["engine"],"model")
        self.assertEqual(received[0][0],"/v1/chat/completions")
        self.assertTrue(all(r[1]["model"]=="contract-test" for r in received))

    def test_compatible_provider_thinking_block_not_persisted(self):
        model=core.Model({"AGENT_MODEL_BASE_URL":"http://127.0.0.1:1/v1","AGENT_MODEL_NAME":"test"})
        payload={"choices":[{"finish_reason":"stop","message":{"content":'<think>private reasoning</think>\n```json\n{"action":"recall","arguments":{}}\n```'}}]}
        with patch(MODULE+".transport.completion",return_value=payload):
            result=model.next([],10)
        self.assertEqual(result,{"action":"recall","arguments":{}})
        self.assertNotIn("private reasoning",json.dumps(result))

    def test_model_truncation_classified(self):
        model=core.Model({"AGENT_MODEL_BASE_URL":"http://127.0.0.1:1/v1","AGENT_MODEL_NAME":"test"})
        payload={"choices":[{"finish_reason":"length","message":{"content":""}}]}
        with patch(MODULE+".transport.completion",return_value=payload):
            with self.assertRaisesRegex(RuntimeError,"truncated"):
                model.next([],10)

    def test_provider_filter_classified(self):
        model=core.Model({"AGENT_MODEL_BASE_URL":"http://127.0.0.1:1/v1","AGENT_MODEL_NAME":"test"})
        with patch(MODULE+".transport.completion",return_value={"input_sensitive":True}):
            with self.assertRaisesRegex(RuntimeError,"filtered"):
                model.next([],10)

    def test_invalid_schedule_engine_rejected(self):
        with self.assertRaises(ValueError):
            self.store.add_schedule(self.mission,"arbitrary",60)

    def test_structured_model_actions_render_as_readable_text(self):
        self.seed()
        run=self.agent.run(self.mission)
        report=run["report"]
        report["actions"]=[{"claim":"Confirm the actual route","evidence_ids":[report["evidence_ids"][0]]}]
        rendered=core.markdown(report)
        self.assertIn("- Confirm the actual route [",rendered)
        self.assertNotIn("{'claim':",rendered)

    def test_malformed_model_response_recovers_within_step_budget(self):
        self.seed()
        outer=self
        rows=self.store.search(countries=self.mission["countries"],topics=self.mission["topics"])[:1]
        actions=[{"action":"read_evidence","arguments":{"id":rows[0]["id"]}}, {"action":"finish","arguments":{"report":product.demo_report(self.mission,rows,[])}}]
        class MalformedOnce:
            count=0
            def next(self,messages,timeout):
                self.count+=1
                if self.count==1:raise ValueError("model_invalid_action_json")
                return actions.pop(0)
        run=core.Agent(self.store,product.SPEC,MalformedOnce).run(self.mission,"model")
        self.assertEqual(run["state"],"completed")
        self.assertEqual(run["steps"][0]["action"],"invalid_model_response")
        self.assertIn("error",run["steps"][0]["observation"])


class WebTests(unittest.TestCase):
    def test_http_api_auth_origin_run_save_reopen(self):
        # Stop the server before removing its workspace (Windows locks open databases).
        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as cleanup:
            store=core.Store(temp);store.import_evidence(FIXTURES)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
            env={**os.environ,"AGENT_UI_TOKEN":"contract-test-token-at-least-24-chars"}
            proc=subprocess.Popen([sys.executable,"-m",MODULE,"--workspace",temp,"serve","--port",str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            def stop():
                proc.terminate()
                try: proc.communicate(timeout=4)
                except subprocess.TimeoutExpired: proc.kill();proc.communicate()
            cleanup.callback(stop)
            base=f"http://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    with urlopen(base+"/health",timeout=.3) as r: self.assertEqual(r.status,200)
                    break
                except OSError: time.sleep(.03)
            else: self.fail("server did not start")
            with self.assertRaises(HTTPError) as error:
                urlopen(base+"/api/state")
            self.assertEqual(error.exception.code,401)
            headers={"Authorization":"Bearer "+env["AGENT_UI_TOKEN"],"Content-Type":"application/json"}
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base+"/api/runs",data=b'{}',headers={**headers,"Origin":"https://attacker.example"}))
            self.assertEqual(error.exception.code,403)
            body=json.dumps({"mission":product.SPEC["starter"],"engine":"demo"}).encode()
            with urlopen(Request(base+"/api/runs",data=body,headers=headers)) as r: rid=json.load(r)["id"]
            for _ in range(100):
                run=store.get_run(rid)
                if run["state"] in ("completed","failed"):break
                time.sleep(.03)
            self.assertEqual(run["state"],"completed")
            with urlopen(Request(base+"/api/state",headers=headers)) as r: state=json.load(r)
            self.assertEqual(state["runs"][0]["id"],rid)
            self.assertNotIn("messages",state["runs"][0])
            with urlopen(base) as r:self.assertIn(b'RESEARCH BRIEF',r.read())


if __name__=="__main__":
    unittest.main()
