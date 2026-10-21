"""Explicit public-query search and bounded page retrieval; no private context sent."""
import json
import os
import re
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

class TextPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'nav', 'footer', 'svg'):
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'nav', 'footer', 'svg'):
            self.hidden = max(0, self.hidden-1)
        if not self.hidden and tag in ('p','div','h1','h2','h3','li','tr','section','article'):
            self.parts.append('\n')
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
    def text(self):
        return '\n'.join(' '.join(line.split()) for line in ''.join(self.parts).splitlines() if line.strip())

def public_queries(mission):
    queries = mission.get('search_queries', [])
    if not isinstance(queries, list) or len(queries)>6 or not all(isinstance(q,str) and 0<len(q.strip())<=500 for q in queries):
        raise ValueError('search_queries must contain at most 6 explicit public queries of 1..500 characters')
    domains = mission.get('search_domains', [])
    if not isinstance(domains,list) or len(domains)>20 or not all(isinstance(d,str) and re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.[a-z]{2,}',d) for d in domains):
        raise ValueError('search_domains must be exact lower-case public host names')
    return queries

def cached(store, key, seconds):
    with store.evidence() as db:
        db.execute('CREATE TABLE IF NOT EXISTS retrieval_cache(key TEXT PRIMARY KEY, at REAL, payload TEXT)')
        row=db.execute('SELECT at,payload FROM retrieval_cache WHERE key=?',(key,)).fetchone()
    if row and time.time()-row[0]<seconds:
        return json.loads(row[1])

def cache(store,key,payload):
    with store.evidence() as db:
        db.execute('CREATE TABLE IF NOT EXISTS retrieval_cache(key TEXT PRIMARY KEY, at REAL, payload TEXT)')
        db.execute('INSERT OR REPLACE INTO retrieval_cache VALUES(?,?,?)',(key,time.time(),json.dumps(payload,ensure_ascii=False)))

def web_search(store, mission, index, timeout=30):
    from .core import digest
    queries=public_queries(mission)
    if type(index) is not int or not 0<=index<len(queries):
        raise ValueError('Select query_index from the mission public search_queries list (zero based)')
    query=queries[index].strip()
    domains=mission.get('search_domains',[])
    provider=os.environ.get('AGENT_SEARCH_PROVIDER','minimax')
    if provider!='minimax':
        raise ValueError('Supported search provider: minimax')
    key=os.environ.get('AGENT_SEARCH_API_KEY','')
    if not key:
        raise ValueError('Set AGENT_SEARCH_API_KEY for public web search')
    identity=digest({'provider':provider,'query':query,'domains':domains})
    payload=cached(store,'search:'+identity,3600)
    hit=payload is not None
    if not hit:
        # Fixed official service endpoint; no model-controlled credentials or URLs.
        request=Request('https://api.minimax.io/v1/coding_plan/search',data=json.dumps({'q':query}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
        try:
            with urlopen(request,timeout=min(timeout,40)) as response:
                raw=response.read(1_000_001)
            if len(raw)>1_000_000:
                raise ValueError('Search response exceeds byte budget')
            payload=json.loads(raw)
        except HTTPError as exc:
            raise ValueError(f'search_http_{exc.code}') from None
        except (URLError,TimeoutError,OSError):
            raise ValueError('search_network_or_timeout') from None
        if payload.get('base_resp',{}).get('status_code',0):
            raise ValueError('search_provider_error')
        if not isinstance(payload.get('organic'),list):
            raise ValueError('search_response_missing_organic')
        cache(store,'search:'+identity,payload)
    records=[]
    for result in payload['organic'][:10]:
        url=result.get('link',''); p=urlsplit(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password or (domains and p.hostname not in domains):
            continue
        if not result.get('snippet') or not result.get('title'):
            continue
        records.append({'title':result['title'][:1000],'body':result['snippet'][:6000],'url':url,
            'countries':mission['countries'],'topics':mission['topics'],'status':'source_claim',
            'retrieval_kind':'search_snippet','search_query':query,'search_provider':provider,
            'provider_date':result.get('date') or None,'published_at':None})
    store.import_evidence({'schema':'field-evidence/v1','records':records})
    ids=[digest({k:v for k,v in dict(r,synthetic=False,event_key=digest(r['url'])[:20]).items() if k not in ('id','observed_at')})[:24] for r in records]
    return {'query':query,'cached':hit,'results':[store.read(eid) for eid in ids],
        'limitation':'Search snippets only. Fetch and read relevant pages before factual conclusions. Provider dates are not verified publication dates.'}

def fetch_page(store, evidence_id=None, source_id=None, timeout=20):
    from .core import digest,fetch_public_https
    if source_id:
        source=next((s for s in store.sources() if s['id']==source_id and s.get('kind')=='page'),None)
        if not source:
            raise ValueError('Unknown registered page source')
        url=source['url']; hosts=source['allowed_hosts']
    else:
        source=store.read(evidence_id)
        if source.get('retrieval_kind')!='search_snippet':
            raise ValueError('Page retrieval requires a discovered search snippet or registered page source')
        url=source['url']; hosts=[urlsplit(url).hostname]
        registered=next((s for s in store.sources() if s.get('kind')=='page' and s['url']==url),None)
        if registered:
            source=registered; hosts=source['allowed_hosts']
    identity=digest({'url':url,'hosts':hosts,'countries':source['countries'],'topics':source['topics'],'published_at':source.get('published_at')})
    previous=cached(store,'page:'+identity,3600)
    if previous:
        return {'id':previous['id'],'cached':True,'retrieval_kind':'page_text'}
    if urlsplit(url).path.lower().endswith('.pdf'):
        raise ValueError('PDF extraction is not supported; register an HTML source or import licensed extracted text')
    raw=fetch_public_https(url,hosts,timeout=min(timeout,25))
    if b'%PDF'==raw[:4] or b'<' not in raw[:1000]:
        raise ValueError('Expected a readable HTML page')
    parser=TextPage(); parser.feed(raw.decode('utf-8',errors='replace'))
    body=parser.text()
    if len(body)<100:
        raise ValueError('Page has insufficient readable text; dynamic/blocked pages require another source')
    record={'title':source.get('title',source.get('id',url)), 'body':body[:28000], 'url':url,
        'countries':source['countries'],'topics':source['topics'],'status':'source_claim',
        'retrieval_kind':'page_text','published_at':source.get('published_at'),
        'content_sha256':__import__('hashlib').sha256(raw).hexdigest(),
        'text_truncated':len(body)>28000,'text_characters':len(body),
        'date_basis':'operator_registered' if source.get('published_at') else 'unknown'}
    store.import_evidence({'schema':'field-evidence/v1','records':[record]})
    record.update(synthetic=False,event_key=digest(url)[:20])
    eid=digest(record)[:24]
    cache(store,'page:'+identity,{'id':eid})
    return {'id':eid,'cached':False,'retrieval_kind':'page_text','text_truncated':record['text_truncated'],'text_characters':len(body)}
