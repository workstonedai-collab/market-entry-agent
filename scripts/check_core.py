import argparse, hashlib, json
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("--peer")
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
m = json.loads((root / "shared-core.json").read_text())
for name, expected in m["files"].items():
    actual = hashlib.sha256((root / "src" / m["module"] / name).read_bytes()).hexdigest()
    assert actual == expected, f"Core manifest drift: {name}"
if a.peer:
    peer = Path(a.peer)
    other = json.loads((peer / "shared-core.json").read_text())
    assert other["version"] == m["version"] and other["files"] == m["files"], "Peer core drift"
print("Shared core manifest verified:", m["version"])
