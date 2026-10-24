"""CI-only installation of a checksum-pinned optional OfficeCLI in runner temp."""
import hashlib
import os
from pathlib import Path
import platform
import urllib.request

system=platform.system();arm=platform.machine().lower() in ('arm64','aarch64')
targets={
 ('Darwin',True):('officecli-mac-arm64','67cf08d95fab556cad9d1e9d0d3b76a7962b5658c716aeaef2e83cbc19af7ff7'),
 ('Darwin',False):('officecli-mac-x64','038716417adb626d5e94bc71dfecea2d2be9838f3d9b2eb49c2f0b3d634cf4f2'),
 ('Linux',False):('officecli-linux-x64','9ee41d5558caea7bcd5aab1b3e76b2bd70f0535f09cf65dda3668130510cc719'),
 ('Windows',False):('officecli-win-x64.exe','117545f3bc817d7c6d2e78a62e4f73f75b918ccd61558e404c60949a8cb9fd1f'),
 ('Windows',True):('officecli-win-arm64.exe','48567b4bc5a124fb0a709bac29a1e13b6760f094741d0e2bb755680ec9e51295'),
}
name,checksum=targets[(system,arm)]
assert os.environ.get('GITHUB_ACTIONS')=='true','Run this installer only inside explicit CI'
target=Path(os.environ['RUNNER_TEMP'])/name
with urllib.request.urlopen('https://github.com/iOfficeAI/OfficeCLI/releases/download/v1.0.158/'+name,timeout=60) as source:
 raw=source.read(40_000_001)
assert len(raw)<=40_000_000 and hashlib.sha256(raw).hexdigest()==checksum,'OfficeCLI checksum mismatch'
target.write_bytes(raw);target.chmod(0o700)
with open(os.environ['GITHUB_ENV'],'a',encoding='utf-8') as handle:
 handle.write('AGENT_OFFICECLI='+str(target)+'\n')
print('Pinned OfficeCLI v1.0.158 checksum verified')
