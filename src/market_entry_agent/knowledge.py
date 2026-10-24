"""Private project collections. Originals are authoritative; lexical indexes rebuildable."""
import base64
import hashlib
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path

from .memory import project_id


def token_text(value):
    words = re.findall(r'[\w-]+', value.lower())
    return ' '.join(part for word in words for part in
                    ([word[i:i+2] for i in range(len(word)-1)] if re.fullmatch(r'[\u4e00-\u9fff]{2,}', word) else [word]))


def text(value, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value)>limit:
        raise ValueError('Expected nonempty bounded text')
    return value.strip()


class Knowledge:
    def __init__(self, store, product):
        self.store, self.product = store, product
        with store.tasks() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS kb_collections(id TEXT PRIMARY KEY,product TEXT,project TEXT,name TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS kb_documents(id TEXT PRIMARY KEY,collection_id TEXT,filename TEXT,title TEXT,metadata TEXT,created REAL,deleted INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS kb_versions(id TEXT PRIMARY KEY,document_id TEXT,checksum TEXT,blob TEXT,created REAL,active INTEGER,metadata TEXT);
            CREATE TABLE IF NOT EXISTS kb_chunks(id TEXT PRIMARY KEY,version_id TEXT,body TEXT,location TEXT,tokens TEXT);
            CREATE TABLE IF NOT EXISTS kb_jobs(id TEXT PRIMARY KEY,collection_id TEXT,payload TEXT,state TEXT,error TEXT,version_id TEXT,lease REAL DEFAULT 0,updated REAL);
            ''')
            try:db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(id UNINDEXED,tokens)')
            except sqlite3.OperationalError:pass

    def collection(self, project, cid):
        project_id(project)
        with self.store.tasks() as db:
            row=db.execute('SELECT * FROM kb_collections WHERE id=? AND product=? AND project=?',(cid,self.product,project)).fetchone()
        if not row:raise ValueError('Knowledge collection outside this project/product')
        return dict(row)

    def create(self, project, name):
        project_id(project); name=text(name)
        cid='collection-'+uuid.uuid4().hex[:20]
        with self.store.tasks() as db:db.execute('INSERT INTO kb_collections VALUES(?,?,?,?,?)',(cid,self.product,project,name,time.time()))
        return self.collection(project,cid)

    def list(self, project):
        project_id(project)
        with self.store.tasks() as db:
            rows=db.execute('SELECT * FROM kb_collections WHERE product=? AND project=? ORDER BY created',(self.product,project)).fetchall()
        return [dict(r,documents=self.documents(project,r['id'])) for r in rows]

    def documents(self, project, cid):
        self.collection(project,cid)
        with self.store.tasks() as db:
            rows=db.execute('SELECT d.*,v.id version_id,v.checksum,v.created version_created,(SELECT count(*) FROM kb_chunks WHERE version_id=v.id) chunks FROM kb_documents d JOIN kb_versions v ON v.document_id=d.id WHERE d.collection_id=? AND d.deleted=0 AND v.active=1 ORDER BY d.created',(cid,)).fetchall()
        return [dict(r,metadata=json.loads(r['metadata'])) for r in rows]

    def queue(self, project, cid, filename, raw, metadata, document_id=None):
        self.collection(project,cid)
        filename=text(filename,240)
        # Never use an uploaded path as a local path; generated IDs own storage names.
        suffix=Path(filename.replace('\\','/')).suffix.lower()
        if suffix not in ('.txt','.md','.csv','.tsv','.pdf','.docx','.xlsx','.pptx'):raise ValueError('Unsupported document format')
        if not isinstance(raw,bytes) or not 0<len(raw)<=8_000_000:raise ValueError('Document must contain 1..8000000 bytes')
        if not isinstance(metadata,dict):raise ValueError('Document metadata must be an object')
        title=text(metadata.get('title') or filename,500)
        for field in ('countries','topics'):
            values=metadata.get(field)
            if not isinstance(values,list) or not 1<=len(values)<=30 or any(not isinstance(x,str) or not x.strip() or len(x)>100 for x in values):raise ValueError('Document requires bounded countries and topics')
        published=metadata.get('published_at')
        if published:
            from datetime import datetime
            datetime.fromisoformat(text(published,60).replace('Z','+00:00'))
        if document_id and not any(d['id']==document_id for d in self.documents(project,cid)):raise ValueError('Replacement document outside collection')
        jid='import-'+uuid.uuid4().hex
        root=self.store.workspace/'knowledge'/'uploads';root.mkdir(parents=True,exist_ok=True,mode=0o700)
        upload=root/(jid+suffix);upload.write_bytes(raw)
        payload={'filename':filename,'suffix':suffix,'metadata':dict(title=title,countries=metadata['countries'],topics=metadata['topics'],published_at=published),'document_id':document_id,'project':project}
        try:
            with self.store.tasks() as db:db.execute('INSERT INTO kb_jobs VALUES(?,?,?,?,?,?,?,?)',(jid,cid,json.dumps(payload,ensure_ascii=False),'queued',None,None,0,time.time()))
        except Exception:
            committed=True
            upload.unlink(missing_ok=True);raise
        return self.job(project,jid)

    def job(self, project, jid):
        with self.store.tasks() as db:row=db.execute('SELECT * FROM kb_jobs WHERE id=?',(jid,)).fetchone()
        if not row:raise ValueError('Unknown import job')
        self.collection(project,row['collection_id'])
        value=dict(row);payload=json.loads(value.pop('payload'));value.pop('lease',None)
        return dict(value,filename=payload['filename'],document_id=payload.get('document_id'))

    def jobs(self, project):
        project_id(project)
        with self.store.tasks() as db:ids=[r[0] for r in db.execute('SELECT j.id FROM kb_jobs j JOIN kb_collections c ON c.id=j.collection_id WHERE c.product=? AND c.project=? ORDER BY updated DESC LIMIT 100',(self.product,project))]
        return [self.job(project,jid) for jid in ids]

    def process(self, project, jid):
        job=self.job(project,jid)
        with self.store.tasks() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM kb_jobs WHERE id=?',(jid,)).fetchone()
            if row['state']=='completed':return self.job(project,jid)
            if row['lease']>time.time():raise ValueError('Import already has an active worker')
            db.execute("UPDATE kb_jobs SET state='processing',error=NULL,lease=?,updated=? WHERE id=?",(time.time()+120,time.time(),jid))
            payload=json.loads(row['payload'])
        upload=self.store.workspace/'knowledge'/'uploads'/(jid+payload['suffix'])
        committed=False;blob=None
        try:
            from .documents import extract
            raw,parts=extract(upload)
            if not parts or len(parts)>100:raise ValueError('Document needs 1..100 readable extraction parts; OCR is not implied')
            checksum=hashlib.sha256(raw).hexdigest()
            meta=dict(payload['metadata'],extraction_limit='PDF: pages 1–40 only; scanned/image content is not OCR. Office: converted text offsets, not certified page/cell/slide positions. Tables preserve row ranges. Large documents may need splitting.');cid=job['collection_id']
            did=payload.get('document_id') or 'document-'+hashlib.sha256((cid+payload['filename']).encode()).hexdigest()[:24]
            vid='version-'+hashlib.sha256((did+checksum+json.dumps(meta,sort_keys=True)).encode()).hexdigest()[:32]
            originals=self.store.workspace/'knowledge'/'originals';originals.mkdir(parents=True,exist_ok=True,mode=0o700)
            blob=vid+payload['suffix'];(originals/blob).write_bytes(raw)
            chunks=[]
            for body,location in parts:
                for offset in range(0,len(body),1600):
                    excerpt=body[offset:offset+1600]
                    if not excerpt.strip():continue
                    eid='kb-'+hashlib.sha256((vid+str(len(chunks))).encode()).hexdigest()[:32]
                    loc=dict(location,chunk_offset=offset)
                    chunks.append((eid,vid,excerpt,json.dumps(loc,ensure_ascii=False),token_text(meta['title']+' '+excerpt)))
            if not chunks or len(chunks)>1500:raise ValueError('Document has no readable text or exceeds chunk budget')
            with self.store.tasks() as db:
                # A deletion during extraction cannot resurrect private material.
                existing=db.execute('SELECT deleted FROM kb_documents WHERE id=?',(did,)).fetchone()
                if existing and existing['deleted']:raise ValueError('Document was deleted; import under a new filename')
                db.execute('INSERT OR IGNORE INTO kb_documents VALUES(?,?,?,?,?,?,0)',(did,cid,payload['filename'],meta['title'],json.dumps(meta,ensure_ascii=False),time.time()))
                db.execute('UPDATE kb_documents SET title=?,metadata=? WHERE id=?',(meta['title'],json.dumps(meta,ensure_ascii=False),did))
                db.execute('UPDATE kb_versions SET active=0 WHERE document_id=?',(did,))
                db.execute('INSERT INTO kb_versions VALUES(?,?,?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET active=1',(vid,did,checksum,blob,time.time(),json.dumps(meta,ensure_ascii=False)))
                db.executemany('INSERT OR IGNORE INTO kb_chunks VALUES(?,?,?,?,?)',chunks)
                try:
                    db.execute('DELETE FROM kb_fts WHERE id IN (SELECT id FROM kb_chunks WHERE version_id=?)',(vid,))
                    db.executemany('INSERT INTO kb_fts VALUES(?,?)',[(r[0],r[4]) for r in chunks])
                except sqlite3.OperationalError:pass
                db.execute("UPDATE kb_jobs SET state='completed',version_id=?,lease=0,updated=? WHERE id=?",(vid,time.time(),jid))
            upload.unlink(missing_ok=True)
        except Exception as exc:
            if blob and not committed:(self.store.workspace/'knowledge'/'originals'/blob).unlink(missing_ok=True)
            error=str(exc)[:180] if isinstance(exc,(ValueError,UnicodeError)) else 'document_processing_'+type(exc).__name__
            with self.store.tasks() as db:db.execute("UPDATE kb_jobs SET state='failed',error=?,lease=0,updated=? WHERE id=?",(error,time.time(),jid))
        return self.job(project,jid)

    def pin(self, project, collections):
        if not isinstance(collections,list) or len(collections)>8 or any(not isinstance(x,str) for x in collections):raise ValueError('Select at most eight knowledge collections')
        versions=[]
        for cid in dict.fromkeys(collections):
            versions.extend(d['version_id'] for d in self.documents(project,cid))
        return {'project':project,'collections':collections,'versions':versions}

    def _rows(self, pin):
        if not pin or not pin.get('collections'):return []
        for cid in pin['collections']:self.collection(pin['project'],cid)
        with self.store.tasks() as db:
            rows=db.execute('SELECT ch.*,v.document_id,v.checksum,v.created,c.id collection_id,d.title,v.metadata FROM kb_chunks ch JOIN kb_versions v ON v.id=ch.version_id JOIN kb_documents d ON d.id=v.document_id JOIN kb_collections c ON c.id=d.collection_id WHERE c.product=? AND c.project=? AND d.deleted=0',(self.product,pin['project'])).fetchall()
        return [dict(r) for r in rows if r['version_id'] in pin['versions'] and r['collection_id'] in pin['collections']]

    def evidence(self,row):
        meta=json.loads(row['metadata'])
        return dict(id=row['id'],title=meta['title'],url='document://'+row['document_id']+'/'+row['version_id'],body=row['body'],countries=meta['countries'],topics=meta['topics'],published_at=meta.get('published_at'),observed_at=__import__('datetime').datetime.fromtimestamp(row['created'],__import__('datetime').timezone.utc).isoformat(),status='source_claim',synthetic=False,event_key=row['document_id'],retrieval_kind='document_text',visibility='private',document_location=json.loads(row['location']),content_sha256=row['checksum'],collection_id=row['collection_id'],document_version=row['version_id'],extraction_limit=meta.get('extraction_limit'))

    def search(self, pin, query='', limit=12):
        rows=self._rows(pin);terms=set(token_text(query).split());ranks={}
        if terms:
            try:
                with self.store.tasks() as db:
                    found=db.execute('SELECT id,bm25(kb_fts) score FROM kb_fts WHERE kb_fts MATCH ?',(' OR '.join('"'+x.replace('"','""')+'"' for x in sorted(terms)),)).fetchall()
                ranks={r['id']:-r['score'] for r in found}
            except sqlite3.OperationalError:pass
        scored=[]
        for row in rows:
            overlap=len(terms.intersection(row['tokens'].split()))
            if terms and not overlap:continue
            scored.append((overlap,ranks.get(row['id'],0),row['created'],row['id'],row))
        scored.sort(key=lambda x:x[:4],reverse=True)
        return [dict(self.evidence(r[-1]),retrieval_score=r[0],body=r[-1]['body'][:400]) for r in scored[:max(1,min(20,int(limit)))]]

    def read(self, pin, eid):
        row=next((r for r in self._rows(pin) if r['id']==eid),None)
        if not row:raise ValueError('Document evidence outside selected project/collection, or deleted')
        return self.evidence(row)

    def read_internal(self, eid):
        # Host-only report assembly; model/API callers must supply an authorized pin.
        with self.store.tasks() as db:
            r=db.execute('SELECT c.project,c.id collection_id,v.id version_id FROM kb_chunks ch JOIN kb_versions v ON ch.version_id=v.id JOIN kb_documents d ON d.id=v.document_id JOIN kb_collections c ON c.id=d.collection_id WHERE ch.id=? AND c.product=? AND d.deleted=0',(eid,self.product)).fetchone()
        if not r:raise ValueError('Document evidence unavailable')
        return self.read({'project':r['project'],'collections':[r['collection_id']],'versions':[r['version_id']]},eid)

    def original(self, project, cid, version):
        self.collection(project,cid)
        with self.store.tasks() as db:r=db.execute('SELECT v.blob FROM kb_versions v JOIN kb_documents d ON d.id=v.document_id WHERE v.id=? AND d.collection_id=? AND d.deleted=0',(version,cid)).fetchone()
        if not r:raise ValueError('Original outside collection or deleted')
        return (self.store.workspace/'knowledge'/'originals'/r['blob']).read_bytes()

    def delete(self, project, cid, did):
        self.collection(project,cid)
        blobs=[]
        with self.store.tasks() as db:
            row=db.execute('SELECT id FROM kb_documents WHERE id=? AND collection_id=?',(did,cid)).fetchone()
            if not row:raise ValueError('Document outside collection')
            versions=db.execute('SELECT id,blob FROM kb_versions WHERE document_id=?',(did,)).fetchall()
            for v in versions:
                try:db.execute('DELETE FROM kb_fts WHERE id IN (SELECT id FROM kb_chunks WHERE version_id=?)',(v['id'],))
                except sqlite3.OperationalError:pass
                db.execute('DELETE FROM kb_chunks WHERE version_id=?',(v['id'],));blobs.append(v['blob'])
            db.execute('UPDATE kb_documents SET deleted=1,metadata=? WHERE id=?',('{}',did))
        for blob in blobs:(self.store.workspace/'knowledge'/'originals'/blob).unlink(missing_ok=True)
        return {'deleted':did,'note':'Future retrieval and originals removed. Saved reports, task excerpts, learned skills and exported copies have separate retention.'}

    def rebuild(self, project):
        project_id(project)
        with self.store.tasks() as db:
            rows=db.execute('SELECT ch.id,ch.tokens FROM kb_chunks ch JOIN kb_versions v ON v.id=ch.version_id JOIN kb_documents d ON d.id=v.document_id JOIN kb_collections c ON c.id=d.collection_id WHERE c.product=? AND c.project=? AND d.deleted=0',(self.product,project)).fetchall()
            try:
                for row in rows:
                    db.execute('DELETE FROM kb_fts WHERE id=?',(row['id'],));db.execute('INSERT INTO kb_fts VALUES(?,?)',tuple(row))
                backend='sqlite-fts5-bm25+overlap'
            except sqlite3.OperationalError:backend='lexical-overlap-fallback'
        return {'indexed_chunks':len(rows),'backend':backend,'model_calls':0}
