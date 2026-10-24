"""Additive private runtime metadata, call receipts, controls and owner fencing."""
import json
import time
import uuid


class RuntimeStore:
    def initialize_runtime(self):
        from .memory import initialize
        with self.tasks() as db:
            initialize(db)
            db.executescript("""
            CREATE TABLE IF NOT EXISTS run_meta(run_id TEXT PRIMARY KEY, payload TEXT);
            CREATE TABLE IF NOT EXISTS run_owners(run_id TEXT PRIMARY KEY, owner TEXT);
            CREATE TABLE IF NOT EXISTS step_inputs(run_id TEXT, seq INTEGER, arguments TEXT, tool_key TEXT, PRIMARY KEY(run_id,seq));
            CREATE TABLE IF NOT EXISTS model_calls(
              id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, attempt TEXT, step INTEGER,
              input_characters INTEGER, elapsed REAL, state TEXT, usage TEXT, context_stats TEXT);
            CREATE INDEX IF NOT EXISTS model_calls_run ON model_calls(run_id,id);
            """)

    def meta(self, rid):
        with self.tasks() as db:
            row = db.execute("SELECT payload FROM run_meta WHERE run_id=?", (rid,)).fetchone()
        return json.loads(row[0]) if row else {}

    def save_meta(self, rid, value, owner=None, seed=None):
        with self.tasks() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_owner(db, rid, owner)
            db.execute("INSERT OR REPLACE INTO run_meta VALUES(?,?)", (rid, json.dumps(value, ensure_ascii=False)))
            if seed is not None:
                db.execute("UPDATE runs SET messages=? WHERE id=?", (json.dumps(seed, ensure_ascii=False), rid))

    @staticmethod
    def require_owner(db, rid, owner):
        if owner:
            row = db.execute("SELECT owner FROM run_owners WHERE run_id=?", (rid,)).fetchone()
            if not row or row[0] != owner:
                raise RuntimeError("run_owner_changed")

    def control(self, rid, state):
        if state not in ("paused", "cancelled"):
            raise ValueError("Control must be paused or cancelled")
        with self.tasks() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM runs WHERE id=?", (rid,)).fetchone()
            if not row:
                raise ValueError("Unknown run")
            if row[0] in ("completed", "cancelled"):
                return {"id": rid, "state": row[0]}
            db.execute("UPDATE runs SET state=?,error=NULL WHERE id=?", (state, rid))
        return {"id": rid, "state": state, "note": "In-flight requests settle at the next safe boundary; no new tool will start."}

    def stopped(self, rid, owner=None):
        with self.tasks() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_owner(db, rid, owner)
            row = db.execute("SELECT state FROM runs WHERE id=?", (rid,)).fetchone()
        return row[0] if row and row[0] in ("paused", "cancelled") else None

    def release(self, rid, owner):
        with self.tasks() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT owner FROM run_owners WHERE run_id=?", (rid,)).fetchone()
            if row and row[0] == owner:
                db.execute("UPDATE runs SET lease_until=0 WHERE id=?", (rid,))

    def start_call(self, rid, attempt, seq, context_stats, owner):
        with self.tasks() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_owner(db, rid, owner)
            state = db.execute("SELECT state FROM runs WHERE id=?", (rid,)).fetchone()[0]
            if state in ("paused", "cancelled"):
                raise RuntimeError("run_" + state)
            cursor = db.execute("INSERT INTO model_calls(run_id,attempt,step,input_characters,elapsed,state,usage,context_stats) VALUES(?,?,?,?,?,?,?,?)",
                                (rid, attempt, seq, context_stats["context_characters"], 0, "in_flight", "{}", json.dumps(context_stats)))
            return cursor.lastrowid

    def end_call(self, cid, elapsed, state, usage):
        safe = {key: value for key, value in (usage if isinstance(usage, dict) else {}).items()
                if key in ("prompt_tokens", "completion_tokens", "total_tokens") and type(value) is int and value >= 0}
        with self.tasks() as db:
            db.execute("UPDATE model_calls SET elapsed=?,state=?,usage=? WHERE id=?", (max(0, elapsed), state, json.dumps(safe), cid))

    def runtime_summary(self, rid):
        with self.tasks() as db:
            rows = db.execute("SELECT input_characters,elapsed,state,usage,context_stats FROM model_calls WHERE run_id=? ORDER BY id", (rid,)).fetchall()
        usages = [json.loads(row["usage"]) for row in rows]
        total = {key: sum(u.get(key, 0) for u in usages) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
        meta = self.meta(rid)
        return {"tracking_available": bool(meta.get("initialized") or rows), "model_calls": len(rows), "failed_model_calls": sum(r["state"] not in ("success", "in_flight") for r in rows),
                "in_flight_or_interrupted_calls": sum(r["state"] == "in_flight" for r in rows),
                "reported_usage": total, "usage_complete": bool(rows) and not meta.get("legacy_history_unmetered") and all("total_tokens" in u for u in usages),
                "legacy_history_unmetered": bool(meta.get("legacy_history_unmetered")),
                "usage_note": "Only provider-reported token counts; missing usage and monetary charges are unknown.",
                "model_seconds": round(sum(row["elapsed"] for row in rows), 3),
                "peak_context_characters": max((row["input_characters"] for row in rows), default=0),
                "context_budget_chars": meta.get("context_budget_chars"),
                "skill_versions": {**{k: v["version"] for k, v in meta.get("loaded_skills", {}).items()}, **({"report-writing":meta["writing_skill"]["version"]} if meta.get("writing_skill") else {})},
                "model_format_repairs": meta.get("model_format_repairs",[]),
                "output_recovery": meta.get("output_recovery"),
                "integration_versions": ({meta['mcp_profile']['name']:meta['mcp_profile']['version']} if meta.get('mcp_profile') else {}),
                "budget_status": meta.get("budget_status", "within_attempt_budget")}

    def call_receipts(self, rid):
        self.get_run(rid)
        with self.tasks() as db:
            rows = db.execute("SELECT id,attempt,step,input_characters,elapsed,state,usage,context_stats FROM model_calls WHERE run_id=? ORDER BY id", (rid,)).fetchall()
        return [{**dict(row), "usage": json.loads(row["usage"]), "context_stats": json.loads(row["context_stats"])} for row in rows]
