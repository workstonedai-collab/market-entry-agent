"""Explicit private project facts and scoped historical research; no model writes."""
from datetime import datetime, timezone
import json
import re
import uuid


def stamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result.replace(tzinfo=result.tzinfo or timezone.utc).astimezone(timezone.utc)


def project_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value):
        raise ValueError("project_id requires 1..64 letters, digits, dots, underscores or hyphens")
    return value


def initialize(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS project_runs(
      run_id TEXT PRIMARY KEY, product TEXT, project_id TEXT, created TEXT);
    CREATE INDEX IF NOT EXISTS project_runs_scope ON project_runs(product,project_id,created);
    CREATE TABLE IF NOT EXISTS project_facts(
      id TEXT PRIMARY KEY, product TEXT, project_id TEXT, key TEXT, value TEXT,
      created TEXT, expires_at TEXT, state TEXT, supersedes TEXT);
    CREATE INDEX IF NOT EXISTS project_facts_scope ON project_facts(product,project_id,key,state);
    """)
    # Older missions may already carry an optional project_id. Never infer a company.
    rows = db.execute("SELECT id,product,mission,created FROM runs WHERE id NOT IN (SELECT run_id FROM project_runs)").fetchall()
    for row in rows:
        mission = json.loads(row["mission"])
        if mission.get("project_id"):
            try:
                project_id(mission["project_id"])
            except ValueError:
                continue
            db.execute("INSERT OR IGNORE INTO project_runs VALUES(?,?,?,?)",
                       (row["id"], row["product"], mission["project_id"], row["created"]))


class ProjectMemory:
    def __init__(self, store, product):
        self.store, self.product = store, product

    def set(self, project, key, value, expires_at=None):
        project_id(project)
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_\-\u4e00-\u9fff]{1,64}", key):
            raise ValueError("Memory key requires 1..64 letters, digits, underscores or hyphens")
        if not isinstance(value, str) or not value.strip() or len(value) > 4000:
            raise ValueError("Memory value requires 1..4000 characters")
        if expires_at is not None and not isinstance(expires_at, str):
            raise ValueError("expires_at must be an ISO date/time string")
        if expires_at:
            stamp(expires_at)
        created = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        identifier = uuid.uuid4().hex[:24]
        with self.store.tasks() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT id,value,expires_at FROM project_facts WHERE product=? AND project_id=? AND key=? AND state='active'",
                             (self.product, project, key)).fetchone()
            if old and old["value"] == value and old["expires_at"] == expires_at:
                return {"id": old["id"], "unchanged": True}
            retained = db.execute("SELECT expires_at FROM project_facts WHERE product=? AND project_id=? AND state='active'",
                                  (self.product, project)).fetchall()
            count = sum(not row[0] or stamp(row[0]) > datetime.now(timezone.utc) for row in retained)
            if not old and count >= 40:
                raise ValueError("Project memory supports at most 40 active facts")
            db.execute("UPDATE project_facts SET state='superseded' WHERE product=? AND project_id=? AND key=? AND state='active'",
                       (self.product, project, key))
            db.execute("INSERT INTO project_facts VALUES(?,?,?,?,?,?,?,?,?)",
                       (identifier, self.product, project, key, value, created, expires_at, "active", old["id"] if old else None))
        return {"id": identifier, "supersedes": old["id"] if old else None, "source_kind": "operator_input"}

    def facts(self, project, as_of=None):
        project_id(project)
        cutoff = stamp(as_of) if as_of else datetime.now(timezone.utc)
        with self.store.tasks() as db:
            # Reconstruct what was recorded at a historical cutoff, without future revisions.
            rows = db.execute("SELECT * FROM project_facts WHERE product=? AND project_id=? ORDER BY created DESC,rowid DESC",
                              (self.product, project)).fetchall()
        selected = {}
        for row in rows:
            if stamp(row["created"]) > cutoff or row["key"] in selected:
                continue
            selected[row["key"]] = dict(row)
        return [{**row, "source_kind": "operator_input"} for row in selected.values()
                if row["state"] != "deleted" and (not row["expires_at"] or stamp(row["expires_at"]) > cutoff)][:40]

    def forget(self, project, key):
        project_id(project)
        with self.store.tasks() as db:
            # Scrub all fact revisions; old task snapshots/reports are separate records.
            count = db.execute("DELETE FROM project_facts WHERE product=? AND project_id=? AND key=?",
                               (self.product, project, key)).rowcount
        return {"removed_fact_revisions": count, "note": "Saved reports and frozen run snapshots are retained separately."}

    def recall(self, mission, exclude=None):
        project = mission.get("project_id")
        cutoff = stamp(mission["as_of"]) if mission.get("as_of") else None
        with self.store.tasks() as db:
            if project:
                project_id(project)
                query = "SELECT r.id,r.mission,r.report,r.created FROM runs r JOIN project_runs p ON p.run_id=r.id WHERE r.state='completed' AND r.product=? AND p.project_id=?"
                parameters = [self.product, project]
            else:
                query = "SELECT id,mission,report,created FROM runs WHERE state='completed' AND product=?"
                parameters = [self.product]
            if cutoff:
                # Run timestamps are UTC ISO strings; future analyses are not historical evidence.
                query += " AND " + ("r.created" if project else "created") + "<=?"
                parameters.append(cutoff.isoformat())
            query += " ORDER BY " + ("r.created DESC,r.rowid DESC" if project else "created DESC,rowid DESC") + " LIMIT 100"
            rows = db.execute(query, parameters).fetchall()
        previous = []
        for row in rows:
            if row["id"] == exclude:
                continue
            prior = json.loads(row["mission"])
            if not project and self._legacy_identity(prior) != self._legacy_identity(mission):
                continue
            report = json.loads(row["report"])
            previous.append({"id": row["id"], "question": prior["question"], "summary": report["summary"][:1200],
                             "evidence_ids": report["evidence_ids"], "created": row["created"],
                             "synthetic": report.get("synthetic", False), "kind": "previous_analysis"})
            if len(previous) == 5:
                break
        from .continuity import ResearchMemory
        return {"project_id": project, "previous": previous,
                "research_memory": ResearchMemory(self.store,self.product).recall(mission),
                "facts": self.facts(project, mission.get("as_of")) if project else [],
                "boundary": "Current mission input takes precedence. Operator facts and previous analysis are not independent source evidence."}

    @staticmethod
    def _legacy_identity(mission):
        result = dict(mission)
        result["question"] = re.sub(r"[\W_]+", "", result.get("question", "").casefold())
        return result
