"""Read-only dedicated Hermes preflight; never prints tokens or provider keys."""
import json,os
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
base=os.environ.get("AGENT_MODEL_BASE_URL","").rstrip("/")
key=os.environ.get("AGENT_MODEL_API_KEY","")
if not base or not key:
    raise SystemExit("Set AGENT_MODEL_BASE_URL and AGENT_MODEL_API_KEY")
from urllib.parse import urlsplit
p=urlsplit(base)
if p.username or p.password or p.query or p.fragment or (p.scheme!="https" and not(p.scheme=="http" and p.hostname in ("127.0.0.1","localhost","::1"))):
    raise SystemExit("Use HTTPS or loopback HTTP without URL credentials")
def get(path):
    req=Request(base+path,headers={"Authorization":"Bearer "+key})
    try:
        with urlopen(req,timeout=10) as response:
            raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise SystemExit("Response exceeds budget")
        return json.loads(raw)
    except HTTPError as exc:raise SystemExit("Hermes HTTP "+str(exc.code)) from None
    except (URLError,OSError):raise SystemExit("Hermes network/unavailable") from None
caps=get("/capabilities");sets=get("/toolsets");models=get("/models")
enabled=[t["name"] for t in sets.get("data",[]) if t.get("enabled")]
print(json.dumps({"platform":caps.get("platform"),"streaming":caps.get("features",{}).get("chat_completions_streaming"),"enabled_toolsets":enabled,"models":[m.get("id") for m in models.get("data",[])]},ensure_ascii=False,indent=2))
if enabled:raise SystemExit("Use a dedicated profile with empty api_server toolsets")
