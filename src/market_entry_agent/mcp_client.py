"""Opt-in public-search MCP stdio client. No private context or model-selected command."""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from urllib.parse import urlsplit


def profile(name):
    if not isinstance(name,str) or not re.fullmatch(r'[a-z0-9_-]{1,64}',name):raise ValueError('mcp_search requires a configured profile name')
    configured=os.environ.get('AGENT_MCP_CONFIG')
    if not configured:raise ValueError('Set AGENT_MCP_CONFIG to an operator-owned private JSON file')
    path=Path(configured).expanduser()
    if path.stat().st_size>32000:raise ValueError('MCP configuration exceeds 32000 bytes')
    values=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(values,dict) or not isinstance(values.get('public_search_profiles'),dict):raise ValueError('Invalid MCP configuration root')
    value=values['public_search_profiles'].get(name)
    allowed={'command','tool','query_field','arguments','env_allowlist','allowed_hosts'}
    if not isinstance(value,dict) or set(value)-allowed:raise ValueError('Invalid public MCP search profile')
    command=value.get('command')
    if not isinstance(command,list) or not 1<=len(command)<=20 or any(not isinstance(x,str) or not x or len(x)>2000 for x in command):raise ValueError('MCP command must be a bounded operator-owned argument list')
    if not Path(command[0]).is_absolute() or not Path(command[0]).is_file():raise ValueError('MCP executable must be an absolute existing file')
    if not isinstance(value.get('tool'),str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',value['tool']):raise ValueError('MCP profile requires an explicit tool name')
    query_field=value.get('query_field','query')
    if not isinstance(query_field,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}',query_field):raise ValueError('Invalid query field')
    arguments=value.get('arguments',{})
    if not isinstance(arguments,dict) or query_field in arguments or len(json.dumps(arguments))>1000:raise ValueError('Invalid fixed MCP search arguments')
    env=value.get('env_allowlist',[])
    if not isinstance(env,list) or len(env)>20 or any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}',x) for x in env):raise ValueError('Invalid MCP environment allowlist')
    hosts=value.get('allowed_hosts',[])
    if not isinstance(hosts,list) or not hosts or len(hosts)>20 or any(not isinstance(x,str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.[a-z]{2,}',x) for x in hosts):raise ValueError('Set exact public source hosts for this MCP search profile')
    result=dict(value,query_field=query_field,arguments=arguments,env_allowlist=env,name=name)
    result['version']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return result


class Client:
    def __init__(self,config,timeout):
        self.deadline=time.monotonic()+min(40,timeout);self.seq=0;self.lines=queue.Queue(maxsize=10)
        # Only process necessities and explicitly allowed service credentials reach the configured server.
        names={'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','TMPDIR','LANG','LC_ALL'}|set(config.get('env_allowlist',[]))
        env={k:v for k,v in os.environ.items() if k in names}
        self.process=subprocess.Popen(config['command'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env)
        def read():
            try:
                while True:
                    line=self.process.stdout.readline(1000001)
                    if not line or len(line)>1000000:self.lines.put(None,timeout=1);break
                    self.lines.put(line,timeout=max(.01,self.deadline-time.monotonic()))
            except (OSError,ValueError,queue.Full):pass
        self.reader=threading.Thread(target=read,daemon=True);self.reader.start()
    def send(self,method,params,notification=False):
        message={'jsonrpc':'2.0','method':method,'params':params}
        if not notification:self.seq+=1;message['id']=self.seq
        raw=(json.dumps(message,ensure_ascii=False)+'\n').encode()
        if len(raw)>4000:raise ValueError('mcp_search_request_limit')
        self.process.stdin.write(raw);self.process.stdin.flush()
        if notification:return None
        for _ in range(50):
            try:line=self.lines.get(timeout=max(.001,self.deadline-time.monotonic()))
            except queue.Empty:raise ValueError('mcp_search_timeout') from None
            if line is None:raise ValueError('mcp_search_protocol_or_output_limit')
            try:reply=json.loads(line)
            except ValueError:raise ValueError('mcp_search_invalid_json') from None
            if not isinstance(reply,dict) or reply.get('jsonrpc')!='2.0':raise ValueError('mcp_search_invalid_protocol')
            if reply.get('id')!=self.seq:continue
            if 'error' in reply:raise ValueError('mcp_search_rpc_failed')
            return reply.get('result',{})
        raise ValueError('mcp_search_message_budget_exhausted')
    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2)
        for stream in (self.process.stdin,self.process.stdout):
            if stream:
                try:stream.close()
                except OSError:pass
        self.reader.join(timeout=1)


def search(store,mission,query,timeout,config):
    from .core import digest
    from .net import cached,cache
    identity=digest({'provider':'mcp','version':config['version'],'query':query,'domains':mission.get('search_domains',[])})
    payload=cached(store,'mcp-search:'+identity,3600);hit=payload is not None
    if not hit:
        client=None
        try:
            client=Client(config,timeout)
            initialized=client.send('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'field-agent-public-search','version':'1'}})
            if initialized.get('protocolVersion') not in ('2025-11-25','2025-06-18','2025-03-26','2024-11-05'):raise ValueError('mcp_search_unsupported_protocol')
            client.send('notifications/initialized',{},True)
            tools=client.send('tools/list',{})
            if not any(t.get('name')==config['tool'] for t in tools.get('tools',[])):raise ValueError('Configured MCP search tool not advertised')
            result=client.send('tools/call',{'name':config['tool'],'arguments':dict(config['arguments'],**{config['query_field']:query})})
            if result.get('isError'):raise ValueError('mcp_search_tool_failed')
            payload=result.get('structuredContent')
            if payload is None:
                blocks=[c['text'] for c in result.get('content',[]) if c.get('type')=='text']
                payload=json.loads('\n'.join(blocks))
            if not isinstance(payload,dict) or not isinstance(payload.get('results'),list):raise ValueError('MCP search must return an object with results[]')
            cache(store,'mcp-search:'+identity,payload)
        except (OSError,subprocess.SubprocessError):raise ValueError('mcp_search_process_failed') from None
        finally:
            if client:client.close()
    records=[];hosts=set(config['allowed_hosts']);domains=mission.get('search_domains',[])
    for row in payload['results'][:10]:
        if not isinstance(row,dict):continue
        url=row.get('url','')
        if not isinstance(url,str):continue
        parts=urlsplit(url)
        if parts.scheme!='https' or parts.hostname not in hosts or parts.username or parts.password or (domains and parts.hostname not in domains):continue
        if not isinstance(row.get('title'),str) or not isinstance(row.get('body'),str) or not row['title'] or not row['body']:continue
        records.append({'title':row['title'][:1000],'body':row['body'][:6000],'url':url,'countries':mission['countries'],'topics':mission['topics'],
            'status':'source_claim','retrieval_kind':'search_snippet','search_query':query,'search_provider':'mcp:'+config['name'],'published_at':None,'provider_date':row.get('published_at') if isinstance(row.get('published_at'),str) else None})
    store.import_evidence({'schema':'field-evidence/v1','records':records})
    ids=[digest({**r,'synthetic':False,'event_key':digest(r['url'])[:20]})[:24] for r in records]
    return {'query':query,'cached':hit,'results':[store.read(eid) for eid in ids],
            'limitation':'External MCP results are untrusted discovery snippets. Fetch and read original source text before citing. Only the configured public query and fixed arguments were sent; source dates are unverified.'}
