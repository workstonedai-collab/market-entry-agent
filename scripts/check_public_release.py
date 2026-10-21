"""Check the explicit public-source allowlist, data shape and release identity."""
from pathlib import Path
import argparse,json,re,subprocess
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--working-tree-only',action='store_true');a=p.parse_args()
allowed=set(json.loads((root/'PUBLIC_FILES.json').read_text())['files'])
tracked=set(subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],cwd=root,text=True).splitlines())
actual={s for s in tracked if (root/s).is_file()}
assert actual==allowed, 'Public file list differs: '+str(sorted(actual^allowed))
patterns=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'\b(?:ghp_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{24,})\b',r'/Users/[^\s/]+|/private/(?:tmp|var)/',r'admin\.'+'gknsailsmart'+r'\.com',r'\b'+'G'+'KN'+r'\b']
for name in sorted(actual):
 file=root/name
 if file.suffix.lower() in ('.png',):continue
 try:text=file.read_text(encoding='utf-8')
 except UnicodeDecodeError:continue
 if name==str(Path(__file__).relative_to(root)):continue
 assert not any(re.search(x,text,re.I) for x in patterns),'Prohibited public content in '+name
 if name.endswith('country-baselines.json'):
  data=json.loads(text)
  assert set(data)=={'schema','method_version','as_of','available_from','status','score_semantics','formula','sources','countries','limitations'}
  assert all(set(c)=={'code','name','region','income_group','wgi','bready'} for c in data['countries'])
for package in (root/'src').iterdir():
 if not package.is_dir() or package.name.endswith('.egg-info'):continue
 for file in package.rglob('*'):
  if file.is_file() and '__pycache__' not in file.parts:assert str(file.relative_to(root)) in allowed,'Unlisted package file'
if not a.working_tree_only:
 for row in subprocess.check_output(['git','log','--all','--format=%ae %ce'],cwd=root,text=True).splitlines():
  assert all(email.endswith('@users.noreply.github.com') for email in row.split()),'Non-anonymous commit identity'
print('Public file list, content, data schema and identity checks passed')
