from __future__ import annotations

import argparse
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import urlsplit, parse_qs

from . import __version__
from .core import Agent, Store, atomic_json, fetch_feed, load_json, markdown, validate_mission
from .product import SPEC
from .memory import ProjectMemory
from .skills import snapshot, catalog as skill_catalog
from .core import REGISTRY
from .workflow import Workflow
from .source_health import overview as source_overview


class AgentHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # The bound address is sufficient; reverse DNS must not delay local startup.
        TCPServer.server_bind(self)
        self.server_name = self.server_address[0]
        self.server_port = self.server_address[1]


def public_run(run):
    return {k: v for k, v in run.items() if k not in ("messages", "lease_until")}


def tick(store, spec=SPEC):
    results = []
    for schedule in store.due():
        error=None
        try:
            run = Agent(store, spec).run(json.loads(schedule["mission"]), schedule["engine"])
            results.append({"schedule": schedule["id"], "run": run["id"], "state": run["state"]})
            if run['state']!='completed':error=run.get('error') or run['state']
        except Exception as exc:
            error=type(exc).__name__
            results.append({'schedule':schedule['id'],'state':'failed','error':error})
        finally:
            store.schedule_complete(schedule["id"],error)
    from .lifecycle import worker_tick
    extra=worker_tick(store,spec['id'])
    results.extend({'monitor':r} for r in extra['monitors'] if r.get('state')!='not_due_or_not_confirmed')
    results.extend({'learning':r} for r in extra['learning'] if r.get('state') not in ('disabled','daily_budget_wait'))
    return results


def serve(store, host, port):
    token = os.environ.get("AGENT_UI_TOKEN", "")
    if host not in ("127.0.0.1", "localhost", "::1") and len(token) < 24:
        raise ValueError("Non-loopback serving requires AGENT_UI_TOKEN with at least 24 characters")
    allowed = {"127.0.0.1", "localhost", "::1"}
    allowed.update(filter(None, os.environ.get("AGENT_UI_ALLOWED_HOSTS", "").split(",")))
    asset = Path(__file__).with_name("web.html").read_text(encoding="utf-8").replace("__AGENT_VERSION__",__version__).encode("utf-8")
    project_asset = Path(__file__).with_name("workflow-ui.js").read_bytes()
    threads = threading.BoundedSemaphore(2)
    available_skills = skill_catalog(snapshot())
    from .lifecycle import Lifecycle
    lifecycle=Lifecycle(store,SPEC['id'])
    def background(work):
        if not threads.acquire(blocking=False):raise ValueError('Two workspace workers are active; retry shortly')
        def perform():
            try:work()
            finally:threads.release()
        threading.Thread(target=perform,daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No questions, tokens or evidence bodies in access logs.

        def reply(self, status, payload, content_type="application/json; charset=utf-8"):
            data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def check(self, api=True):
            host_header = self.headers.get("Host", "")
            try:
                hostname = urlsplit("http://" + host_header).hostname
            except ValueError:
                hostname = None
            if hostname not in allowed:
                self.reply(403, {"error": "Host not allowed"})
                return False
            origin = self.headers.get("Origin")
            if origin:
                parsed = urlsplit(origin)
                if parsed.netloc != host_header or parsed.scheme not in ("http", "https"):
                    self.reply(403, {"error": "Cross-origin request denied"})
                    return False
            if api and token and not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.reply(401, {"error": "Enter your workspace token"})
                return False
            return True

        def do_GET(self):
            path = urlsplit(self.path).path
            if not self.check(api=path.startswith("/api/")):
                return
            if path == "/":
                return self.reply(200, asset, "text/html; charset=utf-8")
            if path == "/workflow-ui.js":
                return self.reply(200, project_asset, "text/javascript; charset=utf-8")
            if path == '/lifecycle-ui.js':
                return self.reply(200,Path(__file__).with_name('lifecycle-ui.js').read_bytes(),'text/javascript; charset=utf-8')
            if path.startswith(('/api/knowledge/','/api/monitors/','/api/learning/','/api/desk/','/api/feedback/')):
                try:
                    _,_,area,action=path.split('/')
                    if action not in ('list','jobs','search','read','original','preview','history','status','export','overview','cited','suggestions','usage'):raise ValueError('This operation requires POST')
                    body={k:v[0] for k,v in parse_qs(urlsplit(self.path).query).items()}
                    if 'collection_ids' in body:body['collection_ids']=body['collection_ids'].split(',')
                    result=lifecycle.dispatch(area,action,body)
                    return self.reply(200,result,'application/octet-stream' if isinstance(result,bytes) else 'application/json; charset=utf-8')
                except (ValueError,KeyError,TypeError) as exc:return self.reply(400,{'error':str(exc)[:180]})
            if path == "/health":
                return self.reply(200, {"status": "ok", "product": SPEC["id"], "version": __version__})
            if path == "/api/research":
                try:
                    from .notebook import snapshot as notebook_snapshot
                    rid=parse_qs(urlsplit(self.path).query).get("run_id",[""])[0]
                    from .depth import snapshot as branch_snapshot
                    return self.reply(200,dict(notebook_snapshot(store,rid),branches=branch_snapshot(store,rid)))
                except ValueError as exc:return self.reply(400,{"error":str(exc)})
            if path == "/api/source-health":
                return self.reply(200,source_overview(store))
            if path == "/api/project":
                try:
                    project = parse_qs(urlsplit(self.path).query).get("project_id", [""])[0]
                    return self.reply(200, Workflow(store, SPEC["id"]).state(project))
                except ValueError as exc:
                    return self.reply(400, {"error": str(exc)})
            if path == "/api/project/history":
                try:
                    query = parse_qs(urlsplit(self.path).query)
                    return self.reply(200, {"history":Workflow(store,SPEC["id"]).history(query.get("project_id",[""])[0],query.get("kind",[""])[0],query.get("id",[""])[0])})
                except ValueError as exc:
                    return self.reply(400, {"error":str(exc)})
            if path == "/api/task-modes":
                from .task_modes import catalog
                return self.reply(200,{"task_modes":catalog(SPEC["id"])})
            if path == "/api/skills":
                project=parse_qs(urlsplit(self.path).query).get('project_id',[None])[0]
                return self.reply(200, {"skills": skill_catalog(snapshot(store,SPEC['id'],project)) if project else available_skills})
            if path in ('/api/memory/notes','/api/memory/notes/history'):
                try:
                    from .continuity import ResearchMemory
                    query=parse_qs(urlsplit(self.path).query);project=query.get('project_id',[''])[0]
                    memory=ResearchMemory(store,SPEC['id'])
                    if path.endswith('/history'):return self.reply(200,{'history':memory.history(project,query.get('key',[''])[0])})
                    return self.reply(200,{'notes':memory.list(project,query.get('as_of',[None])[0])})
                except ValueError as exc:return self.reply(400,{'error':str(exc)})
            if path == "/api/memory":
                try:
                    project = parse_qs(urlsplit(self.path).query).get("project_id", [""])[0]
                    return self.reply(200, {"project_id": project, "facts": ProjectMemory(store, SPEC["id"]).facts(project)})
                except ValueError as exc:
                    return self.reply(400, {"error": str(exc)})
            if path == "/api/countries":
                from .countries import catalog
                return self.reply(200, catalog())
            if path == "/api/country":
                from .countries import dashboard
                try:
                    country = parse_qs(urlsplit(self.path).query).get("code", [""])[0]
                    return self.reply(200, dashboard(store, country))
                except ValueError as exc:
                    return self.reply(400, {"error": str(exc)})
            if path == "/api/compare":
                from .countries import compare
                try:
                    codes = parse_qs(urlsplit(self.path).query).get("countries", [""])[0].split(",")
                    return self.reply(200, compare(codes))
                except ValueError as exc:
                    return self.reply(400, {"error": str(exc)})
            if path == "/api/state":
                return self.reply(200, {"product": {k: SPEC[k] for k in ("id", "name", "tagline", "accent", "starter")},
                    "runs": [public_run(r) for r in store.list_runs()], "evidence": store.export_evidence()["records"],
                    "outbox": store.outbox(), "schedules": store.schedules(), "sources": store.sources(),
                    "source_health": source_overview(store),
                    "model_configured": bool(os.environ.get("AGENT_MODEL_BASE_URL") and os.environ.get("AGENT_MODEL_NAME"))})
            if path.startswith("/api/runs/"):
                try:
                    return self.reply(200, public_run(store.get_run(path.rsplit("/", 1)[-1])))
                except ValueError:
                    return self.reply(404, {"error": "Run not found"})
            self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if not self.check():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > (10_800_000 if self.path=="/api/knowledge/import" else 100_000) or self.headers.get_content_type() != "application/json":
                    return self.reply(400, {"error": "Expected bounded application/json body"})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Request body must be an object")
                if self.path.startswith(('/api/knowledge/','/api/monitors/','/api/learning/','/api/desk/','/api/feedback/')):
                    _,_,area,action=self.path.split('/')
                    result=lifecycle.dispatch(area,action,body,background)
                    return self.reply(200,result,'application/octet-stream' if isinstance(result,bytes) else 'application/json; charset=utf-8')
                if self.path == "/api/project":
                    return self.reply(200, Workflow(store,SPEC["id"]).save_command(body["project_id"],body["command"]))
                if self.path == "/api/project/check":
                    return self.reply(200, Workflow(store,SPEC["id"]).check(body["project_id"]))
                if self.path == '/api/memory/notes':
                    from .continuity import ResearchMemory
                    memory=ResearchMemory(store,SPEC['id'])
                    if body.get('operation')=='forget':return self.reply(200,memory.forget(body['project_id'],body['key']))
                    if body.get('operation','save')!='save':raise ValueError('Unknown typed memory operation')
                    return self.reply(200,memory.save(body['project_id'],body['key'],body['data'],body['expected_revision']))
                if self.path == "/api/memory":
                    memory = ProjectMemory(store, SPEC["id"])
                    if body.get("operation") == "forget":
                        return self.reply(200, memory.forget(body["project_id"], body["key"]))
                    if body.get("operation", "set") != "set":
                        raise ValueError("Unknown memory operation")
                    return self.reply(200, memory.set(body["project_id"], body["key"], body["value"], body.get("expires_at")))
                if self.path == "/api/control":
                    run = store.get_run(body["id"])
                    if run["product"] != SPEC["id"]:
                        raise ValueError("Run belongs to another product")
                    return self.reply(200, store.control(body["id"], body["state"]))
                if self.path in ("/api/runs", "/api/resume"):
                    if self.path == "/api/runs":
                        mission = validate_mission(body.get("mission"))
                        engine = body.get("engine", "demo")
                        if engine not in ("demo", "model"):
                            raise ValueError("Unknown engine")
                        rid = None
                    else:
                        rid = body["id"]
                        run = store.get_run(rid)
                        if run["product"] != SPEC["id"]:
                            raise ValueError("Run belongs to another product")
                        if run["state"] in ("completed", "cancelled"):
                            return self.reply(200, {"id": rid})
                        mission, engine = run["mission"], run["engine"]
                    if not threads.acquire(blocking=False):
                        return self.reply(429, {"error": "Two workers are active; try again shortly"})
                    rid = rid or store.create_run(SPEC["id"], mission, engine)
                    allow_paused = self.path == "/api/resume"
                    def work():
                        try:
                            Agent(store, SPEC).run(resume=rid, allow_paused=allow_paused)
                        except Exception:
                            pass  # Lease conflicts do not overwrite the owner's state.
                        finally:
                            threads.release()
                    threading.Thread(target=work, daemon=True).start()
                    return self.reply(202, {"id": rid})
                if self.path == "/api/schedules":
                    return self.reply(201, {"id": store.add_schedule(body["mission"], body.get("engine", "demo"), int(body.get("interval_seconds", 3600)))})
                if self.path == "/api/schedules/pause":
                    with store.tasks() as db:
                        db.execute("UPDATE schedule SET active=0 WHERE id=?", (body["id"],))
                    return self.reply(200, {"paused": body["id"]})
                if self.path == "/api/approve":
                    store.approve(body["id"])
                    return self.reply(200, {"approved": body["id"]})
                self.reply(404, {"error": "Not found"})
            except (ValueError, KeyError, TypeError) as exc:
                self.reply(400, {"error": str(exc)[:180]})

    server = AgentHTTPServer((host, port), Handler)
    try:
        label=SPEC["name"]
        try:
            label.encode(getattr(sys.stdout,"encoding",None) or "utf-8")
        except UnicodeEncodeError:
            label=SPEC["id"]
        print(f"{label}: http://{host}:{server.server_port} (local workspace)", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None):
    # Keep redirected JSON and diagnostics readable on legacy Windows code pages.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=SPEC["tagline"])
    parser.add_argument("--workspace", default=f"~/.field-agents/{SPEC['id']}", help="Private state directory; use a separate one for each customer")
    parser.add_argument("--evidence-db", default=None, help="Optional shared public evidence database")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Import synthetic fixtures and execute a deterministic demonstration")
    demo.add_argument("--project", help="Explicit private project ID")
    for command in ("pause-run", "cancel", "usage"):
        sub.add_parser(command).add_argument("id")
    project = sub.add_parser("project", help="Open a private business project")
    project.add_argument("project")
    setting = sub.add_parser("project-save", help="Apply a typed JSON business command with optimistic revision checks")
    setting.add_argument("project"); setting.add_argument("file")
    checking = sub.add_parser("project-check", help="Evaluate saved event/exposure or assumption changes; no network calls")
    checking.add_argument("project")
    history = sub.add_parser("project-history", help="Read up to 100 record revisions")
    history.add_argument("project"); history.add_argument("kind"); history.add_argument("id")
    typed=sub.add_parser('memory-notes',help='Read typed research memory for an explicit project')
    typed.add_argument('project');typed.add_argument('--as-of')
    typed=sub.add_parser('memory-note-save',help='Save/correct a typed operator record from a JSON command')
    typed.add_argument('project');typed.add_argument('file')
    typed=sub.add_parser('memory-note-history');typed.add_argument('project');typed.add_argument('key')
    typed=sub.add_parser('memory-note-forget');typed.add_argument('project');typed.add_argument('key')
    sub.add_parser("task-modes",help="List product research task contracts")
    sub.add_parser("skills", help="List configured document skill metadata")
    sub.add_parser("tools", help="Show public tool schemas and execution policies")
    memory = sub.add_parser("memory", help="Read explicit private project facts")
    memory.add_argument("project")
    memory.add_argument("--as-of")
    setting = sub.add_parser("memory-set", help="Save or correct one operator-owned project fact")
    setting.add_argument("project"); setting.add_argument("key"); setting.add_argument("value")
    setting.add_argument("--expires-at")
    forgetting = sub.add_parser("memory-forget", help="Remove all revisions of a project fact; saved runs are separate")
    forgetting.add_argument("project"); forgetting.add_argument("key")
    ingest = sub.add_parser("import", help="Import a field-evidence/v1 JSON bundle")
    ingest.add_argument("file")
    sources = sub.add_parser("sources", help="Register operator-managed RSS feeds")
    sources.add_argument("file")
    fetch = sub.add_parser("fetch", help="Fetch one registered feed")
    fetch.add_argument("id")
    page = sub.add_parser("fetch-page", help="Fetch one registered HTML page")
    page.add_argument("id")
    run = sub.add_parser("run", help="Run a mission")
    run.add_argument("mission")
    run.add_argument("--task-mode",help="Optional product task contract; see task-modes")
    run.add_argument("--project")
    run.add_argument("--skill", action="append", default=[])
    run.add_argument("--engine", choices=("demo", "model"), default="model")
    resume = sub.add_parser("resume", help="Resume a failed or expired run without repeating saved steps")
    resume.add_argument("id")
    show = sub.add_parser("show")
    show.add_argument("id")
    research=sub.add_parser("research-state",help="Read saved questions and evidence fragments for one run")
    research.add_argument("id")
    document=sub.add_parser("import-document",help="Import an operator-selected PDF/CSV/TSV/TXT/MD with provenance")
    document.add_argument("file");document.add_argument("metadata",help="JSON metadata; public defaults to false")
    sub.add_parser("list")
    sub.add_parser("country-list", help="List bundled country coverage and scores")
    country = sub.add_parser("country", help="Country dashboard: baseline, public evidence and saved tasks")
    country.add_argument("country")
    comparison = sub.add_parser("compare", help="Compare one to five countries without merging different formulas into a ranking")
    comparison.add_argument("countries", nargs="+")
    plan = sub.add_parser("research-plan", help="Show structured research lenses and action-plan contracts")
    plan.add_argument("mission")
    export = sub.add_parser("export")
    export.add_argument("id")
    export.add_argument("--output", required=True)
    bundle = sub.add_parser("export-evidence")
    bundle.add_argument("--output", required=True)
    sub.add_parser("outbox", help="Local pending/approved notifications; never sends externally")
    approve = sub.add_parser("approve")
    approve.add_argument("id")
    schedule = sub.add_parser("schedule")
    schedule.add_argument("mission")
    schedule.add_argument("--engine", choices=("demo", "model"), default="model")
    schedule.add_argument("--interval", type=int, default=3600)
    pause = sub.add_parser("pause")
    pause.add_argument("id")
    sub.add_parser("schedules")
    worker = sub.add_parser("worker", help="Run due missions; operator must start this process")
    worker.add_argument("--once", action="store_true")
    mcp=sub.add_parser('mcp-serve',help='Opt-in MCP stdio adapter; read-only unless --allow-runs')
    mcp.add_argument('--allow-runs',action='store_true',help='Permit explicit task create/resume/control; model mode may incur charges')
    mcp.add_argument('--project',help='Restrict private project/task access to this explicit project ID')
    manage=sub.add_parser('manage',help='Private knowledge, confirmed monitoring and learning; see docs/continuous-research.md')
    manage.add_argument('area',choices=('knowledge','monitors','learning','desk','feedback'));manage.add_argument('action')
    manage.add_argument('--project',required=True);manage.add_argument('--data',help='JSON command file')
    manage.add_argument('--file',help='Knowledge import file; never interpreted as a command')
    manage.add_argument('--output',help='Explicit local export destination')
    ui = sub.add_parser("serve")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=SPEC["port"])
    args = parser.parse_args(argv)
    store = Store(args.workspace, args.evidence_db)
    package = Path(__file__).parent
    result = None
    try:
        if args.command=='mcp-serve':
            from .mcp import serve as mcp_serve
            mcp_serve(store,SPEC,args.allow_runs,args.project)
        elif args.command in ('memory-notes','memory-note-save','memory-note-history','memory-note-forget'):
            from .continuity import ResearchMemory
            memory=ResearchMemory(store,SPEC['id'])
            if args.command=='memory-notes':result={'notes':memory.list(args.project,args.as_of)}
            elif args.command=='memory-note-save':
                command=load_json(args.file);result=memory.save(args.project,command['key'],command['data'],command['expected_revision'])
            elif args.command=='memory-note-history':result={'history':memory.history(args.project,args.key)}
            else:result=memory.forget(args.project,args.key)
        elif args.command == "project":
            result = Workflow(store,SPEC["id"]).state(args.project)
        elif args.command == "project-save":
            result = Workflow(store,SPEC["id"]).save_command(args.project,load_json(args.file))
        elif args.command == "project-check":
            result = Workflow(store,SPEC["id"]).check(args.project)
        elif args.command == "project-history":
            result = {"history":Workflow(store,SPEC["id"]).history(args.project,args.kind,args.id)}
        elif args.command == "task-modes":
            from .task_modes import catalog
            result={"task_modes":catalog(SPEC["id"])}
        elif args.command == "skills":
            result = {"skills": skill_catalog(snapshot())}
        elif args.command == "tools":
            result = {"tools": REGISTRY.describe()}
        elif args.command == "memory":
            result = {"project_id": args.project, "facts": ProjectMemory(store, SPEC["id"]).facts(args.project, args.as_of)}
        elif args.command == "memory-set":
            result = ProjectMemory(store, SPEC["id"]).set(args.project, args.key, args.value, args.expires_at)
        elif args.command == "memory-forget":
            result = ProjectMemory(store, SPEC["id"]).forget(args.project, args.key)
        elif args.command in ("pause-run", "cancel"):
            existing = store.get_run(args.id)
            if existing["product"] != SPEC["id"]:
                raise ValueError("Run belongs to another product")
            result = store.control(args.id, "paused" if args.command == "pause-run" else "cancelled")
        elif args.command == "usage":
            result = {"id": args.id, "summary": store.get_run(args.id)["runtime"], "calls": store.call_receipts(args.id)}
        elif args.command == "country-list":
            from .countries import catalog
            result = catalog()
        elif args.command == "country":
            from .countries import dashboard
            result = dashboard(store, args.country)
        elif args.command == "compare":
            from .countries import compare
            result = compare(args.countries)
        elif args.command == "research-plan":
            from .research import plan
            result = plan(SPEC["id"], validate_mission(load_json(args.mission)))
        elif args.command == "demo":
            store.import_evidence(load_json(package / "data" / "demo-evidence.json"))
            mission = dict(SPEC["starter"])
            if args.project:
                mission["project_id"] = args.project
            result = public_run(Agent(store, SPEC).run(mission, "demo"))
        elif args.command == "import":
            result = store.import_evidence(load_json(args.file))
        elif args.command == "sources":
            result = store.register_sources(load_json(args.file))
        elif args.command == "fetch-page":
            from .net import fetch_page
            result = fetch_page(store, source_id=args.id)
        elif args.command == "fetch":
            result = fetch_feed(store, args.id)
        elif args.command == "run":
            mission = load_json(args.mission)
            if args.task_mode:
                mission["task_mode"]=args.task_mode
            if args.project:
                mission["project_id"] = args.project
            if args.skill:
                mission["skill_ids"] = args.skill
            result = public_run(Agent(store, SPEC).run(mission, args.engine))
        elif args.command == "resume":
            result = public_run(Agent(store, SPEC).run(resume=args.id))
        elif args.command == "show":
            result = public_run(store.get_run(args.id))
        elif args.command == "research-state":
            from .notebook import snapshot as notebook_snapshot
            from .depth import snapshot as branch_snapshot
            result=dict(notebook_snapshot(store,args.id),branches=branch_snapshot(store,args.id))
        elif args.command == "import-document":
            from .documents import ingest
            result=ingest(store,args.file,load_json(args.metadata))
        elif args.command == "list":
            result = [{k: r[k] for k in ("id", "state", "engine", "created", "error")} for r in store.list_runs()]
        elif args.command == "export":
            report = store.get_run(args.id)["report"]
            if not report:
                raise ValueError("Run has no completed report")
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.suffix.lower() == ".docx":
                from .office import export_docx
                result=export_docx(report,output)
            elif output.suffix == ".md":
                output.write_text(markdown(report), encoding="utf-8")
            else:
                atomic_json(output, report)
            if output.suffix.lower() != ".docx":
                result = {"saved": str(output)}
        elif args.command == "export-evidence":
            atomic_json(args.output, store.export_evidence())
            result = {"saved": args.output}
        elif args.command == "outbox":
            result = store.outbox()
        elif args.command == "approve":
            store.approve(args.id)
            result = {"approved": args.id}
        elif args.command == "schedule":
            result = {"id": store.add_schedule(load_json(args.mission), args.engine, args.interval)}
        elif args.command == "pause":
            with store.tasks() as db:
                db.execute("UPDATE schedule SET active=0 WHERE id=?", (args.id,))
            result = {"paused": args.id}
        elif args.command == "schedules":
            result = store.schedules()
        elif args.command == "worker":
            while True:
                print(json.dumps(tick(store), ensure_ascii=False), flush=True)
                if args.once:
                    break
                time.sleep(5)
        elif args.command == 'manage':
            from .lifecycle import Lifecycle
            body=load_json(args.data) if args.data else {}
            body['project_id']=args.project
            if args.file:
                import base64
                document=Path(args.file)
                if not document.is_file() or document.stat().st_size>8_000_000:raise ValueError('File unavailable or over 8 MB')
                body.update(filename=document.name,content_base64=base64.b64encode(document.read_bytes()).decode())
            result=Lifecycle(store,SPEC['id']).dispatch(args.area,args.action,body)
            if isinstance(result,bytes):
                if not args.output:raise ValueError('Binary/original/skill exports require --output')
                with Path(args.output).open('xb') as output:output.write(result)
                result={'output':args.output}
        elif args.command == "serve":
            serve(store, args.host, args.port)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if isinstance(result, dict) and result.get("state") == "failed":
                return 1
        return 0
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
