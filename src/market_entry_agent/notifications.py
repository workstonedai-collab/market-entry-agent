"""Explicit operator-configured Hermes delivery; uncertain sends never retry silently."""
import hashlib
import json
import os
import subprocess
from pathlib import Path


def profile(name):
    path=os.environ.get('AGENT_MONITOR_DELIVERY_CONFIG','')
    if not path:raise ValueError('Configure AGENT_MONITOR_DELIVERY_CONFIG for external delivery')
    root=json.loads(Path(path).expanduser().read_text(encoding='utf-8'))
    p=root.get(name)
    if not isinstance(p,dict) or set(p)!={'label','target','executable'} or any(not isinstance(p[x],str) or not p[x] for x in p):raise ValueError('Delivery profile requires label, target and executable')
    binary=Path(p['executable']).expanduser()
    if not binary.is_absolute() or not binary.is_file():raise ValueError('Hermes executable must be an existing absolute operator path')
    if os.name=='nt' and binary.suffix.lower() not in ('.exe','.com'):raise ValueError('Native Windows delivery requires a directly executable Hermes .exe, not a shell wrapper')
    p['executable']=str(binary)
    return p


def binding(name):
    p=profile(name)
    return {'label':p['label'],'fingerprint':hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()}


def message_id(value):
    if isinstance(value,dict):
        if isinstance(value.get('message_id'),str) and value['message_id']:return value['message_id']
        for v in value.values():
            found=message_id(v)
            if found:return found
    if isinstance(value,list):
        for v in value:
            found=message_id(v)
            if found:return found
    return None


def send(store,config,did):
    if config.get('delivery','local')=='local':return {'state':'local_inbox'}
    p=profile(config['delivery_profile'])
    if binding(config['delivery_profile'])!=config['delivery_binding']:raise ValueError('Delivery destination changed; edit and reconfirm monitor settings')
    with store.tasks() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM monitor_deliveries WHERE id=?',(did,)).fetchone()
        if not row:raise ValueError('Unknown delivery')
        if row['state']=='sending':
            db.execute("UPDATE monitor_deliveries SET state='unknown' WHERE id=?",(did,));return {'state':'unknown'}
        if row['state']!='pending':return {'state':row['state']}
        db.execute("UPDATE monitor_deliveries SET state='sending' WHERE id=?",(did,))
        payload=json.loads(row['payload'])
    # Send the saved digest, never regenerate it to recover a delivery failure.
    body=payload['title']+'\n\n'+'\n\n'.join(i['title']+'\n'+i['summary'] for i in payload['items'])
    state='unknown';receipt=None
    try:
        with __import__('tempfile').TemporaryFile() as output:
            result=subprocess.run([p['executable'],'send','--to',p['target'],'--json',body],stdout=output,stderr=subprocess.DEVNULL,timeout=60,check=False)
            if result.returncode:state='failed'
            else:
                output.seek(0);raw=output.read(1_000_001)
                if len(raw)<=1_000_000:
                    try:receipt=message_id(json.loads(raw))
                    except (ValueError,UnicodeError):pass
                state='sent' if receipt else 'unknown'
    except OSError:state='failed'
    except subprocess.TimeoutExpired:pass
    with store.tasks() as db:
        if receipt:payload['external_receipt']={'message_id':receipt,'destination_label':p['label']}
        db.execute('UPDATE monitor_deliveries SET state=?,payload=? WHERE id=?',(state,json.dumps(payload,ensure_ascii=False),did))
    return {'state':state,'message_id':receipt}
