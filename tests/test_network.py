import importlib,io,json,os,tempfile,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core');net=importlib.import_module(MODULE+'.net');transport=importlib.import_module(MODULE+'.transport')
class NetworkTests(unittest.TestCase):
 def test_public_query_only_and_cache(self):
  with tempfile.TemporaryDirectory() as d:
   store=core.Store(d);mission={'search_queries':['site:imo.org shipping'],'context':'PRIVATE COMPANY SALES','countries':['Yemen'],'topics':['shipping']}
   body={'organic':[{'title':'Statement','link':'https://www.imo.org/a','snippet':'Source statement'}]}
   class Response(io.BytesIO):
    pass
   calls=[]
   def call(request,**kw):
    calls.append(json.loads(request.data));return Response(json.dumps(body).encode())
   with patch.dict(os.environ,{'AGENT_SEARCH_API_KEY':'test-only'}),patch.object(net,'urlopen',side_effect=call):
    first=net.web_search(store,mission,0);second=net.web_search(store,mission,0)
   self.assertEqual(calls,[{'q':'site:imo.org shipping'}]);self.assertTrue(second['cached']);self.assertEqual(first['results'][0]['retrieval_kind'],'search_snippet')
   self.assertNotIn('PRIVATE COMPANY',json.dumps(store.export_evidence()))
   with self.assertRaises(ValueError):net.web_search(store,mission,-1)
 def test_page_retrieval_and_cache(self):
  with tempfile.TemporaryDirectory() as d:
   store=core.Store(d);store.register_sources({'sources':[{'id':'page','kind':'page','title':'Official','url':'https://example.org/a','allowed_hosts':['example.org'],'countries':['Yemen'],'topics':['shipping'],'published_at':'2024-03-06'}]})
   with patch.object(core,'fetch_public_https',return_value=('<html><script>SECRET()</script><p>'+('Official statement. '*15)+'</p></html>').encode()) as fetch:
    one=net.fetch_page(store,source_id='page');two=net.fetch_page(store,source_id='page')
   row=store.read(one['id']);self.assertNotIn('SECRET',row['body']);self.assertEqual(row['retrieval_kind'],'page_text');self.assertEqual(fetch.call_count,1);self.assertTrue(two['cached'])
 def test_discovered_registered_page_inherits_explicit_date(self):
  with tempfile.TemporaryDirectory() as d:
   store=core.Store(d)
   row={'title':'Found','body':'Snippet','url':'https://example.org/a','countries':['Yemen'],'topics':['shipping'],'retrieval_kind':'search_snippet'}
   store.import_evidence({'schema':'field-evidence/v1','records':[row]});eid=store.export_evidence()['records'][0]['id']
   store.register_sources({'sources':[dict(row,id='registered',kind='page',allowed_hosts=['example.org'],published_at='2024-03-06')]})
   with patch.object(core,'fetch_public_https',return_value=('<p>'+('Evidence text. '*20)+'</p>').encode()):
    result=net.fetch_page(store,evidence_id=eid)
   record=store.read(result['id']);self.assertEqual(record['published_at'],'2024-03-06');self.assertTrue(core.Agent.in_time(record,{'as_of':'2024-03-07'}))
 def test_historical_filter_before_result_limit(self):
  with tempfile.TemporaryDirectory() as d:
   store=core.Store(d)
   records=[{'title':'shipping '+str(i),'body':'shipping evidence','url':'https://example.org/'+str(i),'countries':['Yemen'],'topics':['shipping'],'published_at':'2024-03-08' if i else '2024-03-06','observed_at':str(i).zfill(2)} for i in range(20)]
   store.import_evidence({'schema':'field-evidence/v1','records':records})
   rows=store.search('shipping',['Yemen'],['shipping'],predicate=lambda row:core.Agent.in_time(row,{'as_of':'2024-03-07'}))
   self.assertEqual(len(rows),1);self.assertEqual(rows[0]['published_at'],'2024-03-06')
 def test_historical_cutoff_excludes_unknown_and_future(self):
  mission={'as_of':'2024-03-07T23:59:59Z'}
  self.assertTrue(core.Agent.in_time({'published_at':'2024-03-06'},mission))
  self.assertFalse(core.Agent.in_time({'published_at':'2024-03-08'},mission))
  self.assertFalse(core.Agent.in_time({'published_at':None},mission))
 def test_atom_link_and_excerpt(self):
  with tempfile.TemporaryDirectory() as d:
   store=core.Store(d);store.register_sources({'sources':[{'id':'atom','url':'https://example.org/feed','allowed_hosts':['example.org'],'countries':['UK'],'topics':['trade']}]})
   xml=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Trade update</title><link href="https://example.org/update"/><summary>Real policy summary</summary><updated>2024-01-01T00:00:00Z</updated></entry></feed>'
   with patch.object(core,'fetch_public_https',return_value=xml):core.fetch_feed(store,'atom')
   row=store.export_evidence()['records'][0];self.assertEqual(row['url'],'https://example.org/update');self.assertEqual(row['retrieval_kind'],'feed_excerpt')
 def stream(self,events,delay=0):
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    self.rfile.read(int(self.headers['Content-Length']));self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
    try:
     for event in events:
      time.sleep(delay);self.wfile.write(('data: '+(json.dumps(event) if isinstance(event,dict) else event)+'\n\n').encode());self.wfile.flush()
    except (BrokenPipeError,ConnectionResetError):pass
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  return 'http://127.0.0.1:'+str(server.server_port)+'/v1'
 def test_stream_activity_outlives_idle_window(self):
  events=[{'choices':[{'delta':{'reasoning_content':'private reasoning'}}]}]+[{'choices':[{'delta':{'content':c}}]} for c in ['{"action":','"recall",','"arguments":{}}']]+[{'choices':[{'delta':{},'finish_reason':'stop'}]},'[DONE]']
  base=self.stream(events,.03);p=transport.completion(base,'',{'stream':True},2,.07)
  self.assertGreater(.03*len(events),.07);self.assertEqual(json.loads(p['choices'][0]['message']['content'])['action'],'recall');self.assertNotIn('private reasoning',json.dumps(p))
 def test_incomplete_stream_is_not_a_completed_action(self):
  base=self.stream([{'choices':[{'delta':{'content':'{}'}}]}])
  with self.assertRaisesRegex(RuntimeError,'incomplete'):transport.completion(base,'',{},2)
 def test_absolute_deadline_even_with_active_stream(self):
  base=self.stream([{'choices':[{'delta':{'content':'x'}}]}]*20,.02)
  start=time.monotonic()
  with self.assertRaises(RuntimeError):transport.completion(base,'',{},.10,.05)
  self.assertLess(time.monotonic()-start,.5)
