"""Workspace-owned model settings and explicit setup checks. No credential discovery."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from urllib.parse import urlsplit

KEYS={'AGENT_MODEL_BASE_URL','AGENT_MODEL_NAME','AGENT_MODEL_MAX_TOKENS','AGENT_MODEL_REASONING_EFFORT','AGENT_MODEL_API_KEY'}
_sessions={}
_lock=threading.Lock()


def _path(store):return store.workspace/'model-profile.json'


def _profile(store):
    path=_path(store)
    if not path.exists():return {}
    if path.is_symlink() or path.stat().st_size>12000:raise ValueError('Workspace model profile is unavailable or too large')
    try:value=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):raise ValueError('Workspace model profile is unreadable') from None
    if not isinstance(value,dict) or not {'AGENT_MODEL_BASE_URL','AGENT_MODEL_NAME'}<=set(value) or set(value)-KEYS or any(not isinstance(v,str) for v in value.values()):raise ValueError('Invalid workspace model profile')
    return value


def environment(store):
    env=dict(os.environ);saved=_profile(store)
    if not saved:return env
    # Never carry an environment credential to a newly chosen endpoint.
    prior_base=env.get('AGENT_MODEL_BASE_URL','').rstrip('/')
    if saved.get('AGENT_MODEL_BASE_URL','').rstrip('/')!=prior_base:env.pop('AGENT_MODEL_API_KEY',None)
    env.update(saved)
    with _lock:session=_sessions.get(str(store.workspace))
    if session and session[0]==env.get('AGENT_MODEL_BASE_URL','').rstrip('/'):env['AGENT_MODEL_API_KEY']=session[1]
    return env


def save_model(store,body):
    from .core import Model
    if not isinstance(body,dict) or set(body)-{'base_url','model','api_key','remember_key','max_tokens','reasoning_effort'}:raise ValueError('Unknown model setup fields')
    base=body.get('base_url');name=body.get('model');key=body.get('api_key','');remember=body.get('remember_key',False);maximum=body.get('max_tokens',6000);effort=body.get('reasoning_effort','')
    if not isinstance(base,str) or len(base)>2000 or not isinstance(name,str) or not 1<=len(name)<=200:raise ValueError('Model endpoint and name are required')
    if not isinstance(key,str) or len(key)>4000 or '\n' in key or type(remember) is not bool:raise ValueError('Invalid model credential settings')
    if not isinstance(effort,str) or effort not in ('','low','medium','high','xhigh','max'):raise ValueError('Invalid reasoning effort')
    if type(maximum) is not int or not 512<=maximum<=6000:raise ValueError('Model output limit must be 512..6000')
    settings={'AGENT_MODEL_BASE_URL':base.strip().rstrip('/'),'AGENT_MODEL_NAME':name.strip(),'AGENT_MODEL_MAX_TOKENS':str(maximum),'AGENT_MODEL_REASONING_EFFORT':effort}
    try:current=environment(store)
    except (ValueError,OSError,TypeError):current={}
    if not key and current.get('AGENT_MODEL_BASE_URL','').rstrip('/')==settings['AGENT_MODEL_BASE_URL']:key=current.get('AGENT_MODEL_API_KEY','')
    Model(dict(settings,AGENT_MODEL_API_KEY=key))  # Validate before changing persisted or in-memory state.
    if remember and key:settings['AGENT_MODEL_API_KEY']=key
    path=_path(store)
    if path.is_symlink():raise ValueError('Refusing a symlinked model profile')
    fd,temporary=tempfile.mkstemp(prefix='.model-profile-',dir=store.workspace)
    try:
        os.chmod(temporary,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as handle:json.dump(settings,handle,ensure_ascii=False,indent=2)
        os.replace(temporary,path)
    finally:
        if Path(temporary).exists():Path(temporary).unlink()
    initialize_checks(store)
    with store.tasks() as db:db.execute('DELETE FROM setup_checks')
    with _lock:
        if key:_sessions[str(store.workspace)]=(settings['AGENT_MODEL_BASE_URL'],key)
        else:_sessions.pop(str(store.workspace),None)
    return {'saved':True,'credential_storage':'private_file_unencrypted' if remember and key else 'current_process_only' if key else 'not_configured',
            'network_tested':False,'note':'Settings saved. A separate explicit connection test makes one model request. Session-only keys are unavailable to a separately started worker.'}


def source_pack():return json.loads(Path(__file__).with_name('data').joinpath('public-source-pack.json').read_text(encoding='utf-8'))


def register_sources(store,ids):
    if not isinstance(ids,list) or not 1<=len(ids)<=8 or any(not isinstance(i,str) for i in ids):raise ValueError('Select public source IDs')
    known={s['id']:s for s in source_pack()['sources']}
    if any(i not in known for i in ids):raise ValueError('Source outside this product pack')
    existing={s['id']:s for s in store.sources()}
    if any(i in existing and existing[i]!=known[i] for i in ids):raise ValueError('Existing source settings differ; review them explicitly instead of overwriting with the example pack')
    return dict(store.register_sources({'sources':[known[i] for i in dict.fromkeys(ids)]}),monitoring_started=False,network_called=False)


def initialize_checks(store):
    with store.tasks() as db:db.execute('CREATE TABLE IF NOT EXISTS setup_checks(product TEXT PRIMARY KEY,fingerprint TEXT,state TEXT,error TEXT,checked REAL)')


def model_fingerprint(env):
    return hashlib.sha256(json.dumps({k:env.get(k,'') for k in sorted(KEYS-{'AGENT_MODEL_API_KEY'})},sort_keys=True).encode()).hexdigest()


def connection_test(store,product):
    from .core import Model
    initialize_checks(store);env=environment(store);model=Model(env);state='failed';error=None
    try:
        action=model.next([{'role':'system','content':'Connection test only. Return JSON {"action":"diagnostic","arguments":{"ok":true}}. No research or tools.'},{'role':'user','content':'Return the requested connection-test JSON.'}],timeout=25)
        if action.get('action')!='diagnostic' or action.get('arguments',{}).get('ok') is not True:raise ValueError('model_diagnostic_contract')
        state='success'
    except (ValueError,RuntimeError,OSError) as exc:
        import re
        message=str(exc)
        error=message if re.fullmatch(r'[a-zA-Z0-9_ .:-]{1,120}',message) else type(exc).__name__
    stamp=time.time()
    with store.tasks() as db:db.execute('INSERT OR REPLACE INTO setup_checks VALUES(?,?,?,?,?)',(product,model_fingerprint(env),state,error,stamp))
    return {'state':state,'error':error,'checked_at':stamp,'model_requests':1,'user_material_sent':False}


def status(store,product):
    from .core import Model
    from .source_health import overview
    from .worker_health import status as workers
    initialize_checks(store);model=None;issue=None
    try:env=environment(store)
    except (ValueError,OSError,TypeError):env={};issue='workspace_profile_unreadable'
    try:model=Model(env)
    except (ValueError,OSError,TypeError) as exc:issue='model_configuration_missing_or_invalid'
    with store.tasks() as db:row=db.execute('SELECT * FROM setup_checks WHERE product=?',(product,)).fetchone()
    last=dict(row) if row and row['fingerprint']==model_fingerprint(env) else None
    if last:last.pop('fingerprint',None)
    adapters={}
    for label,var in [('office_import','AGENT_DOCUMENT_ADAPTER_PYTHON'),('word_export','AGENT_OFFICECLI')]:
        value=os.environ.get(var,'');adapters[label]={'configured':bool(value),'file_available':bool(value and Path(value).expanduser().is_file())}
    adapters['pdf']={'configured':bool(os.environ.get('AGENT_PDF_ADAPTER_PYTHON') or shutil.which('pdftotext'))}
    return {'model':{'configured':model is not None,'name':model.name if model else None,'base_url':model.base if model else None,'max_tokens':model.max_tokens if model else 6000,'reasoning_effort':model.effort if model else '', 'credential_persisted':bool(_profile(store).get('AGENT_MODEL_API_KEY')) if model else False,'endpoint_host':urlsplit(model.base).hostname if model else None,'credential_available':bool(model and model.key),'profile_saved':_path(store).is_file(),'issue':issue,'last_connection_test':last},
            'sources':overview(store),'source_pack':source_pack()['sources'],'adapters':adapters,
            'optional_connections':{'mcp_search_configured':bool(os.environ.get('AGENT_MCP_CONFIG')),'hermes_delivery_configured':bool(os.environ.get('AGENT_MONITOR_DELIVERY_CONFIG'))},
            'workers':workers(store,product),'model_calls':0,'note':'Configuration and file availability only. A successful test is a separate observation; adapters are not executed by this status read.'}


def model_configured(store):
    from .core import Model
    try:Model(environment(store));return True
    except (ValueError,OSError,TypeError):return False
