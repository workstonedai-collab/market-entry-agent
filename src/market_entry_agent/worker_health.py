"""Observed worker heartbeats and tick completion, scoped to one private workspace."""
import os
import threading
import time
import uuid


def initialize(store):
    with store.tasks() as db:db.execute('CREATE TABLE IF NOT EXISTS worker_sessions(id TEXT PRIMARY KEY,product TEXT,pid INTEGER,started REAL,heartbeat REAL,tick_started REAL,tick_finished REAL,state TEXT,error TEXT)')


class WorkerSession:
    def __init__(self,store,product,interval=10):
        self.store,self.product=store,product;self.id=uuid.uuid4().hex;self.interval=interval;self.stop_event=threading.Event();self.thread=None

    def __enter__(self):
        initialize(self.store);stamp=time.time()
        with self.store.tasks() as db:db.execute('INSERT INTO worker_sessions VALUES(?,?,?,?,?,?,?, ?,NULL)',(self.id,self.product,os.getpid(),stamp,stamp,None,None,'idle'))
        self.thread=threading.Thread(target=self._pulse,daemon=True);self.thread.start();return self

    def _pulse(self):
        while not self.stop_event.wait(self.interval):
            try:
                with self.store.tasks() as db:db.execute('UPDATE worker_sessions SET heartbeat=? WHERE id=?',(time.time(),self.id))
            except Exception:pass  # A failed heartbeat becomes stale; it never claims a successful tick.

    def begin(self):
        with self.store.tasks() as db:db.execute("UPDATE worker_sessions SET heartbeat=?,tick_started=?,state='working',error=NULL WHERE id=?",(time.time(),time.time(),self.id))

    def finish(self,error=None):
        with self.store.tasks() as db:db.execute("UPDATE worker_sessions SET heartbeat=?,tick_finished=?,state=?,error=? WHERE id=?",(time.time(),time.time(),'error' if error else 'idle',error,self.id))

    def __exit__(self,exc_type,exc,tb):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=2)
        with self.store.tasks() as db:db.execute("UPDATE worker_sessions SET heartbeat=?,state='stopped',error=? WHERE id=?",(time.time(),exc_type.__name__ if exc_type else None,self.id))


def status(store,product,at=None):
    initialize(store);stamp=time.time() if at is None else at
    with store.tasks() as db:rows=db.execute('SELECT * FROM worker_sessions WHERE product=? ORDER BY started DESC LIMIT 10',(product,)).fetchall()
    values=[]
    for row in rows:
        value=dict(row);value['heartbeat_age_seconds']=max(0,stamp-row['heartbeat'])
        value['observed_state']='stopped' if row['state']=='stopped' else 'stale' if stamp-row['heartbeat']>45 else row['state']
        values.append(value)
    return {'sessions':values,'recently_active':any(v['observed_state'] in ('idle','working','error') for v in values),
            'scope':'Workspace worker heartbeat only; not proof of completed research or external delivery.'}
