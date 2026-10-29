"""Exercise shipped lifecycle form contracts and escaping without a browser dependency."""
import shutil
import subprocess
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'),'Optional UI check requires Node.js')
class LifecycleBrowser(unittest.TestCase):
    def test_preview_form_scope_and_escaping(self):
        script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();const $=id=>{if(!elements.has(id))elements.set(id,{value:'',checked:false,disabled:false,textContent:'',innerHTML:'',selectedOptions:[],options:[],classList:{contains(){return true}},addEventListener(){}});return elements.get(id)};
const c=vm.createContext({$,assert,console,window:{addEventListener(){}},document:{hidden:false,querySelectorAll:()=>[],addEventListener(){}},esc:x=>String(x??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x])),skillsLoaded:false,mission:()=>({question:'Current question',countries:['Vietnam'],topics:['trade'],knowledge_ids:['selected-only']}),clearTimeout,setTimeout});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),c);
vm.runInContext(`
$('lc-project').value='project';$('monitor-name').value='Watch';$('monitor-kind').value='theme';$('monitor-criteria').value='New applicability';$('monitor-min-sources').value='1';$('monitor-interval').value='60';$('monitor-digest').value='1440';$('monitor-timezone').value='UTC+08:00';$('monitor-engine').value='rules';$('monitor-delivery').value='local';
monitorDraft={config:{mission:{max_model_calls:3,search_domains:['example.org'],question:'old'}}};
const config=watchConfig();assert.equal(config.mission.question,'Current question');assert.equal(config.mission.project_id,'project');assert.equal(config.mission.max_model_calls,3);assert.deepEqual(config.mission.search_domains,['example.org']);assert.equal(JSON.stringify(config.mission.knowledge_ids),JSON.stringify(['selected-only']));assert.equal(config.check_interval,3600);assert.equal(config.digest_interval,86400);assert.equal(config.allow_private_delivery,false);
const unsafe='<script>alert(1)</script>';
const html=monitorPreviewHTML({settings:{...config,name:unsafe,criteria:unsafe,source_ids:[],include_terms:[],exclude_terms:[],quiet_hours:[]},matching_records:1,matches:[{title:unsafe,excerpt:unsafe}]});
assert.ok(!html.includes('<script>'));assert.ok(html.includes('&lt;script&gt;'));assert.ok(html.includes('规则检查不调用模型'));assert.ok(html.includes('知识库 1 个'));assert.ok(html.includes('尚未刷新外部来源'));
const feedback=feedbackControls('report',unsafe,unsafe);assert.ok(!feedback.includes('<script>'));assert.ok(feedback.includes('&lt;script&gt;'));assert.ok(feedback.includes('data-feedback-rating="needs_correction"'));

`,c);
'''
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'src'/'market_entry_agent'/'lifecycle-ui.js')],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
