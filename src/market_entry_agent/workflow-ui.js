// Incremental private project desk; all text from sources and operator data is escaped.
let projectDesk=null, editingRecord=null, projectOverview=null;
const fieldSpec={
 event:[['title','事件名称'],['subject','事件主体'],['location','地点'],['occurred_at','事件发生日期（如 2024-02-18）'],['published_at','本次进展发布日期'],['countries','国区','list'],['topics','主题标签','list'],['summary','来源怎么说','area'],['severity','严重程度','low|moderate|high|critical'],['confidence','信息依据','unconfirmed|source_statement|corroborated'],['status','事件状态','tracking|escalated|easing|closed'],['impact','可能影响及不确定性','area'],['next_check','接下来检查什么','area'],['change_note','本次改变了什么','area'],['evidence_ids','来源编号','list'],['entity_keys','关联业务对象编号（可留空）','list']],
 exposure:[['name','关注对象名称'],['countries','关注国区（可留空）','list'],['topics','关注主题（可留空）','list'],['min_severity','达到什么程度开始提醒','low|moderate|high|critical'],['active','是否启用','bool'],['note','对象说明（私有）','area'],['object_type','对象类型','other|route|port|supplier|project|country'],['entity_keys','关联对象编号（如 port-jebel-ali）','list'],['deadline','关键业务日期（可留空）'],['importance','业务重要程度','medium|low|high']],
 event_alias:[['subject','别名中的事件主体'],['location','别名地点'],['occurred_at','同一事件的发生日期'],['target_event_id','对应的主事件编号'],['reason','为什么确认是同一事件','area']],
 event_merge:[['source_id','待合并事件编号（也填作本记录编号）'],['target_id','保留的主事件编号'],['reason','合并原因；旧历史继续保留','area']],
 feedback:[['alert_id','提醒编号'],['state','反馈','seen|relevant|irrelevant|handled'],['note','反馈说明','area']],
 profile:[['product','具体产品与用途','area'],['buyer','目标客户与使用场景','area'],['stage','当前阶段','exploring|targeted|operating'],['countries','候选或经营国区','list'],['capabilities','渠道、交付和服务能力','area'],['constraints','已有约束或不能接受的条件','area'],['budget','预算与时间条件（可留空）','area']],
 option:[['name','选项名称'],['countries','目标国区','list'],['mode','进入方式'],['status','当前判断','researching|candidate|selected|deferred|blocked'],['rationale','为什么考虑或暂缓','area'],['tradeoff','采用它需要接受什么取舍（可留空）','area'],['requirements','需要的资源和条件（可留空）','area'],['next_validation','先验证什么、为什么先做（可留空）','area'],['demand','需求与买方依据','dimension'],['access','进入条件','dimension'],['channel','渠道与竞争','dimension'],['delivery','交付与售后','dimension'],['economics','成本及经济性假设','dimension'],['risks','风险与待验证事项','dimension'],['evidence_ids','来源编号（可留空）','list']],
 assumption:[['statement','方案依赖的关键假设','area'],['status','当前依据','unchecked|supported|challenged|needs_review'],['countries','需监测的国区','list'],['topics','需监测的主题','list'],['option_ids','关联选项编号','list'],['stage_ids','关联阶段编号（可留空）','list'],['evidence_ids','本次判断依据编号（可留空）','list'],['note','判断依据或下一项验证','area'],['blocking','不解决就无法推进','bool'],['decision_impact','对选择的影响','medium|high|low'],['effort','验证投入','medium|low|high'],['validation_owner','由谁去验证'],['next_test','取得什么资料','area'],['if_supported','得到支持后怎么选','area'],['if_not','不成立时怎么调整','area']],
 stage:[['goal','阶段目标','area'],['option_id','关联选项编号'],['actions','计划做什么（每行一项）','lines'],['deliverables','交付物（每行一项）','lines'],['completion_signal','怎样判断阶段完成','area'],['depends_on','前置阶段编号（可留空）','list'],['status','进度','planned|doing|blocked|done'],['note','进度说明；完成时填写实际结果','area'],['evidence_ids','相关来源编号（可留空）','list']],
 transaction:[['name','交易安排名称'],['option_id','关联方案编号'],['manufacturer','生产方与所在国'],['exporter','出口方与所在国'],['seller','合同卖方与所在国'],['importer','进口申报主体与所在国'],['buyer','客户与所在国'],['incoterm','约定贸易术语（未知可留空）'],['responsibility_note','税费、单证与履约责任；未确认处请说明','area']],
 economics:[['name','测算名称'],['option_id','关联方案编号'],['currency','统一币种（三位代码，如 USD）'],['unit','数量单位，如 台 或 吨'],['quantity','数量','economic'],['unit_price','单位售价','economic'],['unit_cost','单位产品成本','economic'],['freight','整笔运输费','economic'],['insurance','整笔保险费','economic'],['customs_value','明确口径的完税基数','economic'],['duty_rate','关税比例（如 0.05）','economic'],['channel_fee','整笔渠道费用','economic'],['fixed_cost','本方案其他固定费用','economic'],['recoverable_tax','可抵扣税款的现金占用','economic']],
 decision:[['title','本次决策'],['rationale','选择及暂缓的理由','area'],['option_ids','相关选项编号','list'],['evidence_ids','来源编号（可留空）','list']]
};
const businessLabels={event:'事件',event_alias:'事件别名',event_merge:'合并事件',transaction:'交易责任',economics:'报价与测算',exposure:'关注对象',feedback:'提醒反馈',profile:'企业情况',option:'进入方案',assumption:'关键假设',stage:'推进计划',decision:'决策记录'};
const valueLabels={medium:'中',other:'其他',route:'航线',port:'港口',supplier:'供应商',project:'项目',country:'国区',low:'低',moderate:'中',high:'高',critical:'严重',unconfirmed:'尚待确认',source_statement:'来源有说明，待交叉核实',corroborated:'多份资料相互支持',tracking:'跟踪中',escalated:'升级',easing:'缓和',closed:'结束',seen:'已阅',relevant:'有用',irrelevant:'与我无关',handled:'已处理',exploring:'寻找方向',targeted:'已有目标市场',operating:'已进入经营',researching:'研究中',candidate:'候选',selected:'已选择',deferred:'暂缓',blocked:'受阻',unchecked:'待验证',supported:'有支持依据',challenged:'有反向依据',needs_review:'有新资料，待判断',planned:'待开始（建议计划）',doing:'进行中',done:'已完成（由你记录）'};
function attentionBand(value){return {urgent:'优先处理',watch:'持续关注',routine:'常规留意'}[value]||value||'待判断'}
function attentionReason(value){return {'Operator deadline has passed':'已超过填写的关键日期','Operator deadline within seven days':'距关键日期不超过7天','Operator deadline more than seven days away':'距关键日期超过7天'}[value]||(value.startsWith('Event severity: ')?'事件严重程度：'+(valueLabels[value.slice(16)]||value.slice(16)):value.startsWith('Operator importance: ')?'业务重要程度：'+({low:'低',medium:'中',high:'高'}[value.slice(21)]||value.slice(21)):value)}
function economicNames(keys){const labels=Object.fromEntries(fieldSpec.economics.map(([k,label])=>[k,label]));return keys.map(k=>labels[k]||k).join('、')}
function businessKind(){return $('business-kind').value}
function businessForm(kind,record=null){
 editingRecord=record;
 $('business-id').value=record?.id||(kind==='profile'?'main':kind==='event'?'auto':'');
 $('business-id').disabled=!!record||kind==='profile';
 $('business-id-hint').textContent=record?'这条记录的编号已固定。保存修改会留下新版本，原内容仍可在“修改记录”中查看。':kind==='feedback'?'反馈编号与提醒编号相同；保存后可继续补充处理说明。':kind==='event'?'保留 auto，会按主体、地点和发生日期识别同一事件。来源编号可在“证据与来源”中查看。':kind==='profile'?'企业情况固定使用 main，每次修改都会保留旧版本。':'为这条记录取一个固定编号，如 route-red-sea 或 germany-distributor。后续关联方案、假设和计划时会用到它。';
 $('business-editor-title').textContent=(record?'修改':'新增')+(businessLabels[kind]||kind);
 $('business-fields').innerHTML=fieldSpec[kind].map(([key,label,type])=>{
  let value=record?.data?.[key]??(type==='dimension'?record?.data?.dimensions?.[key]:undefined)??(type==='economic'?record?.data?.values?.[key]:undefined)??(type==='bool'?(key==='blocking'?false:true):'');
  let id='bf-'+key, control;
  if(type==='economic'){let row=value&&typeof value==='object'?value:null;control='<input id="'+id+'" value="'+esc(row?.value??'')+'" placeholder="未知留空；为零需填 0"><select aria-label="'+esc(label+'的依据')+'" id="'+id+'-basis"><option value="assumption">测算假设</option><option value="operator_quote" '+(row?.basis==='operator_quote'?'selected':'')+'>已取得的报价</option></select><input aria-label="'+esc(label+'的依据说明')+'" id="'+id+'-note" value="'+esc(row?.note??'')+'" placeholder="报价来源或假设依据">'}
  else if(type==='bool')control='<select id="'+id+'"><option value="true" '+(value===true?'selected':'')+'>启用</option><option value="false" '+(value===false?'selected':'')+'>停用</option></select>';
  else if(type?.includes('|'))control='<select id="'+id+'">'+type.split('|').map(v=>'<option value="'+v+'" '+(v===value?'selected':'')+'>'+esc(valueLabels[v]||v)+'</option>').join('')+'</select>';
  else if(['area','dimension','lines'].includes(type))control='<textarea id="'+id+'">'+esc(Array.isArray(value)?value.join('\n'):value)+'</textarea>';
  else control='<input id="'+id+'" value="'+esc(Array.isArray(value)?value.join(', '):value)+'">';
  return '<div><label for="'+id+'">'+esc(label)+'</label>'+control+'</div>';
 }).join('');
 $('business-editor').classList.remove('hidden');
}
function historyFields(kind,data){
 const specs=fieldSpec[kind]||[], labels={revenue:'销售收入',goods_cost:'产品成本',duty:'关税',operating_cost:'已列费用合计',contribution_before_other_costs:'扣除已列费用后的贡献额',cash_outlay_including_recoverable_tax:'含可抵扣税款的现金支出',contribution_margin:'贡献额占收入比例',...Object.fromEntries(specs.map(([key,label])=>[key,label]))};
 const value=(key,v)=>{
  if(v===null||v===undefined||v==='')return '未填写';
  if(typeof v==='boolean')return v?'启用':'停用';
  if(Array.isArray(v))return v.length?v.map(x=>value(key,x)).join('；'):'未填写';
  if(typeof v==='object')return Object.entries(v).map(([k,x])=>(labels[k]||k)+'：'+value(k,x)).join('；');
  if(kind==='economics'&&['revenue','goods_cost','duty','operating_cost','contribution_before_other_costs','cash_outlay_including_recoverable_tax','contribution_margin'].includes(key)&&Number.isFinite(Number(v)))return key==='contribution_margin'?(Number(v)*100).toFixed(2)+'%':Number(v).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
  return ['status','stage','confidence','severity','min_severity','state'].includes(key)?valueLabels[v]||String(v):String(v);
 };
 return '<dl>'+Object.entries(data).map(([key,v])=>'<dt><b>'+esc(labels[key]||(key==='dimensions'?'方案比较':key))+'</b></dt><dd style="white-space:pre-wrap;margin:6px 0 14px">'+esc(value(key,v))+'</dd>').join('')+'</dl>';
}
function historyHTML(kind,id,history){
 return '<h3>修改记录 · '+esc(id)+'</h3>'+history.map(r=>'<details><summary>第 '+r.revision+' 版 · '+esc(r.updated)+'</summary>'+historyFields(kind,r.data)+'<details><summary>查看原始 JSON</summary><pre>'+esc(JSON.stringify(r.data,null,2))+'</pre></details></details>').join('');
}
async function openProject(){
 try{let id=$('business-project').value.trim(); let [data,health]=await Promise.all([api('/api/project?project_id='+encodeURIComponent(id)),api('/api/source-health')]);if(id!==$('business-project').value.trim())return;projectDesk=data;state.source_health=health;$('project-id').value=id;$('lc-project').value=id;if(typeof syncProject==='function')syncProject();renderProject();if(typeof loadKnowledge==='function')await loadKnowledge();await loadResearchDesk(id);if(id!==$('business-project').value.trim())return;$('business-status').textContent='已打开私有项目 '+id;}catch(e){error(e)}
}
function renderProject(){
 if(!projectDesk)return;
 let risk=projectDesk.product==='georisk-agent', kinds=risk?['event','exposure','event_alias','event_merge','feedback']:['profile','option','transaction','economics','assumption','stage','decision'];
 $('business-title').textContent=risk?'事件跟踪与业务影响':'市场选择与落地计划';
 $('business-intro').textContent=risk?'记下你关注的人员、资产、航线或业务，跟踪相关事件的进展、可能影响，以及接下来要留意的变化。':'先说清产品、客户和经营条件，再比较去哪里、怎么进入，记录需要验证的前提和下一步工作。';
 $('business-kind').innerHTML=kinds.map(k=>'<option value="'+k+'">'+businessLabels[k]+'</option>').join('');
 $('business-editor').classList.add('hidden');
 let groups=kinds.filter(k=>k!=='feedback').map(kind=>'<div class="card"><h2>'+businessLabels[kind]+'</h2>'+(projectDesk[kind].map(r=>'<div class="source"><b>'+esc(r.data.title||r.data.name||r.data.product||r.data.statement||r.data.goal||r.data.subject||r.data.source_id||r.id)+'</b> <span class="tag">'+esc(valueLabels[r.data.status]||valueLabels[r.data.stage]||'已保存')+'</span><p>'+esc(r.data.summary||r.data.rationale||r.data.note||r.data.constraints||'')+'</p><p class="small">编号 '+esc(r.id)+' · 版本 '+r.revision+' · '+esc(r.origin==='agent_proposal'?'智能体建议':r.origin==='runtime'?'运行记录':'你录入的资料')+'</p><div class="buttons"><button data-business-edit="'+kind+':'+r.id+'">查看与修改</button><button data-business-history="'+kind+':'+r.id+'">修改记录</button></div></div>').join('')||'<p class="hint">尚无记录。</p>')+'</div>').join('');
 let optionDetails=(!risk&&projectDesk.comparison?.length)?'<div class="card"><h2>方案取舍与下一步</h2>'+projectDesk.comparison.map(o=>'<div class="source"><b>'+esc(o.name)+'</b><p>主要取舍：'+esc(o.tradeoff||'待研究')+'</p><p>需要具备：'+esc(o.requirements||'待补充资源和条件')+'</p><p>先验证：'+esc(o.next_validation||'待确定验证顺序')+'</p></div>').join('')+'</div>':'';
 if(!risk&&projectDesk.comparison?.length)groups='<div class="card"><h2>进入方案比较</h2><p class="hint">从需求、准入、渠道、交付、成本和风险六方面比较方案。国区指数可作背景参考；企业条件改变后，需要重新判断方案是否合适。</p><div class="table-scroll"><table><tr><th>选项</th><th>需求</th><th>准入</th><th>渠道</th><th>交付</th><th>经济性</th><th>风险</th></tr>'+projectDesk.comparison.map(o=>'<tr><td>'+esc(o.name)+'<br>'+esc(o.countries.join(', ')+' · '+o.mode)+(o.profile_changed?'<br><span class="tag warn">企业条件已更新</span>':'')+'</td>'+['demand','access','channel','delivery','economics','risks'].map(k=>'<td>'+esc(o.dimensions[k]||'待补充')+'</td>').join('')+'</tr>').join('')+'</table></div></div>'+optionDetails+groups;
 if(!risk&&projectDesk.economic_scenarios?.length)groups+=economicsHTML(projectDesk.economic_scenarios);
 if(!risk&&projectDesk.validation_queue?.length)groups+='<div class="card"><h2>先验证什么</h2>'+projectDesk.validation_queue.map(r=>'<div class="source"><b>'+r.rank+' · '+esc(r.statement)+'</b><p>'+esc(r.next_test||r.note||'待明确下一步')+'</p><p class="hint">阻断推进：'+(r.why_ranked.blocking?'是':'否')+'；对选择影响：'+esc(valueLabels[r.why_ranked.decision_impact]||r.why_ranked.decision_impact)+'；验证投入：'+esc(valueLabels[r.why_ranked.effort]||r.why_ranked.effort)+'</p><p>得到支持：'+esc(r.if_supported||'待补充')+'；不成立：'+esc(r.if_not||'待补充')+'</p></div>').join('')+'</div>';
 if(risk&&projectDesk.attention_queue?.length)groups+='<div class="card"><h2>本地检查后的关注顺序</h2><p class="hint">按最近保存的严重程度、业务重要性和关键日期排序。历史提醒仍保留在下方，请结合资料日期使用。</p>'+projectDesk.attention_queue.map(r=>'<div class="source"><b>'+esc(r.data.title)+' · '+esc(r.data.exposure)+'</b><p>'+esc(attentionBand(r.data.priority?.band||'watch'))+' · '+esc((r.data.priority?.reasons||[]).map(attentionReason).join('；'))+'</p></div>').join('')+'</div>';
 let notices=risk?projectDesk.alerts:projectDesk.reviews;
 $('business-source-health').innerHTML=sourceHealthHTML(state.source_health);
 $('business-notices').innerHTML='<p class="hint">资料时效以来源日期为准；历史记录不代表当前预警。本地检查不会刷新外部来源。</p><h2>'+(risk?'变化提醒':'关键假设的新资料')+'</h2>'+(notices.length?notices.slice().reverse().map(r=>'<div class="source"><b>'+esc(r.data.title||r.data.statement)+'</b><p>'+esc(risk?r.data.assessment.impact:'发现了与这条假设相关的新资料。请结合原方案判断：前提是否改变，哪些工作需要调整。资料匹配本身还不能说明政策适用或方案失效。')+'</p>'+(risk?changeHTML(r.data)+'<p>处理顺序：'+esc(attentionBand(r.data.priority?.band))+'；'+esc((r.data.priority?.reasons||[]).map(attentionReason).join('；'))+'</p><p>关联对象：'+esc(r.data.exposure)+' · '+esc(valueLabels[r.data.severity])+' · '+esc(valueLabels[r.data.status])+'</p><p>接下来关注：'+esc(r.data.assessment.next_check)+'</p><p class="small">资料发布日期 '+esc(r.data.published_at)+'；来源 '+esc(r.data.evidence_ids.join(', '))+'</p>':'<p>关联方案：'+esc(r.data.option_ids.map(id=>projectDesk.option.find(o=>o.id===id)?.data.name||id).join('；')||'未关联')+'；阶段：'+esc(r.data.stage_ids.map(id=>projectDesk.stage.find(o=>o.id===id)?.data.goal||id).join('；')||'未关联')+'</p><p class="small">新资料 '+esc(r.data.new_evidence_ids.join(', '))+'</p>')+'<p class="small">提醒编号 '+esc(r.id)+' · '+esc(r.updated)+'</p>'+(risk?'<p class="small">反馈：'+esc(valueLabels[projectDesk.feedback.find(f=>f.data.alert_id===r.id)?.data.state]||'尚未记录')+'</p><button data-business-feedback="'+r.id+'">记录反馈</button>':'')+'</div>').join(''):'<p class="hint">暂无新的变化提醒。这里检查的是已保存资料，请先确认来源是否已更新。</p>');
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
 for(let[key,,type] of fieldSpec[kind]){let value=$('bf-'+key).value.trim();if(type==='economic'){data.values??={};data.values[key]=value===''?null:{value,basis:$('bf-'+key+'-basis').value,note:$('bf-'+key+'-note').value.trim()}}else if(type==='dimension'){data.dimensions??={};data.dimensions[key]=value}else data[key]=type==='bool'?value==='true':type==='list'?value.split(/[,，]/).map(s=>s.trim()).filter(Boolean):type==='lines'?value.split('\n').map(s=>s.trim()).filter(Boolean):value}
 let r=await api('/api/project',{project_id:projectDesk.project_id,command:{kind,id:$('business-id').value.trim(),expected_revision:editingRecord?.revision||0,data}});
 await openProject();$('business-status').textContent='已保存 '+businessLabels[kind]+' '+r.id+'，版本 '+r.revision;
 }catch(e){error(e)}};
$('business-check').onclick=async()=>{try{if(!projectDesk)throw Error('请先打开项目。');let d=await api('/api/project/check',{project_id:projectDesk.project_id});await openProject();$('business-status').textContent='已对比本地资料，新增提醒 '+(d.alerts_created??d.reviews_created)+' 条。此操作未访问外部来源。'}catch(e){error(e)}};
$('business-research').onclick=()=>{if(!projectDesk)return error('请先打开项目。');$('project-id').value=projectDesk.project_id;
let risk=projectDesk.product==='georisk-agent', profile=projectDesk.profile?.[0]?.data;
let prior=projectOverview?.project_id===projectDesk.project_id?(projectOverview.recent.find(r=>r.engine==='model'&&r.state==='completed')||projectOverview.recent[0]):null;
let rows=risk?projectDesk.exposure.filter(r=>r.data.active).map(r=>r.data):projectDesk.option.map(r=>r.data);
let countries=profile?.countries?.length?profile.countries:rows.flatMap(r=>r.countries||[]);
if(!countries.length&&risk)countries=projectDesk.event.flatMap(r=>r.data.countries||[]);
let topics=(risk?projectDesk.event:projectDesk.assumption).flatMap(r=>r.data.topics||[]);
if(!topics.length&&risk)topics=rows.flatMap(r=>r.topics||[]);
if(!countries.length&&prior)countries=prior.countries||[];if(!topics.length&&prior)topics=prior.topics||[];
$('countries').value=[...new Set(countries)].join(', ');$('topics').value=[...new Set(topics)].join(', ');
$('context').value='';$('search-queries').value='';$('skill-choice').value='project-continuity';$('question').value=projectDesk.product==='georisk-agent'?'本项目关注的事件有什么新进展？说明哪些业务可能受影响、判断依据是什么，接下来要留意哪些变化；有资料支持时更新事件记录。':'结合企业情况和已有方案，分析当前最需要做的选择。比较各方案的机会、进入条件、成本与约束，说明哪些前提需要验证、下一步先做什么。';if(prior?.task_mode){$('task-mode').value=prior.task_mode;if(['topic-research','event-tracking'].includes(prior.task_mode))$('question').value='接着本项目的研究继续：\n'+Array.from(prior.question).slice(0,1500).join('')+'\n围绕已有解释、仍需检验的问题和下一步取材展开，不虚构企业背景。';}for(const option of [...($('knowledge-choice').options||[])])option.selected=(prior?.knowledge_ids||[]).includes(option.value);for(const id of ['public-terms','public-facets','external-search-profile'])if($(id))$(id).value='';if($('research-depth'))$('research-depth').checked=false;$('engine').value=state.model_configured?'model':'demo';openView('work');$('run-status').textContent='已带入本项目的国区和主题，上一项任务的背景与搜索词已清空。补充这次要解决的问题和可公开搜索的关键词后，再点“开始研究”。模型模式会接收本项目资料。'};
$('business-export').onclick=()=>{if(projectDesk)saveBlob(projectDesk,projectDesk.project_id+'-private-project.json')};
$('business-project').oninput=()=>{projectDesk=null;projectOverview=null;editingRecord=null;$('business-editor').classList.add('hidden');$('business-records').innerHTML='';$('business-notices').innerHTML='';$('business-history').innerHTML='';$('business-overview').innerHTML='';$('business-status').textContent='请打开当前项目。'};
document.querySelector('[data-view="project-desk"]').addEventListener('click',()=>{if(!$('business-project').value)$('business-project').value=$('project-id').value});

function projectSourceLinks(rows){
 return (rows||[]).map(s=>'<details class="source"><summary><a target="_blank" rel="noopener noreferrer" href="'+esc(safeLink(s.url))+'">'+esc(s.title)+'</a> · '+esc(s.published_at||'发布日期待补')+'</summary><p class="small">已保存资料摘录（不代表已读取完整原文）</p><p>'+esc(s.saved_excerpt||'')+'</p><p class="small">'+esc(s.id)+'</p></details>').join('');
}
function changeHTML(data){
 const labels={severity:'严重程度',status:'事件状态',confidence:'信息依据',impact:'业务影响',next_check:'接下来关注'};
 let diffs=data.changes||Object.keys(labels).filter(k=>(data.previous||{})[k]!==data.assessment[k]).map(k=>({field:k,before:(data.previous||{})[k],after:data.assessment[k]}));
 return '<h3>'+(data.previous?'与上次相比':'首次记录')+'</h3><div class="table-scroll"><table><tr><th>判断</th><th>上次</th><th>本次</th></tr>'+diffs.map(d=>'<tr><td>'+esc(labels[d.field]||d.field)+'</td><td>'+esc(valueLabels[d.before]||d.before||'首次记录')+'</td><td>'+esc(valueLabels[d.after]||d.after)+'</td></tr>').join('')+'</table></div>'+(data.change_note?'<p>变化说明：'+esc(data.change_note)+'</p>':'')+'<p class="small">本次新增来源 '+esc((data.new_evidence_ids||[]).join(', ')||'无新增编号；判断可能依据已有资料更新')+'</p>'+projectSourceLinks(data.source_details);
}
function decisionHTML(report){
 let html=report.business_context?.length?'<h3>业务背景与推断</h3><ul>'+report.business_context.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'';
 for(const row of report.project_changes||[])html+='<div class="card"><h3>本次变化与业务影响</h3><b>'+esc(row.data.title+' · '+row.data.exposure)+'</b>'+changeHTML(row.data)+'</div>';
 if(report.decision_options?.length)html+='<h3>方案取舍</h3><div class="table-scroll"><table><tr><th>方案</th><th>适合的条件</th><th>主要取舍</th><th>需要具备</th><th>先验证</th></tr>'+report.decision_options.map(o=>'<tr>'+['name','fit','tradeoff','requirements','next_check'].map(k=>'<td>'+esc(o[k])+'</td>').join('')+'</tr>').join('')+'</table></div>';
 if(report.validation_priorities?.length)html+='<h3>先验证什么</h3>'+report.validation_priorities.map(p=>'<div class="source"><b>'+esc(p.question)+'</b><p>为什么先做：'+esc(p.why_first)+'</p><p>下一步：'+esc(p.next_step)+'</p><p>若得到支持：'+esc(p.if_supported)+'</p><p>若不成立：'+esc(p.if_not)+'</p></div>').join('');
 return html;
}
function decisionText(report){
 let out=report.business_context?.length?'\n\n## 业务背景与推断\n'+report.business_context.map(x=>'- '+x).join('\n'):'';
 for(const r of report.project_changes||[]){const d=r.data;out+='\n\n## 本次变化与业务影响\n'+d.title+' · '+d.exposure+'\n'+(d.changes||[]).map(x=>'- '+({severity:'严重程度',status:'事件状态',confidence:'信息依据',impact:'业务影响',next_check:'接下来关注'}[x.field]||x.field)+'：'+(valueLabels[x.before]||x.before||'首次记录')+' → '+(valueLabels[x.after]||x.after)).join('\n')+'\n变化说明：'+(d.change_note||'')+'\n'+(d.source_details||[]).map(s=>'- 来源：'+s.title+' '+s.url+' ['+s.id+']').join('\n');}
 if(report.decision_options?.length)out+='\n\n## 方案取舍\n'+report.decision_options.map(o=>'### '+o.name+'\n适合的条件：'+o.fit+'\n主要取舍：'+o.tradeoff+'\n需要具备：'+o.requirements+'\n先验证：'+o.next_check+'\n依据：'+(o.evidence_ids||[]).join(', ')).join('\n\n');
 if(report.validation_priorities?.length)out+='\n\n## 先验证什么\n'+report.validation_priorities.map(p=>'### '+p.question+'\n为什么先做：'+p.why_first+'\n下一步：'+p.next_step+'\n若得到支持：'+p.if_supported+'\n若不成立：'+p.if_not+'\n依据：'+(p.evidence_ids||[]).join(', ')).join('\n\n');
 return out;
}
function sourceHealthHTML(health){
 if(!health)return '';
 const labels={fresh:'在刷新间隔内',stale:'已超过刷新间隔',never_fetched:'尚无成功获取记录'};
 return '<div class="card"><h2>来源更新情况</h2><p>已登记 '+health.registered+' 个来源 · '+health.fresh+' 个在刷新间隔内 · '+health.latest_failed+' 个最近尝试失败</p><p class="hint">这里统计整个工作空间已登记来源的获取状态，未按当前项目筛选。获取成功不等于已核实内容，也不代表全网覆盖。</p>'+health.sources.map(s=>'<div class="source"><b>'+esc(s.title)+'</b> <span class="tag">'+esc(labels[s.freshness])+'</span><p class="small">最近成功获取：'+esc(s.last_success||'暂无')+'；最近尝试：'+esc(s.last_attempt||'暂无')+'</p><p class="small">刷新间隔 '+esc(s.refresh_hours)+' 小时'+(s.cached?'；本次使用缓存，未重新获取':'')+(s.latest_attempt_failed?'；最近获取失败：'+esc(s.last_error):'')+'</p></div>').join('')+'</div>';
}

function reportProse(value){
 return String(value||'').split(/\n\s*\n/).filter(p=>p.trim()).map(p=>'<p>'+esc(p).replace(/\n/g,'<br>')+'</p>').join('');
}

function economicsHTML(rows){
 const metrics=[['revenue','销售收入'],['goods_cost','产品成本'],['duty','关税'],['operating_cost','已列费用合计'],['contribution_before_other_costs','扣除已列费用后的贡献额'],['cash_outlay_including_recoverable_tax','含可抵扣税款的现金支出'],['contribution_margin','贡献额占收入比例']];
 const format=(k,v)=>v===null||v===undefined?'未填写':Number.isFinite(Number(v))?(k==='contribution_margin'?(Number(v)*100).toFixed(2)+'%':Number(v).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})):String(v);
 return '<div class="card"><h2>报价情景测算</h2><p class="hint">各情景使用表头所示币种；不同币种不直接比较。缺项保留为空，贡献额尚未扣除未列费用。页面保留两位小数，导出保留计算原值。</p><div class="table-scroll"><table><tr><th>测算项目</th>'+rows.map(r=>'<th>'+esc(r.name)+'<br>'+esc(r.currency)+'</th>').join('')+'</tr>'+metrics.map(([k,label])=>'<tr><td>'+esc(label)+'</td>'+rows.map(r=>'<td>'+esc(format(k,r.calculation.metrics[k]))+'</td>').join('')+'</tr>').join('')+'</table></div>'+rows.map(r=>'<details class="source"><summary>'+esc(r.name)+' · 输入依据</summary><p>未填项目：'+esc(economicNames(r.calculation.missing)||'无')+'</p><p>采用假设：'+esc(economicNames(r.calculation.assumptions)||'无')+'</p></details>').join('')+'</div>';
}

/* Project-scoped saved research. Actions reopen records; nothing runs automatically. */
async function loadResearchDesk(project){
 const target=$('business-overview');target.textContent='正在读取本项目的研究记录…';
 try{const d=await api('/api/desk/overview?project_id='+encodeURIComponent(project));if(project!==$('business-project').value.trim())return;
 if(!Array.isArray(d.recent)||!Array.isArray(d.collections))throw Error('研究档案格式不可用');projectOverview=d;
 const risk=state.product.id==='georisk-agent';
 target.innerHTML='<h2>'+(risk?'议题研究档案':'方案研究档案')+'</h2><p class="hint">本项目已保存的材料与判断；不会自动刷新来源或调整已有选择。</p>'+
 '<p>知识库 '+d.collections.length+' 个 · 持续关注 '+d.monitors.filter(m=>m.state==='active').length+' 项 · 最近研究 '+d.recent.length+' 项'+(d.has_more_runs?'（还有更早记录）':'')+'</p>'+
 d.recent.map(r=>'<div class="source"><b>'+esc(r.title||r.question)+'</b><p>'+esc(r.summary?r.summary.slice(0,360)+(r.summary.length>360?'…':''):'任务尚未保存报告。')+'</p><p class="hint">'+esc(r.updated)+' · '+esc(({completed:'已保存',running:'运行中',queued:'等待处理',failed:'失败，可查看记录',paused:'已暂停',cancelled:'已取消'})[r.state]||r.state)+'</p><button data-desk-run="'+esc(r.id)+'">打开任务与报告</button></div>').join('')+
 '<h3>仍在研究的问题</h3>'+list(d.open_questions.map(q=>q.text))+
 Object.entries(d.memory).filter(([k,v])=>v.length).map(([kind,rows])=>'<h3>'+esc(({source_fact:'来源陈述',hypothesis:'假设',judgment:'已有判断',decision_proposal:'拟议方案',operator_decision:'你的决定'})[kind])+'</h3>'+list(rows.map(r=>r.text))).join('')+
 '<h3>最近报告的来源</h3>'+d.sources.map(s=>'<div class="source"><b>'+esc(s.title||s.id)+'</b><p class="hint">'+esc(s.published_at||'发布日期未提供')+' · '+esc(({document_text:'本地文档文字',page_text:'已获取网页正文',attributed_public_summary:'署名摘要',search_snippet:'搜索摘要，供发现来源'})[s.retrieval_kind]||s.retrieval_kind||'来源类型未提供')+(s.document_location?' · '+esc(savedSourcePlace(s.document_location)):'')+'</p></div>').join('');
 target.querySelectorAll('[data-desk-run]').forEach(b=>b.onclick=async()=>{try{const run=await api('/api/runs/'+encodeURIComponent(b.dataset.deskRun));state.runs=state.runs.filter(r=>r.id!==run.id);state.runs.unshift(run);selected=run.id;openView('work');renderDetail()}catch(e){error(e)}});
 }catch(e){if(project===$('business-project').value.trim())target.textContent='暂时无法读取研究档案：'+(e.message||e)}
}

function savedSourcePlace(loc){
 if(!loc)return '';
 if(loc.page)return '第 '+loc.page+' 页'+(loc.section_heading?' · '+loc.section_heading:'');
 if(loc.row_start)return '第 '+loc.row_start+'—'+loc.row_end+' 行';
 if(loc.section_heading)return '章节：'+loc.section_heading;
 const offset=(loc.text_offset||loc.page_offset||0)+(loc.chunk_offset||0);
 return '转换后文字位置 '+offset;
}
