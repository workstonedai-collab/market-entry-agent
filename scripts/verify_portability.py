"""Exercise the installed agent through real CLI and loopback HTTP boundaries.

Uses synthetic fixtures, an isolated Unicode workspace, and no model credentials.
"""
from pathlib import Path
import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, ProxyHandler, build_opener

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
        server = subprocess.Popen(
            [sys.executable, "-X", "utf8=0", "-m", module, "--workspace", str(workspace), "serve", "--port", str(port)],
            cwd=ROOT, env=server_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    with http.open(base + "/health", timeout=1) as response:
                        health = json.load(response)
                    break
                except OSError as exc:
                    if server.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("Local web server did not become ready (" + type(exc).__name__ + ": " + str(exc) + ")") from None
                    time.sleep(.1)
            assert health["version"] == metadata["version"]
            with http.open(base + "/", timeout=5) as response:
                assert b"RESEARCH BRIEF" in response.read()
            headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
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
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
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
