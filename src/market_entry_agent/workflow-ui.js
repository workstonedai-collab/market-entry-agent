// Incremental private project desk; all text from sources and operator data is escaped.
let projectDesk=null, editingRecord=null;
const fieldSpec={
 event:[['title','事件名称'],['subject','事件主体'],['location','地点'],['occurred_at','事件发生日期（如 2024-02-18）'],['published_at','本次进展发布日期'],['countries','国区','list'],['topics','主题标签','list'],['summary','来源怎么说','area'],['severity','严重程度','low|moderate|high|critical'],['confidence','信息依据','unconfirmed|source_statement|corroborated'],['status','事件状态','tracking|escalated|easing|closed'],['impact','可能影响及不确定性','area'],['next_check','接下来检查什么','area'],['change_note','本次改变了什么','area'],['evidence_ids','来源编号','list']],
 exposure:[['name','关注对象名称'],['countries','关注国区（可留空）','list'],['topics','关注主题（可留空）','list'],['min_severity','达到什么程度开始提醒','low|moderate|high|critical'],['active','是否启用','bool'],['note','对象说明（私有）','area']],
 feedback:[['alert_id','提醒编号'],['state','反馈','seen|relevant|irrelevant|handled'],['note','反馈说明','area']],
 profile:[['product','具体产品与用途','area'],['buyer','目标客户与使用场景','area'],['stage','当前阶段','exploring|targeted|operating'],['countries','候选或经营国区','list'],['capabilities','渠道、交付和服务能力','area'],['constraints','已有约束或不能接受的条件','area'],['budget','预算与时间条件（可留空）','area']],
 option:[['name','选项名称'],['countries','目标国区','list'],['mode','进入方式'],['status','当前判断','researching|candidate|selected|deferred|blocked'],['rationale','为什么考虑或暂缓','area'],['demand','需求与买方依据','dimension'],['access','进入条件','dimension'],['channel','渠道与竞争','dimension'],['delivery','交付与售后','dimension'],['economics','成本及经济性假设','dimension'],['risks','风险与待验证事项','dimension'],['evidence_ids','来源编号（可留空）','list']],
 assumption:[['statement','方案依赖的关键假设','area'],['status','当前依据','unchecked|supported|challenged|needs_review'],['countries','需监测的国区','list'],['topics','需监测的主题','list'],['option_ids','关联选项编号','list'],['stage_ids','关联阶段编号（可留空）','list'],['evidence_ids','本次判断依据编号（可留空）','list'],['note','判断依据或下一项验证','area']],
 stage:[['goal','阶段目标','area'],['option_id','关联选项编号'],['actions','计划做什么（每行一项）','lines'],['deliverables','交付物（每行一项）','lines'],['completion_signal','怎样判断阶段完成','area'],['depends_on','前置阶段编号（可留空）','list'],['status','进度','planned|doing|blocked|done'],['note','进度说明；完成时填写实际结果','area'],['evidence_ids','相关来源编号（可留空）','list']],
 decision:[['title','本次决策'],['rationale','选择及暂缓的理由','area'],['option_ids','相关选项编号','list'],['evidence_ids','来源编号（可留空）','list']]
};
const businessLabels={event:'事件',exposure:'关注对象',feedback:'提醒反馈',profile:'企业情况',option:'进入方案',assumption:'关键假设',stage:'推进计划',decision:'决策记录'};
const valueLabels={low:'低',moderate:'中',high:'高',critical:'严重',unconfirmed:'尚待确认',source_statement:'来源有说明，待交叉核实',corroborated:'多份资料相互支持',tracking:'跟踪中',escalated:'升级',easing:'缓和',closed:'结束',seen:'已阅',relevant:'有用',irrelevant:'与我无关',handled:'已处理',exploring:'寻找方向',targeted:'已有目标市场',operating:'已进入经营',researching:'研究中',candidate:'候选',selected:'已选择',deferred:'暂缓',blocked:'受阻',unchecked:'待验证',supported:'有支持依据',challenged:'有反向依据',needs_review:'有新资料，待判断',planned:'待开始（建议计划）',doing:'进行中',done:'已完成（由你记录）'};
function businessKind(){return $('business-kind').value}
function businessForm(kind,record=null){
 editingRecord=record;
 $('business-id').value=record?.id||(kind==='profile'?'main':kind==='event'?'auto':'');
 $('business-id').disabled=!!record||kind==='profile';
 $('business-id-hint').textContent=record?'这条记录的编号已固定。保存修改会留下新版本，原内容仍可在“修改记录”中查看。':kind==='feedback'?'反馈编号与提醒编号相同；保存后可继续补充处理说明。':kind==='event'?'保留 auto，会按主体、地点和发生日期识别同一事件。来源编号可在“证据与来源”中查看。':kind==='profile'?'企业情况固定使用 main，每次修改都会保留旧版本。':'为这条记录取一个固定编号，如 route-red-sea 或 germany-distributor。后续关联方案、假设和计划时会用到它。';
 $('business-editor-title').textContent=(record?'修改':'新增')+(businessLabels[kind]||kind);
 $('business-fields').innerHTML=fieldSpec[kind].map(([key,label,type])=>{
  let value=record?.data?.[key]??(type==='dimension'?record?.data?.dimensions?.[key]:undefined)??(type==='bool'?true:'');
  let id='bf-'+key, control;
  if(type==='bool')control='<select id="'+id+'"><option value="true" '+(value===true?'selected':'')+'>启用</option><option value="false" '+(value===false?'selected':'')+'>停用</option></select>';
  else if(type?.includes('|'))control='<select id="'+id+'">'+type.split('|').map(v=>'<option value="'+v+'" '+(v===value?'selected':'')+'>'+esc(valueLabels[v]||v)+'</option>').join('')+'</select>';
  else if(['area','dimension','lines'].includes(type))control='<textarea id="'+id+'">'+esc(Array.isArray(value)?value.join('\n'):value)+'</textarea>';
  else control='<input id="'+id+'" value="'+esc(Array.isArray(value)?value.join(', '):value)+'">';
  return '<div><label for="'+id+'">'+esc(label)+'</label>'+control+'</div>';
 }).join('');
 $('business-editor').classList.remove('hidden');
}
function historyFields(kind,data){
 const specs=fieldSpec[kind]||[], labels=Object.fromEntries(specs.map(([key,label])=>[key,label]));
 const value=(key,v)=>{
  if(v===null||v===undefined||v==='')return '未填写';
  if(typeof v==='boolean')return v?'启用':'停用';
  if(Array.isArray(v))return v.length?v.map(x=>value(key,x)).join('；'):'未填写';
  if(typeof v==='object')return Object.entries(v).map(([k,x])=>(labels[k]||k)+'：'+value(k,x)).join('；');
  return ['status','stage','confidence','severity','min_severity','state'].includes(key)?valueLabels[v]||String(v):String(v);
 };
 return '<dl>'+Object.entries(data).map(([key,v])=>'<dt><b>'+esc(labels[key]||(key==='dimensions'?'方案比较':key))+'</b></dt><dd style="white-space:pre-wrap;margin:6px 0 14px">'+esc(value(key,v))+'</dd>').join('')+'</dl>';
}
function historyHTML(kind,id,history){
 return '<h3>修改记录 · '+esc(id)+'</h3>'+history.map(r=>'<details><summary>第 '+r.revision+' 版 · '+esc(r.updated)+'</summary>'+historyFields(kind,r.data)+'<details><summary>查看原始 JSON</summary><pre>'+esc(JSON.stringify(r.data,null,2))+'</pre></details></details>').join('');
}
async function openProject(){
 try{let id=$('business-project').value.trim(); let data=await api('/api/project?project_id='+encodeURIComponent(id));if(id!==$('business-project').value.trim())return;projectDesk=data;$('project-id').value=id;renderProject();$('business-status').textContent='已打开私有项目 '+id;}catch(e){error(e)}
}
function renderProject(){
 if(!projectDesk)return;
 let risk=projectDesk.product==='georisk-agent', kinds=risk?['event','exposure','feedback']:['profile','option','assumption','stage','decision'];
 $('business-title').textContent=risk?'事件跟踪与业务影响':'市场选择与落地计划';
 $('business-intro').textContent=risk?'记下你关注的人员、资产、航线或业务，跟踪相关事件的进展、可能影响，以及接下来要留意的变化。':'先说清产品、客户和经营条件，再比较去哪里、怎么进入，记录需要验证的前提和下一步工作。';
 $('business-kind').innerHTML=kinds.map(k=>'<option value="'+k+'">'+businessLabels[k]+'</option>').join('');
 $('business-editor').classList.add('hidden');
 let groups=kinds.filter(k=>k!=='feedback').map(kind=>'<div class="card"><h2>'+businessLabels[kind]+'</h2>'+(projectDesk[kind].map(r=>'<div class="source"><b>'+esc(r.data.title||r.data.name||r.data.product||r.data.statement||r.data.goal)+'</b> <span class="tag">'+esc(valueLabels[r.data.status]||valueLabels[r.data.stage]||'已保存')+'</span><p>'+esc(r.data.summary||r.data.rationale||r.data.note||r.data.constraints||'')+'</p><p class="small">编号 '+esc(r.id)+' · 版本 '+r.revision+' · '+esc(r.origin==='agent_proposal'?'智能体建议':r.origin==='runtime'?'运行记录':'你录入的资料')+'</p><div class="buttons"><button data-business-edit="'+kind+':'+r.id+'">查看与修改</button><button data-business-history="'+kind+':'+r.id+'">修改记录</button></div></div>').join('')||'<p class="hint">尚无记录。</p>')+'</div>').join('');
 if(!risk&&projectDesk.comparison?.length)groups='<div class="card"><h2>进入方案比较</h2><p class="hint">从需求、准入、渠道、交付、成本和风险六方面比较方案。国区指数可作背景参考；企业条件改变后，需要重新判断方案是否合适。</p><div class="table-scroll"><table><tr><th>选项</th><th>需求</th><th>准入</th><th>渠道</th><th>交付</th><th>经济性</th><th>风险</th></tr>'+projectDesk.comparison.map(o=>'<tr><td>'+esc(o.name)+'<br>'+esc(o.countries.join(', ')+' · '+o.mode)+(o.profile_changed?'<br><span class="tag warn">企业条件已更新</span>':'')+'</td>'+['demand','access','channel','delivery','economics','risks'].map(k=>'<td>'+esc(o.dimensions[k]||'待补充')+'</td>').join('')+'</tr>').join('')+'</table></div></div>'+groups;
 let notices=risk?projectDesk.alerts:projectDesk.reviews;
 $('business-notices').innerHTML='<p class="hint">资料时效以来源日期为准；历史记录不代表当前预警。本地检查不会刷新外部来源。</p><h2>'+(risk?'变化提醒':'关键假设的新资料')+'</h2>'+(notices.length?notices.slice().reverse().map(r=>'<div class="source"><b>'+esc(r.data.title||r.data.statement)+'</b><p>'+esc(risk?r.data.assessment.impact:'发现了与这条假设相关的新资料。请结合原方案判断：前提是否改变，哪些工作需要调整。资料匹配本身还不能说明政策适用或方案失效。')+'</p>'+(risk?'<p>关联对象：'+esc(r.data.exposure)+' · '+esc(valueLabels[r.data.severity])+' · '+esc(valueLabels[r.data.status])+'</p><p>接下来关注：'+esc(r.data.assessment.next_check)+'</p><p class="small">资料发布日期 '+esc(r.data.published_at)+'；来源 '+esc(r.data.evidence_ids.join(', '))+'</p>':'<p>关联方案：'+esc(r.data.option_ids.map(id=>projectDesk.option.find(o=>o.id===id)?.data.name||id).join('；')||'未关联')+'；阶段：'+esc(r.data.stage_ids.map(id=>projectDesk.stage.find(o=>o.id===id)?.data.goal||id).join('；')||'未关联')+'</p><p class="small">新资料 '+esc(r.data.new_evidence_ids.join(', '))+'</p>')+'<p class="small">提醒编号 '+esc(r.id)+' · '+esc(r.updated)+'</p>'+(risk?'<p class="small">反馈：'+esc(valueLabels[projectDesk.feedback.find(f=>f.data.alert_id===r.id)?.data.state]||'尚未记录')+'</p><button data-business-feedback="'+r.id+'">记录反馈</button>':'')+'</div>').join(''):'<p class="hint">暂无新的变化提醒。这里检查的是已保存资料，请先确认来源是否已更新。</p>');
 $('business-records').innerHTML=groups;
 document.querySelectorAll('[data-business-edit]').forEach(b=>b.onclick=()=>{let [kind,id]=b.dataset.businessEdit.split(':');$('business-kind').value=kind;businessForm(kind,projectDesk[kind].find(r=>r.id===id));$('business-editor').scrollIntoView({behavior:'smooth'})});
 document.querySelectorAll('[data-business-history]').forEach(b=>b.onclick=async()=>{try{let[kind,id]=b.dataset.businessHistory.split(':');let d=await api('/api/project/history?project_id='+encodeURIComponent(projectDesk.project_id)+'&kind='+kind+'&id='+encodeURIComponent(id));$('business-history').innerHTML=historyHTML(kind,id,d.history)}catch(e){error(e)}});
 document.querySelectorAll('[data-business-feedback]').forEach(b=>b.onclick=()=>{let id=b.dataset.businessFeedback, old=projectDesk.feedback.find(r=>r.id===id);$('business-kind').value='feedback';businessForm('feedback',old||{id,revision:0,data:{alert_id:id,state:'seen',note:''}});$('business-editor').scrollIntoView({behavior:'smooth'})});
}
$('business-open').onclick=openProject;
$('business-new').onclick=()=>{if(!projectDesk)return error('请先打开项目。');businessForm(businessKind())};
$('business-kind').onchange=()=>businessForm(businessKind());
$('business-save').onclick=async()=>{try{
 if(!projectDesk)throw Error('请先打开项目。');let kind=businessKind(),data={};
 for(let[key,,type] of fieldSpec[kind]){let value=$('bf-'+key).value.trim();if(type==='dimension'){data.dimensions??={};data.dimensions[key]=value}else data[key]=type==='bool'?value==='true':type==='list'?value.split(/[,，]/).map(s=>s.trim()).filter(Boolean):type==='lines'?value.split('\n').map(s=>s.trim()).filter(Boolean):value}
 let r=await api('/api/project',{project_id:projectDesk.project_id,command:{kind,id:$('business-id').value.trim(),expected_revision:editingRecord?.revision||0,data}});
 await openProject();$('business-status').textContent='已保存 '+businessLabels[kind]+' '+r.id+'，版本 '+r.revision;
 }catch(e){error(e)}};
$('business-check').onclick=async()=>{try{if(!projectDesk)throw Error('请先打开项目。');let d=await api('/api/project/check',{project_id:projectDesk.project_id});await openProject();$('business-status').textContent='已对比本地资料，新增提醒 '+(d.alerts_created??d.reviews_created)+' 条。此操作未访问外部来源。'}catch(e){error(e)}};
$('business-research').onclick=()=>{if(!projectDesk)return error('请先打开项目。');$('project-id').value=projectDesk.project_id;
let risk=projectDesk.product==='georisk-agent', profile=projectDesk.profile?.[0]?.data;
let rows=risk?projectDesk.exposure.filter(r=>r.data.active).map(r=>r.data):projectDesk.option.map(r=>r.data);
let countries=profile?.countries?.length?profile.countries:rows.flatMap(r=>r.countries||[]);
if(!countries.length&&risk)countries=projectDesk.event.flatMap(r=>r.data.countries||[]);
let topics=(risk?projectDesk.event:projectDesk.assumption).flatMap(r=>r.data.topics||[]);
if(!topics.length&&risk)topics=rows.flatMap(r=>r.topics||[]);
$('countries').value=[...new Set(countries)].join(', ');$('topics').value=[...new Set(topics)].join(', ');
$('context').value='';$('search-queries').value='';$('skill-choice').value='project-continuity';$('question').value=projectDesk.product==='georisk-agent'?'本项目关注的事件有什么新进展？说明哪些业务可能受影响、判断依据是什么，接下来要留意哪些变化；有资料支持时更新事件记录。':'结合企业情况和已有方案，分析当前最需要做的选择。比较各方案的机会、进入条件、成本与约束，说明哪些前提需要验证、下一步先做什么。';$('engine').value=state.model_configured?'model':'demo';openView('work');$('run-status').textContent='已带入本项目的国区和主题，上一项任务的背景与搜索词已清空。补充这次要解决的问题和可公开搜索的关键词后，再点“开始研究”。模型模式会接收本项目资料。'};
$('business-export').onclick=()=>{if(projectDesk)saveBlob(projectDesk,projectDesk.project_id+'-private-project.json')};
$('business-project').oninput=()=>{projectDesk=null;editingRecord=null;$('business-editor').classList.add('hidden');$('business-records').innerHTML='';$('business-notices').innerHTML='';$('business-history').innerHTML='';$('business-status').textContent='请打开当前项目。'};
document.querySelector('[data-view="project-desk"]').addEventListener('click',()=>{if(!$('business-project').value)$('business-project').value=$('project-id').value});
