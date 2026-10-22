"""Private versioned business records. Public evidence and private project state stay separate."""
from datetime import datetime, timezone
import hashlib
import json
import re
from .memory import project_id, stamp


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()[:24]


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', value):
        raise ValueError('Record ID requires 1..64 letters, digits, dots, underscores or hyphens')
    return value


def text(value, limit=3000, optional=False):
    if not isinstance(value, str) or len(value) > limit or (not optional and not value.strip()):
        raise ValueError('Expected bounded nonempty text')
    return value.strip()


def strings(value, limit=20):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError('Expected a bounded list')
    return list(dict.fromkeys(text(x, 128) for x in value))


def choice(value, options):
    if value not in options:
        raise ValueError('Expected one of: ' + ', '.join(map(str, options)))
    return value


def fields(value, allowed):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError('Unsupported record fields')


def date(value):
    return stamp(text(value, 64)).isoformat()


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS business_records(
      product TEXT, project TEXT, kind TEXT, id TEXT, revision INTEGER,
      data TEXT, origin TEXT, updated TEXT,
      PRIMARY KEY(product,project,kind,id,revision));
    CREATE INDEX IF NOT EXISTS business_scope ON business_records(product,project,kind,id,revision);
    ''')


class Records:
    def __init__(self, store, product):
        self.store, self.product = store, product

    def list(self, db, project, kind):
        project_id(project); identifier(kind)
        rows = db.execute('''SELECT b.* FROM business_records b WHERE product=? AND project=? AND kind=?
          AND revision=(SELECT MAX(c.revision) FROM business_records c
          WHERE c.product=b.product AND c.project=b.project AND c.kind=b.kind AND c.id=b.id)
          ORDER BY updated,id''', (self.product, project, kind)).fetchall()
        return [self.unpack(r) for r in rows]

    @staticmethod
    def unpack(row):
        return {**{k: row[k] for k in ('id', 'revision', 'origin', 'updated')}, 'data': json.loads(row['data'])}

    def get(self, db, project, kind, rid):
        project_id(project); identifier(kind); identifier(rid)
        row = db.execute('SELECT * FROM business_records WHERE product=? AND project=? AND kind=? AND id=? ORDER BY revision DESC LIMIT 1',
                         (self.product, project, kind, rid)).fetchone()
        return self.unpack(row) if row else None

    def save(self, db, project, kind, rid, data, expected=None, origin='operator'):
        old = self.get(db, project, kind, rid)
        if old and old['data'] == data:
            return dict(old, unchanged=True)
        revision = old['revision'] if old else 0
        if expected != revision:
            raise ValueError('revision_conflict: reload this record before updating')
        if len(encoded(data)) > 24000:
            raise ValueError('Business record exceeds 24000 characters')
        if not old and len(self.list(db, project, kind)) >= (100 if kind in self.kinds else 5000):
            raise ValueError('Project record capacity reached')
        updated = datetime.now(timezone.utc).isoformat(timespec='microseconds')
        db.execute('INSERT INTO business_records VALUES(?,?,?,?,?,?,?,?)',
                   (self.product, project, kind, rid, revision+1, encoded(data), origin, updated))
        return {'id': rid, 'revision': revision+1, 'data': data, 'origin': origin, 'updated': updated}

    def history(self, project, kind, rid):
        project_id(project); identifier(kind); identifier(rid)
        with self.store.tasks() as db:
            rows = db.execute('SELECT * FROM business_records WHERE product=? AND project=? AND kind=? AND id=? ORDER BY revision DESC LIMIT 100',
                              (self.product, project, kind, rid)).fetchall()
        return [self.unpack(r) for r in rows]

    def references(self, ids, countries=None, topics=None, as_of=None):
        from .countries import scope_keys
        ids = strings(ids)
        for eid in ids:
            row = self.store.read(eid)
            if row.get('retrieval_kind') == 'search_snippet':
                raise ValueError('Discovery snippets cannot support business records; read a source page')
            if as_of and (not row.get('published_at') or stamp(row['published_at']) > stamp(as_of)):
                raise ValueError('Historical project update cites unknown or later publication')
            if countries and not scope_keys(countries).intersection(scope_keys(row['countries'])):
                raise ValueError('Business evidence outside country scope')
            if topics and not set(topics).intersection(row['topics']):
                raise ValueError('Business evidence outside topic scope')
        return ids

    def save_command(self, project, command, origin='operator'):
        project_id(project)
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            return self.change(db, project, command, origin)

    def state(self, project):
        project_id(project)
        with self.store.tasks() as db:
            return self.state_in(db, project)

    def snapshot(self, project):
        # Freeze business context on the first attempt, just like private project memory.
        data = self.state(project)
        return {'product': self.product, 'project_id': project,
                'records': {kind: data[kind] for kind in self.context_kinds},
                'notice': 'PRIVATE PROJECT DATA. Source claims and operator inputs are not independently verified. Current mission takes precedence.'}

    def validate_report(self, report, run):
        update = report.get('project_update')
        if update is None:
            return
        if run['mission'].get('as_of'):
            raise ValueError('Historical reports cannot mutate the live project; replay in an isolated workspace')
        if not run['mission'].get('project_id'):
            raise ValueError('project_update requires an explicit project_id')
        fields(update, ['commands'])
        commands = update.get('commands')
        if not isinstance(commands, list) or not 1 <= len(commands) <= 12:
            raise ValueError('project_update requires 1..12 typed commands')
        read = set(report['evidence_ids'])
        unique = set()
        for command in commands:
            fields(command, ['kind','id','data','expected_revision'])
            if not isinstance(command.get('data'), dict):
                raise ValueError('Project command data must be an object')
            key = (command.get('kind'), command.get('id'))
            if key in unique:
                raise ValueError('One command per business record per report')
            unique.add(key)
            if command.get('kind') not in self.agent_kinds:
                raise ValueError('Model cannot change operator profile, exposure, feedback or progress')
            if not set(command.get('data', {}).get('evidence_ids', [])).issubset(read):
                raise ValueError('Project update cites evidence not read in this report')
            self.normalize(command['kind'], command['data'], run['mission'].get('as_of'))
        # Validate dependencies, revision expectations and cross-command references in a rolled-back transaction.
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('SAVEPOINT validate_project_update')
            try:
                for command in commands:
                    self.change(db, run['mission']['project_id'], command, 'agent_proposal', run)
            except ValueError as exc:
                if not str(exc).startswith(('revision_conflict:', 'Option must use the current profile revision', 'operator_state_protected:')):
                    raise
            finally:
                db.execute('ROLLBACK TO validate_project_update')
                db.execute('RELEASE validate_project_update')

    def accept_report(self, db, run, report):
        update = report.get('project_update')
        if not update:
            return None
        project = run['mission']['project_id']
        receipt = self.get(db, project, 'report_receipt', run['id'])
        if receipt:
            return receipt['data']
        frozen = self.store.meta(run['id']).get('project_state', {})
        if 'records' not in frozen:
            value = {'state':'needs_rebase','reason':'This older run has no frozen business state; create a new task for project updates.'}
            self.save(db, project, 'report_receipt', run['id'], value, 0, 'runtime')
            return value
        db.execute('SAVEPOINT apply_project_update')
        try:
            results = [self.change(db, project, c, 'agent_proposal', run) for c in update['commands']]
            value = {'state': 'applied', 'records': [{k: r[k] for k in ('id', 'revision')} for r in results]}
        except ValueError as exc:
            db.execute('ROLLBACK TO apply_project_update')
            # A user edit between model response and commit never discards the successful report.
            value = {'state': 'needs_rebase', 'reason': str(exc)[:160], 'note': 'Report retained; project data was not overwritten.'}
        finally:
            db.execute('RELEASE apply_project_update')
        self.save(db, project, 'report_receipt', run['id'], value, 0, 'runtime')
        return value

    def change(self, db, project, command, origin, run=None):
        fields(command, ['kind', 'id', 'data', 'expected_revision'])
        if type(command.get('expected_revision', 0)) is not int or command.get('expected_revision', 0) < 0:
            raise ValueError('expected_revision requires a nonnegative integer')
        kind = choice(command.get('kind'), self.kinds)
        rid = identifier(command.get('id'))
        normalized = self.normalize(kind, command.get('data'), run['mission'].get('as_of') if run else None)
        self.validate_links(db, project, kind, rid, normalized, origin)
        if run:
            from .countries import scope_keys
            if normalized.get('countries') and not scope_keys(normalized['countries']).issubset(scope_keys(run['mission']['countries'])):
                raise ValueError('Project update extends mission country scope')
            if normalized.get('topics') and not set(normalized['topics']).issubset(run['mission']['topics']):
                raise ValueError('Project update extends mission topic scope')
        result = self.save(db, project, kind, rid, normalized, command.get('expected_revision', 0), origin)
        return result

    def validate_links(self, db, project, kind, rid, data, origin):
        pass


def brief(snapshot, kind=None, rid=None):
    records = snapshot.get('records', {})
    if kind is not None:
        if kind not in records:
            raise ValueError('Unknown business kind in this frozen project')
        rows = records[kind]
        if rid is not None:
            found = next((r for r in rows if r['id'] == rid), None)
            if not found:
                raise ValueError('Unknown record in this frozen project')
            return {'kind':kind, 'record':found}
        records = {kind:rows}
    return {'project_id':snapshot.get('project_id'), 'notice':snapshot.get('notice'),
            'records':{k:[{'id':r['id'],'revision':r['revision'],'label':str(r['data'].get('name') or r['data'].get('title') or r['data'].get('product') or r['data'].get('statement') or r['data'].get('goal') or r['id'])[:200],
                         'status':r['data'].get('status') or r['data'].get('stage')} for r in rows] for k,rows in records.items()},
            'read_more':'Call project_state with kind and id for a complete frozen record.'}
