"""Execute the shipped browser helpers with Node when available; no npm packages."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Optional browser-script check requires Node.js")
class ProjectBrowser(unittest.TestCase):
    def test_forms_history_and_untrusted_values(self):
        script = r"""
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const elements=new Map();
const element=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',innerHTML:'',disabled:false,classList:{remove(){},add(){}},addEventListener(){}});return elements.get(id)};
const context=vm.createContext({assert,$:element,document:{querySelector:element,querySelectorAll:()=>[]},esc:v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
vm.runInContext(`
businessForm('event');assert.equal($('business-id').value,'auto');assert.ok($('business-id-hint').textContent.includes('auto'));
businessForm('option');assert.equal($('business-id').value,'');assert.ok(!$('business-id-hint').textContent.includes('auto'));
businessForm('profile');assert.equal($('business-id').value,'main');assert.equal($('business-id').disabled,true);
businessForm('option',{id:'existing',revision:2,data:{name:'<img src=x onerror=alert(1)>',dimensions:{demand:'preserved'}}});
assert.equal($('business-id').value,'existing');assert.equal($('business-id').disabled,true);
assert.ok(!$('business-fields').innerHTML.includes('<img'));assert.ok($('business-fields').innerHTML.includes('preserved'));
for(const kind of Object.keys(fieldSpec)){
 const data={status:kind==='stage'?'done':'candidate',note:'<script>alert(1)</script>',unknown_field:'keep me',actions:['one','two'],active:false};
 const html=historyHTML(kind,'<unsafe>',[{revision:2,updated:'2026-10-22',data}]);
 assert.ok(html.includes('<dl>'));assert.ok(html.includes('<pre>'));
 assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<unsafe>'));assert.ok(html.includes('&lt;script&gt;'));
 assert.ok(html.includes('keep me'));assert.ok(html.includes('one；two'));assert.ok(!html.includes('>false<'));
}
businessForm('economics',{id:'quote',revision:2,data:{name:'Synthetic',values:{freight:{value:'0',basis:'operator_quote',note:'<unsafe quote>'}}}});
assert.ok($('business-fields').innerHTML.includes('value="0"'));assert.ok($('business-fields').innerHTML.includes('&lt;unsafe quote&gt;'));assert.ok(!$('business-fields').innerHTML.includes('<unsafe quote>'));
assert.ok(historyFields('economics',{contribution_before_other_costs:'680'}).includes('贡献额'));
assert.ok(attentionReason('Operator deadline within seven days').includes('7天'));
const calculation={metrics:{revenue:'2000',contribution_before_other_costs:'680',contribution_margin:'0.34'},missing:['freight'],assumptions:['unit_price']};
const economics=economicsHTML([{name:'<unsafe>',currency:'USD',calculation}]);assert.ok(economics.includes('680.00'));assert.ok(economics.includes('34.00%'));assert.ok(economics.includes('未填写'));assert.ok(!economics.includes('<unsafe>'));assert.ok(economics.includes('单位售价'));
const dimensions=historyFields('option',{dimensions:{demand:'demand detail',economics:'cost detail'},status:'selected'});
assert.ok(dimensions.includes('demand detail'));assert.ok(dimensions.includes('cost detail'));assert.ok(!dimensions.includes('>selected<'));
assert.ok(!historyFields('stage',{status:'done'}).includes('>done<'));
const hostile='<img src=x onerror=alert(1)>';
const change=changeHTML({previous:{impact:'old'},assessment:{severity:'high',status:'escalated',confidence:'source_statement',impact:hostile,next_check:'check'},change_note:hostile,new_evidence_ids:[],source_details:[]});
assert.ok(change.includes('old'));assert.ok(change.includes('&lt;img'));assert.ok(!change.includes('<img'));
const aids=decisionHTML({decision_options:[{name:hostile,fit:'conditional',tradeoff:'control',requirements:'quote needed',next_check:'buyer interview'}],validation_priorities:[{question:'demand',why_first:'changes choice',next_step:'interview',if_supported:'continue',if_not:'pause'}]});
assert.ok(aids.includes('quote needed'));assert.ok(aids.includes('pause'));assert.ok(!aids.includes('<img'));
const health=sourceHealthHTML({registered:1,fresh:0,latest_failed:1,sources:[{title:hostile,freshness:'stale',refresh_hours:24,latest_attempt_failed:true,last_error:'retrieval_failed'}]});
assert.ok(!health.includes('<img'));assert.ok(health.includes('retrieval_failed'));
const paragraphs=reportProse('first paragraph\\n\\n<script>second</script>');
assert.equal((paragraphs.match(/<p>/g)||[]).length,2);assert.ok(!paragraphs.includes('<script>'));assert.ok(paragraphs.includes('&lt;script&gt;'));

`,context);
console.log('Shipped UI: all record types, typed hints, saved values, readable history and HTML escaping passed.');
"""
        result = subprocess.run([shutil.which("node"), "-e", script, str(ROOT / "src" / "market_entry_agent" / "workflow-ui.js")], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
