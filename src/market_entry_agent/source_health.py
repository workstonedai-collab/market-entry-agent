"""Registered-source retrieval receipts. A cache hit never claims a new network refresh."""
from datetime import datetime, timedelta, timezone
import re


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS source_health(
      source_id TEXT PRIMARY KEY, last_attempt TEXT, last_success TEXT, last_failure TEXT,
      last_error TEXT, cache_hit INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0,
      failures INTEGER DEFAULT 0)''')


def record(store, source_id, success, cached=False, error=None):
    at = datetime.now(timezone.utc).isoformat()
    # Never persist exception bodies, request headers or credential-bearing URLs.
    code = error if isinstance(error, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,79}', error) else 'retrieval_failed'
    with store.evidence() as db:
        initialize(db)
        db.execute('INSERT OR IGNORE INTO source_health(source_id) VALUES(?)', (source_id,))
        db.execute('''UPDATE source_health SET last_attempt=?,cache_hit=?,attempts=attempts+1,
          failures=failures+?,last_success=CASE WHEN ? THEN ? ELSE last_success END,
          last_failure=CASE WHEN ? THEN ? ELSE last_failure END,
          last_error=CASE WHEN ? THEN ? ELSE last_error END WHERE source_id=?''',
          (at,int(cached),int(not success),int(success and not cached),at,int(not success),at,int(not success),code,source_id))


def retrieve(store, source_id, operation):
    try:
        result = operation()
    except Exception as exc:
        record(store, source_id, False, error=str(exc) if isinstance(exc, (ValueError, RuntimeError)) else None)
        raise
    record(store, source_id, True, cached=bool(result.get('cached',False)))
    return result


def overview(store, at=None):
    current = at or datetime.now(timezone.utc)
    rows=[]
    with store.evidence() as db:
        initialize(db)
        saved={r['source_id']:dict(r) for r in db.execute('SELECT * FROM source_health')}
    for source in store.sources():
        state=saved.get(source['id'],{})
        last=state.get('last_success')
        age=(current-datetime.fromisoformat(last)).total_seconds() if last else None
        hours=source.get('refresh_hours',24)
        if type(hours) not in (int,float) or not 1<=hours<=720:hours=24
        fresh='never_fetched' if age is None else 'fresh' if 0<=age<=hours*3600 else 'stale'
        failed=bool(state.get('last_failure') and state['last_failure']==state.get('last_attempt'))
        rows.append({'id':source['id'],'title':source.get('title',source['id']),'url':source['url'],
          'kind':source.get('kind','feed'),'countries':source['countries'],'topics':source['topics'],
          'last_attempt':state.get('last_attempt'),'last_success':last,'last_failure':state.get('last_failure'),
          'last_error':state.get('last_error'),'latest_attempt_failed':failed,'cached':bool(state.get('cache_hit')),
          'freshness':fresh,'refresh_hours':hours,'attempts':state.get('attempts',0),'failures':state.get('failures',0)})
    return {'checked_at':current.isoformat(),'scope':'registered_sources_only','internet_coverage_complete':False,
      'registered':len(rows),'fresh':sum(r['freshness']=='fresh' for r in rows),
      'stale':sum(r['freshness']=='stale' for r in rows),'never_fetched':sum(r['freshness']=='never_fetched' for r in rows),
      'latest_failed':sum(r['latest_attempt_failed'] for r in rows),'sources':rows}
