"""Bounded streaming chat transport. Incomplete actions are never checkpointed."""
import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

MAX_BYTES=1_000_000

def completion(base,key,body,timeout,idle_seconds=120,request_id=None):
    end=time.monotonic()+timeout
    headers={'Content-Type':'application/json','Accept':'text/event-stream, application/json'}
    if key:
        headers['Authorization']='Bearer '+key
    if request_id:
        headers['Idempotency-Key']=request_id
    request=Request(base+'/chat/completions',data=json.dumps(body).encode(),headers=headers)
    try:
        with urlopen(request,timeout=max(.01,min(timeout,idle_seconds))) as response:
            if 'text/event-stream' not in response.headers.get('Content-Type',''):
                chunks=[]; size=0
                while response.fp is not None:
                    remaining=end-time.monotonic()
                    if remaining<=0:
                        raise RuntimeError('run_deadline_exceeded')
                    response.fp.raw._sock.settimeout(max(.01,min(idle_seconds,remaining)))
                    chunk=response.read1(min(65536,MAX_BYTES+1-size))
                    if not chunk:
                        break
                    chunks.append(chunk);size+=len(chunk)
                    if size>MAX_BYTES:
                        raise ValueError('Model response exceeds byte budget')
                raw=b''.join(chunks)
                if time.monotonic()>end:
                    raise RuntimeError('run_deadline_exceeded')
                return json.loads(raw)
            pieces=[]; size=0; finish=None; done=False
            while True:
                remaining=end-time.monotonic()
                if remaining<=0:
                    raise RuntimeError('run_deadline_exceeded')
                # urllib exposes the underlying socket here on supported CPython.
                # Read timeout is idle time; total deadline stays independent.
                try:
                    response.fp.raw._sock.settimeout(max(.01,min(idle_seconds,remaining)))
                except AttributeError:
                    pass
                line=response.readline(MAX_BYTES-size+1)
                size+=len(line)
                if size>MAX_BYTES:
                    raise ValueError('Model response exceeds byte budget')
                if not line:
                    break
                if not line.startswith(b'data:'):
                    continue
                data=line[5:].strip()
                if not data:
                    continue
                if data==b'[DONE]':
                    done=True; break
                event=json.loads(data)
                if event.get('error'):
                    raise RuntimeError('model_stream_error')
                if event.get('input_sensitive') or event.get('output_sensitive'):
                    raise RuntimeError('model_content_filtered')
                if event.get('base_resp',{}).get('status_code',0):
                    raise RuntimeError('model_provider_error')
                for choice in event.get('choices',[]):
                    if choice.get('index',0)!=0:
                        continue
                    if choice.get('finish_reason'):
                        finish=choice['finish_reason']
                    content=choice.get('delta',{}).get('content')
                    if isinstance(content,str):
                        pieces.append(content)
                    # Provider reasoning, tool progress and other channels discarded.
            if not finish or not done:
                raise RuntimeError('model_stream_incomplete')
            if finish not in ('stop','length'):
                raise RuntimeError('model_stream_finish_'+str(finish)[:30])
            return {'choices':[{'message':{'content':''.join(pieces)},'finish_reason':finish}]}
    except HTTPError as exc:
        raise RuntimeError(f'model_http_{exc.code}') from None
    except (URLError,TimeoutError,OSError):
        raise RuntimeError('model_network_or_timeout') from None
