"""Exercise the installed agent through real CLI and loopback HTTP boundaries.

Uses synthetic fixtures, an isolated Unicode workspace, and no model credentials.
"""
from pathlib import Path
import argparse
import json
import importlib
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, ProxyHandler, build_opener
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]


def verify():
    metadata = json.loads((ROOT / "agent.json").read_text(encoding="utf-8"))
    module = metadata["python_module"]
    mission = json.loads((ROOT / "examples/mission.json").read_text(encoding="utf-8"))
    env = {key: value for key, value in os.environ.items() if not key.startswith("AGENT_")}
    # A legacy redirected stream must not prevent Unicode JSON or serving the UI.
    env.update(PYTHONUTF8="0", PYTHONIOENCODING="cp1252", NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
    # Loopback verification must not use host or system-configured HTTP proxies.
    http = build_opener(ProxyHandler({}))
    checks = []
    with tempfile.TemporaryDirectory(prefix="field-agent-portable-") as temporary:
        workspace = Path(temporary) / "研究 work space"
        exports = Path(temporary) / "报告 exports"

        def cli(*args):
            result = subprocess.run(
                [sys.executable, "-X", "utf8=0", "-m", module, "--workspace", str(workspace), *args],
                env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40,
            )
            if result.returncode:
                raise RuntimeError("CLI verification failed: " + args[0] + " (exit " + str(result.returncode) + ")")
            return json.loads(result.stdout.decode("utf-8"))

        country = cli("country", "越南")
        assert country["baseline"]["code"] == "VNM"
        assert cli("country-list")["coverage"]["economies"] == 215
        assert cli("compare", "越南", "阿联酋")["same_basis"] is False
        checks.append("unicode_country_data_and_mixed_coverage")

        run = cli("demo")
        assert run["state"] == "completed" and run["report"]["synthetic"]
        reopened = cli("show", run["id"])
        assert reopened["report"] == run["report"]
        assert cli("resume", run["id"])["steps"] == reopened["steps"]
        checks.append("cli_saved_report_reopen_and_idempotent_resume")

        for suffix in ("json", "md"):
            target = exports / ("研究报告." + suffix)
            cli("export", run["id"], "--output", str(target))
            text = target.read_text(encoding="utf-8")
            assert run["report"]["title"] in text
        checks.append("utf8_markdown_and_json_exports")

        assert len(cli("skills")["skills"]) >= 2
        assert any(tool["name"] == "read_result" for tool in cli("tools")["tools"])
        cli("memory-set", "cli-project", "产品", "虚构设备")
        assert cli("memory", "cli-project")["facts"][0]["value"] == "虚构设备"
        project_run = cli("run", str(ROOT / "examples/project-mission.json"), "--engine", "demo", "--project", "cli-project")
        assert project_run["state"] == "completed" and project_run["report"]["project_id"] == "cli-project"
        receipt = cli("usage", project_run["id"])
        assert receipt["summary"]["tracking_available"] and receipt["summary"]["model_calls"] == 0
        cli("memory-forget", "cli-project", "产品")
        assert cli("memory", "cli-project")["facts"] == []
        checks.append("project_memory_skills_and_usage_cli")
        business = json.loads((ROOT / "examples/public-project-case.json").read_text(encoding="utf-8"))["operator_commands"][0]
        command_file = Path(temporary) / "项目记录.json"
        command_file.write_text(json.dumps(business,ensure_ascii=False),encoding="utf-8")
        created = cli("project-save","cli-business",str(command_file))
        assert cli("project","cli-business")[business["kind"]][0]["id"] == created["id"]
        assert len(cli("project-history","cli-business",business["kind"],created["id"])["history"]) == 1
        cli("project-check","cli-business")
        checks.append("typed_business_cli_save_reopen_history_check")

        schedule = cli("schedule", str(ROOT / "examples/mission.json"), "--engine", "demo", "--interval", "60")
        due = cli("worker", "--once")
        assert len(due) == 1 and due[0]["state"] == "completed"
        assert cli("worker", "--once") == []
        cli("pause", schedule["id"])
        checks.append("explicit_worker_and_persisted_schedule")

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = "http://127.0.0.1:" + str(port)
        token = "portable-test-only-token-at-least-24"
        server_env = dict(env, AGENT_UI_TOKEN=token)
        server_log = tempfile.TemporaryFile()
        server = subprocess.Popen(
            [sys.executable, "-X", "utf8=0", "-m", module, "--workspace", str(workspace), "serve", "--port", str(port)],
            cwd=ROOT, env=server_env, stdout=server_log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 45
            while True:
                try:
                    with http.open(base + "/health", timeout=5) as response:
                        health = json.load(response)
                    break
                except OSError as exc:
                    if server.poll() is not None or time.monotonic() >= deadline:
                        server_log.seek(0)
                        diagnostic = server_log.read(2000).decode("utf-8", "replace")
                        raise RuntimeError("Local web server did not become ready (exit=" + str(server.poll()) + ", " + type(exc).__name__ + ": " + str(exc) + "). Startup: " + diagnostic) from None
                    time.sleep(.1)
            assert health["version"] == metadata["version"]
            with http.open(base + "/", timeout=5) as response:
                assert b"RESEARCH BRIEF" in response.read()
                assert "script-src 'self' 'unsafe-inline'" in response.headers["Content-Security-Policy"]
            headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
            with http.open(Request(base + "/api/source-health", headers=headers), timeout=5) as response:
                source_health = json.load(response)
                assert source_health["scope"] == "registered_sources_only"
                assert source_health["internet_coverage_complete"] is False
            checks.append("authenticated_source_refresh_receipts")
            with http.open(Request(base + "/api/country?code=VNM", headers=headers), timeout=5) as response:
                assert json.load(response)["baseline"]["code"] == "VNM"
            body = json.dumps({"mission": mission, "engine": "demo"}, ensure_ascii=False).encode("utf-8")
            with http.open(Request(base + "/api/runs", data=body, headers=headers), timeout=5) as response:
                assert response.status == 202
                run_id = json.load(response)["id"]
            deadline = time.monotonic() + 15
            while True:
                with http.open(Request(base + "/api/runs/" + run_id, headers=headers), timeout=5) as response:
                    saved = json.load(response)
                if saved["state"] in ("completed", "failed"):
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("HTTP demo did not finish")
                time.sleep(.1)
            assert saved["state"] == "completed" and saved["report"]["synthetic"]
            assert cli("show", run_id)["report"] == saved["report"]
            checks.append("http_task_country_query_and_saved_result")
            def post(path, value):
                data = json.dumps(value, ensure_ascii=False).encode("utf-8")
                with http.open(Request(base + path, data=data, headers=headers), timeout=5) as response:
                    return json.load(response)

            created = post("/api/project", {"project_id":"http-business","command":business})
            with http.open(Request(base+"/api/project?project_id=http-business",headers=headers),timeout=5) as response:
                assert json.load(response)[business["kind"]][0]["id"] == created["id"]
            with http.open(Request(base+"/api/project/history?project_id=http-business&kind="+business["kind"]+"&id="+created["id"],headers=headers),timeout=5) as response:
                assert len(json.load(response)["history"]) == 1
            post("/api/project/check", {"project_id":"http-business"})
            with http.open(base+"/workflow-ui.js",timeout=5) as response:
                assert b"renderProject" in response.read()
            for unsafe in [Request(base+"/api/project?project_id=http-business"),Request(base+"/api/project?project_id=http-business",headers=dict(headers,Origin="https://example.org"))]:
                try:
                    http.open(unsafe,timeout=5)
                    raise AssertionError("Private business endpoint accepted unauthorised request")
                except HTTPError as exc:
                    assert exc.code in (401,403)
            checks.append("typed_business_http_auth_origin_save_reopen_and_local_check")
            post("/api/memory", {"project_id": "http-project", "key": "产品", "value": "虚构 HTTP 资料"})
            with http.open(Request(base + "/api/memory?project_id=http-project", headers=headers), timeout=5) as response:
                assert json.load(response)["facts"][0]["value"] == "虚构 HTTP 资料"
            post("/api/memory", {"operation": "forget", "project_id": "http-project", "key": "产品"})
            private = importlib.import_module(module + ".core").Store(workspace)
            waiting = private.create_run(metadata["id"], mission, "demo")
            assert post("/api/control", {"id": waiting, "state": "paused"})["state"] == "paused"
            post("/api/resume", {"id": waiting})
            until = time.monotonic() + 15
            while private.get_run(waiting)["state"] not in ("completed", "failed"):
                if time.monotonic() >= until:
                    raise RuntimeError("Paused HTTP task did not resume")
                time.sleep(.1)
            assert private.get_run(waiting)["state"] == "completed"
            cancelled = private.create_run(metadata["id"], mission, "demo")
            assert post("/api/control", {"id": cancelled, "state": "cancelled"})["state"] == "cancelled"
            assert cli("resume", cancelled)["state"] == "cancelled"
            checks.append("http_project_memory_pause_resume_and_cancel")

        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            server_log.close()
        # TemporaryDirectory cleanup after process exit also checks released file handles.
    return {"product": metadata["id"], "version": metadata["version"], "platform": platform.system(),
            "python": platform.python_version(), "checks": checks + ["workspace_cleanup_after_server_exit"],
            "model_calls": 0, "external_requests": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
