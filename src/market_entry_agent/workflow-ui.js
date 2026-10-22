// Incremental private project desk; all text from sources and operator data is escaped.
let projectDesk=null, editingRecord=null;
const fieldSpec={
 event:[['title','事件标题'],['subject','事件主体'],['location','地点'],['occurred_at','发生日期（ISO 日期）'],['published_at','本次进展发布日期'],['countries','国区','list'],['topics','主题标签','list'],['summary','来源陈述','area'],['severity','严重程度','low|moderate|high|critical'],['confidence','信息依据','unconfirmed|source_statement|corroborated'],['status','事件状态','tracking|escalated|easing|closed'],['impact','可能影响及不确定性','area'],['next_check','接下来检查什么','area'],['change_note','本次改变了什么','area'],['evidence_ids','公开证据编号','list']],
 exposure:[['name','关注对象名称'],['countries','关注国区（可留空）','list'],['topics','关注主题（可留空）','list'],['min_severity','首次提醒最低严重程度','low|moderate|high|critical'],['active','是否启用','bool'],['note','对象说明（私有）','area']],
 feedback:[['alert_id','提醒编号'],['state','反馈','seen|relevant|irrelevant|handled'],['note','反馈说明','area']],
 profile:[['product','具体产品与用途','area'],['buyer','目标客户与使用场景','area'],['stage','当前阶段','exploring|targeted|operating'],['countries','候选或经营国区','list'],['capabilities','渠道、交付和服务能力','area'],['constraints','已有约束或不能接受的条件','area'],['budget','预算与时间条件（可留空）','area']],
 option:[['name','选项名称'],['countries','目标国区','list'],['mode','进入方式'],['status','当前判断','researching|candidate|selected|deferred|blocked'],['rationale','为什么考虑或暂缓','area'],['demand','需求与买方依据','dimension'],['access','进入条件','dimension'],['channel','渠道与竞争','dimension'],['delivery','交付与售后','dimension'],['economics','成本及经济性假设','dimension'],['risks','风险与待验证事项','dimension'],['evidence_ids','公开证据编号（可留空）','list']],
 assumption:[['statement','方案依赖的经营假设','area'],['status','当前依据','unchecked|supported|challenged|needs_review'],['countries','需监测的国区','list'],['topics','需监测的主题','list'],['option_ids','关联选项编号','list'],['stage_ids','关联阶段编号（可留空）','list'],['evidence_ids','本次判断依据编号（可留空）','list'],['note','判断依据或下一项验证','area']],
 stage:[['goal','阶段目标','area'],['option_id','关联选项编号'],['actions','拟议工作（每行一项）','lines'],['deliverables','交付物（每行一项）','lines'],['completion_signal','怎样判断阶段完成','area'],['depends_on','前置阶段编号（可留空）','list'],['status','进度','planned|doing|blocked|done'],['note','进度说明；完成时填写实际结果','area'],['evidence_ids','相关公开证据编号（可留空）','list']],
 decision:[['title','本次决策'],['rationale','选择及暂缓的理由','area'],['option_ids','相关选项编号','list'],['evidence_ids','公开证据编号（可留空）','list']]
};
const businessLabels={event:'事件',exposure:'经营暴露',feedback:'提醒反馈',profile:'企业画像',option:'进入选项',assumption:'经营假设',stage:'行动阶段',decision:'决策记录'};
const valueLabels={low:'低',moderate:'中',high:'高',critical:'严重',unconfirmed:'尚待确认',source_statement:'来源陈述',corroborated:'有交叉支持的判断',tracking:'跟踪中',escalated:'升级',easing:'缓和',closed:'结束',seen:'已阅',relevant:'有用',irrelevant:'与我无关',handled:'已处理',exploring:'寻找方向',targeted:'已有目标市场',operating:'已进入经营',researching:'研究中',candidate:'候选',selected:'已选择',deferred:'暂缓',blocked:'受阻',unchecked:'待验证',supported:'有支持依据',challenged:'有反向依据',needs_review:'有新资料待研究',planned:'拟议阶段',doing:'进行中',done:'操作者标记完成'};
function businessKind(){return $('business-kind').value}
function businessForm(kind,record=null){
 editingRecord=record;
 $('business-id').value=record?.id||(kind==='profile'?'main':kind==='event'?'auto':'');
 $('business-id').disabled=!!record||kind==='profile';
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
async function openProject(){
 try{let id=$('business-project').value.trim(); let data=await api('/api/project?project_id='+encodeURIComponent(id));if(id!==$('business-project').value.trim())return;projectDesk=data;$('project-id').value=id;renderProject();$('business-status').textContent='已打开私有项目 '+id;}catch(e){error(e)}
}
function renderProject(){
 if(!projectDesk)return;
 let risk=projectDesk.product==='georisk-agent', kinds=risk?['event','exposure','feedback']:['profile','option','assumption','stage','decision'];
 $('business-title').textContent=risk?'事件与经营暴露':'企业进入项目';
 $('business-intro').textContent=risk?'围绕同一事件保存来源和变化，匹配私有关注对象，形成可回看的本地提醒。':'从企业条件开始，比较进入选项，记录方案成立的假设并跟踪行动进度。';
 $('business-kind').innerHTML=kinds.map(k=>'<option value="'+k+'">'+businessLabels[k]+'</option>').join('');
 $('business-editor').classList.add('hidden');
 let groups=kinds.filter(k=>k!=='feedback').map(kind=>'<div class="card"><h2>'+businessLabels[kind]+'</h2>'+(projectDesk[kind].map(r=>'<div class="source"><b>'+esc(r.data.title||r.data.name||r.data.product||r.data.statement||r.data.goal)+'</b> <span class="tag">'+esc(valueLabels[r.data.status]||valueLabels[r.data.stage]||'已保存')+'</span><p>'+esc(r.data.summary||r.data.rationale||r.data.note||r.data.constraints||'')+'</p><p class="small">编号 '+esc(r.id)+' · 版本 '+r.revision+' · '+esc(r.origin==='agent_proposal'?'智能体拟议更新':r.origin==='runtime'?'运行记录':'操作者录入')+'</p><div class="buttons"><button data-business-edit="'+kind+':'+r.id+'">查看与修改</button><button data-business-history="'+kind+':'+r.id+'">版本记录</button></div></div>').join('')||'<p class="hint">尚无记录。</p>')+'</div>').join('');
 if(!risk&&projectDesk.comparison?.length)groups='<div class="card"><h2>进入选项比较</h2><p class="hint">按同一问题比较，不按宏观指数自动排序。画像更新后，请重新研究受影响的选项。</p><div class="table-scroll"><table><tr><th>选项</th><th>需求</th><th>准入</th><th>渠道</th><th>交付</th><th>经济性</th><th>风险</th></tr>'+projectDesk.comparison.map(o=>'<tr><td>'+esc(o.name)+'<br>'+esc(o.countries.join(', ')+' · '+o.mode)+(o.profile_changed?'<br><span class="tag warn">企业条件已更新</span>':'')+'</td>'+['demand','access','channel','delivery','economics','risks'].map(k=>'<td>'+esc(o.dimensions[k]||'待补充')+'</td>').join('')+'</tr>').join('')+'</table></div></div>'+groups;
 let notices=risk?projectDesk.alerts:projectDesk.reviews;
 $('business-notices').innerHTML='<p class="hint">资料时效以来源日期为准；历史记录不代表当前预警。本地检查不会刷新外部来源。</p><h2>'+(risk?'变化提醒':'经营假设更新提醒')+'</h2>'+(notices.length?notices.slice().reverse().map(r=>'<div class="source"><b>'+esc(r.data.title||r.data.statement)+'</b><p>'+esc(risk?r.data.assessment.impact:'有新增匹配资料，需要研究它是否改变原假设；系统没有自动作出法律或商业结论。')+'</p>'+(risk?'<p>关联对象：'+esc(r.data.exposure)+' · '+esc(valueLabels[r.data.severity])+' · '+esc(valueLabels[r.data.status])+'</p><p>下次检查：'+esc(r.data.assessment.next_check)+'</p><p class="small">来源进展日期 '+esc(r.data.published_at)+'；依据 '+esc(r.data.evidence_ids.join(', '))+'</p>':'<p>影响选项：'+esc(r.data.option_ids.map(id=>projectDesk.option.find(o=>o.id===id)?.data.name||id).join('；')||'未关联')+'；阶段：'+esc(r.data.stage_ids.map(id=>projectDesk.stage.find(o=>o.id===id)?.data.goal||id).join('；')||'未关联')+'</p><p class="small">新资料 '+esc(r.data.new_evidence_ids.join(', '))+'</p>')+'<p class="small">提醒编号 '+esc(r.id)+' · '+esc(r.updated)+'</p>'+(risk?'<p class="small">反馈：'+esc(valueLabels[projectDesk.feedback.find(f=>f.data.alert_id===r.id)?.data.state]||'尚未记录')+'</p><button data-business-feedback="'+r.id+'">记录反馈</button>':'')+'</div>').join(''):'<p class="hint">尚无本地变化提醒。没有提醒不代表外部没有事件；请确认资料更新和来源覆盖。</p>');
 $('business-records').innerHTML=groups;
 document.querySelectorAll('[data-business-edit]').forEach(b=>b.onclick=()=>{let [kind,id]=b.dataset.businessEdit.split(':');$('business-kind').value=kind;businessForm(kind,projectDesk[kind].find(r=>r.id===id));$('business-editor').scrollIntoView({behavior:'smooth'})});
 document.querySelectorAll('[data-business-history]').forEach(b=>b.onclick=async()=>{try{let[kind,id]=b.dataset.businessHistory.split(':');let d=await api('/api/project/history?project_id='+encodeURIComponent(projectDesk.project_id)+'&kind='+kind+'&id='+encodeURIComponent(id));$('business-history').innerHTML='<h3>版本记录 · '+esc(id)+'</h3>'+d.history.map(r=>'<details><summary>版本 '+r.revision+' · '+esc(r.updated)+'</summary><pre>'+esc(JSON.stringify(r.data,null,2))+'</pre></details>').join('')}catch(e){error(e)}});
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
$('business-check').onclick=async()=>{try{if(!projectDesk)throw Error('请先打开项目。');let d=await api('/api/project/check',{project_id:projectDesk.project_id});await openProject();$('business-status').textContent='已检查保存资料，新增提醒 '+(d.alerts_created??d.reviews_created)+' 条。此操作未访问外部来源。'}catch(e){error(e)}};
$('business-research').onclick=()=>{if(!projectDesk)return error('请先打开项目。');$('project-id').value=projectDesk.project_id;
let risk=projectDesk.product==='georisk-agent', profile=projectDesk.profile?.[0]?.data;
let rows=risk?projectDesk.exposure.filter(r=>r.data.active).map(r=>r.data):projectDesk.option.map(r=>r.data);
let countries=profile?.countries?.length?profile.countries:rows.flatMap(r=>r.countries||[]);
if(!countries.length&&risk)countries=projectDesk.event.flatMap(r=>r.data.countries||[]);
let topics=(risk?projectDesk.event:projectDesk.assumption).flatMap(r=>r.data.topics||[]);
if(!topics.length&&risk)topics=rows.flatMap(r=>r.topics||[]);
$('countries').value=[...new Set(countries)].join(', ');$('topics').value=[...new Set(topics)].join(', ');
$('context').value='';$('search-queries').value='';$('skill-choice').value='project-continuity';$('question').value=projectDesk.product==='georisk-agent'?'检查本项目事件的新进展，说明经营暴露和可观察条件；有来源支持时按项目合同保存事件更新。':'结合本项目企业条件和现有进入选项，研究当前决策，提出可比较的选项、经营假设和阶段计划。';$('engine').value=state.model_configured?'model':'demo';openView('work');$('run-status').textContent='已带入项目国区和主题，并清空上一项任务的背景与公开查询。请补充本次要求及允许发送的公开关键词；模型模式会接收本项目资料。'};
$('business-export').onclick=()=>{if(projectDesk)saveBlob(projectDesk,projectDesk.project_id+'-private-project.json')};
$('business-project').oninput=()=>{projectDesk=null;editingRecord=null;$('business-editor').classList.add('hidden');$('business-records').innerHTML='';$('business-notices').innerHTML='';$('business-history').innerHTML='';$('business-status').textContent='请打开当前项目。'};
document.querySelector('[data-view="project-desk"]').addEventListener('click',()=>{if(!$('business-project').value)$('business-project').value=$('project-id').value});
