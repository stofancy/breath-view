'use strict';
let reportData=null, reportRequest=0, compareMode='previous', reportLoading=false;
const contextDrafts=new Map();
const contextValue=name=>document.querySelector(`input[name="${name}"]:checked`)?.value||'unknown';
function setContextValue(name,value){
  const input=document.querySelector(`input[name="${name}"][value="${CSS.escape(value||'unknown')}"]`)||document.querySelector(`input[name="${name}"][value="unknown"]`);
  if(input)input.checked=true;
}
function renderProfessional() {
  const r=reportData,p=r.current,prev=r.previous;
  $('#reportSummary').textContent=r.summary;
  $('#reportComparison').innerHTML=`<table><thead><tr><th>指标</th><th>当前</th><th>前期</th></tr></thead><tbody>${[
    ['已结算记录日',`${p.settled_days}/${p.calendar_days}`,`${prev.settled_days}/${prev.calendar_days}`],
    ['记录日平均使用',duration(p.mean_minutes),duration(prev.mean_minutes)],
    ['事件条目/h（加权）',fmt(p.frequency,2),fmt(prev.frequency,2)],
    ['少于 4 小时的记录日',p.under4_days,prev.under4_days],
    ['有波形的记录日',p.wave_days,prev.wave_days]
  ].map(row=>'<tr>'+row.map((cell,i)=>`<${i?'td':'th'}>${cell}</${i?'td':'th'}>`).join('')+'</tr>').join('')}</tbody></table><p class="small-note">前期 ${prev.start} — ${prev.end}。${r.comparison.eligible?'满足描述性比较的数据条件。':'数据不足，不自动解释差值。'}</p>`;
  $('#reportQuestions').innerHTML=r.questions.map(q=>`<li>${escape(q)}</li>`).join('');
  $('#reportFindings').innerHTML=r.findings.map(f=>`<section class="finding"><h3>${escape(f.title)}</h3><dl><dt>观察</dt><dd>${escape(f.observed)}</dd><dt>解释</dt><dd>${escape(f.meaning)}</dd><dt>下一步</dt><dd>${escape(f.action)}</dd></dl>${f.refs.length?'<div class="finding-sources">依据：'+f.refs.map(id=>{const source=r.sources.find(s=>s.id===id);return `<a href="${source.url}" rel="noreferrer">${escape(id)}</a>`;}).join(' · ')+'</div>':''}</section>`).join('');
  $('#reportDays').innerHTML=r.review_days.map(day=>`<tr data-review-day="${day.date}" tabindex="0"><td><button class="report-date" data-review-day="${day.date}">${day.date}</button></td><td>${day.reasons.map(escape).join('；')}</td><td>${duration(day.minutes)}</td><td>${fmt(day.frequency,2)}</td><td>${day.wave?'有':'无'}</td></tr>`).join('')||'<tr><td colspan="5">当前期间没有符合排序条件的已结算记录。</td></tr>';
  $('#reportWaves').innerHTML=r.wave_reviews.length?r.wave_reviews.map(d=>{
    if(d.error)return `<p>${d.date}：读取失败，${escape(d.error)}</p>`;
    const ipap=d.stats.ipap||{},epap=d.stats.epap||{},leak=d.stats.leak||{};
    return `<div class="wave-review"><button class="report-date" data-review-day="${d.date}">${d.date} · 打开波形</button><span>保留约 ${duration(d.wave_seconds/60)}（每包按 1 秒计）/ 摘要 ${duration(d.summary_minutes)}（约 ${fmt(d.coverage==null?null:d.coverage*100,0)}%）</span><span>吸气压力 IPAP 中位 / P95：${fmt(ipap.median)} / ${fmt(ipap.p95)} cmH₂O</span><span>呼气压力 EPAP 中位 / P95：${fmt(epap.median)} / ${fmt(epap.p95)} cmH₂O</span><span>设备漏气中位 / P95：${fmt(leak.median)} / ${fmt(leak.p95)} L/min</span><span>${d.events_with_wave}/${d.events} 个事件分钟与波形有交集；${d.gaps.length} 个至少 5 分钟的无记录间隔。</span>${d.gaps.length?'<div>'+d.gaps.slice(0,5).map(g=>`<button class="outline" data-review-gap="${d.date}" data-start="${g.start}" data-end="${g.end}">${clock(g.start)}–${clock(g.end)}（${fmt(g.minutes,0)}分）</button>`).join(' ')+'</div>':''}</div>`;
  }).join(''):'<p class="small-note">优先复核的日期没有可用波形；未据此推测压力或漏气变化。</p>';
  $$('[data-review-day]').forEach(button=>{button.onclick=event=>{event.stopPropagation();openDay(button.dataset.reviewDay);};button.onkeydown=event=>{if(event.key==='Enter'){event.stopPropagation();openDay(button.dataset.reviewDay);}};});
  $$('[data-review-gap]').forEach(button=>button.onclick=async()=>{await openDay(button.dataset.reviewGap);if(dayKey===button.dataset.reviewGap&&detail)setWindow(Math.max(0,Number(button.dataset.start)-120),Math.min(86400,Number(button.dataset.end)+120));});
  $('#comparisonRule').textContent=r.comparison.rule;
  $('#reportSources').innerHTML=r.sources.map(source=>`<li><a href="${source.url}" rel="noreferrer">${escape(source.title)}</a></li>`).join('');
}

const contextNames={sleepiness:'sleepiness',mask_problem:'maskProblem',mask_off:'maskOff',unrefreshed:'unrefreshed',gasping:'gasping',drowsy_driving:'drowsyDriving'};
const contextKey=()=>$('#contextForm').dataset.period;
const reportKey=r=>`${r.current.start}|${r.current.end}`;
const help=(key)=>`<button class="term-help" data-term="${key}" aria-label="解释${escape(reportData.patient.glossary[key][0])}">?</button>`;
const trendText=c=>c.eligible?`${fmt(c.period.frequency,2)} → ${fmt(reportData.current.frequency,2)} 条目/小时`:`${c.period.settled_days}/${c.period.calendar_days} 天可计算`;
function updateExportState(){
  const disabled=reportLoading||!reportData||contextDrafts.has(reportKey(reportData));
  $('#openExport').disabled=disabled;
  ['reportDownload','mobilePdf','mobileHtml'].forEach(id=>$('#'+id).setAttribute('aria-disabled',String(disabled)));
}
async function loadReport(force=false){
  if(!overview||!dateRange)return;
  $('#reportStart').value=dateRange[0];$('#reportEnd').value=dateRange[1];
  for(const id of ['reportStart','reportEnd']){$('#'+id).min=overview.days[0].date;$('#'+id).max=overview.days.at(-1).date;}
  if(!force&&!reportLoading&&reportData&&reportKey(reportData)===dateRange.join('|')&&reportData.imported_at===overview.imported_at)return;
  const seq=++reportRequest,params=new URLSearchParams({start:dateRange[0],end:dateRange[1]});
  reportLoading=true;updateExportState();
  $('#reportStatus').textContent='正在读取这段期间的记录…';
  $('#reportContent').setAttribute('aria-busy','true');
  try{
    const data=await api('report?'+params);
    if(seq!==reportRequest)return;
    reportData=data;renderReport();
    $('#reportDownload').href='api/report.html?'+params;
    $('#mobilePdf').href='api/mobile.pdf?'+params;
    $('#mobileHtml').href='api/mobile.html?'+params;
    $('#reportStatus').textContent=`${data.current.start} 至 ${data.current.end} · 最近已结算记录 ${data.patient.latest_settled||'暂无'} · 设备日期`;
  }catch(error){if(seq===reportRequest){$('#reportStatus').textContent='读取失败：'+error.message;$('#reportContent').hidden=true;reportData=null;}}
  finally{if(seq===reportRequest){reportLoading=false;$('#reportContent').setAttribute('aria-busy','false');updateExportState();}}
}
function renderReport(){
  const r=reportData,p=r.current,v=r.patient,a=v.assessment;
  $('#reportContent').hidden=false;
  $('#patientPeriod').textContent=`${p.calendar_days} 天治疗记录`;
  $('#patientTitle').textContent=v.title;$('#patientDetail').textContent=v.detail;$('#patientBoundary').textContent=v.boundary;
  $('#assessmentReasons').innerHTML=a.reasons.map(reason=>`<li>${escape(reason)}</li>`).join('');
  $('#assessmentConfidence').textContent=a.confidence_note;
  $('#assessmentRules').innerHTML=a.rules.map(rule=>`<li>${escape(rule)}</li>`).join('');
  $('#patientMetrics').innerHTML=`
    <article class="panel patient-metric"><div>呼吸事件指数（估算） ${help('frequency')}</div><strong>${fmt(p.frequency,2)} <small>条目 / 小时</small></strong><span>${sumCounts(p.counts)} 条记录 ÷ ${fmt(p.total_minutes/60,1)} 戴机小时 · AHI ${help('ahi')}</span></article>
    <article class="panel patient-metric assessment-metric" data-state="${a.state}"><div>初步判断 ${help('assessment')}</div><strong class="text-value">${escape(a.brief)}</strong><span>${escape(a.confidence)}</span></article>
    <article class="panel patient-metric"><div>平均每天戴机 ${help('usage')}</div><strong class="time-value">${duration(p.mean_minutes)}</strong><span>${p.use_days} 天记录到使用 / ${p.settled_days} 天可计算</span></article>`;
  renderPatientComparison();
  const f=v.followup;
  $('#patientFollowup').dataset.level=f.level;
  $('#patientFollowup').innerHTML=`<div class="eyebrow">需要找医生吗</div><h2>${escape(f.title)}</h2><p>${escape(f.reason)}</p><div class="next-step">${escape(f.action)}</div><button id="editFeelings" class="outline">${Object.values(r.context).some(x=>x==='yes'||x==='no')?'更新我的感受':'补充我的感受'}</button><details class="followup-why"><summary>为什么这样建议</summary><p>综合事件水平、趋势、佩戴和已填写的感受给出下一步。症状和安全问题优先；具体判断理由在上方“为什么这样判断”中。</p>${f.refs.map(id=>{const source=r.sources.find(s=>s.id===id);return source?`<a href="${escape(source.url)}" rel="noreferrer">${escape(source.title)}</a>`:'';}).join('<br>')}</details>`;
  $('#editFeelings').onclick=()=>{$('#contextPanel').open=true;$('#contextPanel').scrollIntoView({block:'start'});$('#sleepHours').focus({preventScroll:true});};
  $('#patientCoverage').textContent=v.coverage+' 数据导入：'+r.imported_at?.replace('T',' ')+'。';
  $('#patientTypes').innerHTML=['OSA','CSA','HYP'].map(k=>`<div>${escape(v.glossary[k][0])} ${help(k)}<strong>${p.counts[k]} <small>条目</small></strong><span>${fmt(p.type_rates[k],2)} 条目 / 小时</span></div>`).join('');
  $('#patientGlossary').innerHTML=Object.values(v.glossary).map(([name,meaning])=>`<details class="glossary-item"><summary>${escape(name)}</summary><p>${escape(meaning)}</p></details>`).join('');
  renderProfessional();renderContext();updateExportState();
}
function sumCounts(counts){return Object.values(counts).reduce((a,b)=>a+b,0);}
function renderPatientComparison(){
  const c=reportData.patient.comparisons[compareMode],p=reportData.current;
  const usage=c.minutes_delta;
  const usageText=usage==null?'':Math.round(Math.abs(usage))===0?'平均戴机时长相近':`平均戴机${usage>0?'增加':'减少'} ${Math.round(Math.abs(usage))} 分钟`;
  $('#patientChange').innerHTML=`<div class="change-head" data-direction="${c.direction}"><strong>${escape(c.text)}</strong><span>${escape(trendText(c))}</span></div><p class="small-note">${compareMode==='year'?'去年同期':'前期'}：${c.period.start} 至 ${c.period.end} · ${c.period.settled_days}/${c.period.calendar_days} 天可计算</p>${usageText?`<p class="usage-change">${usageText}。戴机时间不等于睡眠时间，需要与你的作息核对。</p>`:''}`;
  const points=reportData.patient.trend,w=640,h=150,left=32,right=12,top=18,bottom=28,plotHeight=h-top-bottom;
  const values=points.filter(x=>x.frequency!=null).map(x=>x.frequency);
  const max=Math.max(1,...values),step=(w-left-right)/points.length;
  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="每日呼吸事件记录频率，空白为没有可计算的记录"><line x1="${left}" y1="${h-bottom}" x2="${w-right}" y2="${h-bottom}" stroke="#c7d5db"/><text x="4" y="${top+4}">${fmt(max,1)}</text><text x="12" y="${h-bottom}">0</text>`;
  points.forEach((d,i)=>{
    const x=left+i*step+step*.12,bw=Math.max(.2,step*.76);
    if(d.frequency==null){svg+=`<rect x="${x}" y="${h-bottom-3}" width="${bw}" height="3" fill="#b4bec5"><title>${d.date}：${d.state==='pending'?'未结算':'无可计算记录'}</title></rect>`;return;}
    const bh=Math.max(2,d.frequency/max*plotHeight),label=`${d.date}：${fmt(d.frequency,2)} 条目/小时，戴机 ${duration(d.minutes)}`;
    svg+=`<rect class="trend-day" tabindex="0" role="button" aria-label="${label}" data-patient-day="${d.date}" x="${x}" y="${h-bottom-bh}" width="${bw}" height="${bh}" rx="1" fill="#4b7e92"><title>${label}</title></rect>`;
  });
  svg+=`<text x="${left}" y="${h-5}">${p.start.slice(5)}</text><text x="${w-right}" y="${h-5}" text-anchor="end">${p.end.slice(5)}</text></svg>`;
  $('#patientChart').innerHTML=svg;
  $('#patientTrendTable').innerHTML=`<table><thead><tr><th>日期</th><th>记录/小时</th><th>戴机时间</th></tr></thead><tbody>${points.map(d=>`<tr><td>${d.state==='settled'?`<button class="report-date" data-patient-day="${d.date}">${d.date}</button>`:d.date}</td><td>${d.frequency==null?(d.state==='pending'?'未结算':'—'):fmt(d.frequency,2)}</td><td>${duration(d.minutes)}</td></tr>`).join('')}</tbody></table>`;
  $$('[data-patient-day]').forEach(el=>{el.onclick=()=>openDay(el.dataset.patientDay);el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openDay(el.dataset.patientDay);}};});
}
function readForm(){
  const context={sleep_hours:$('#sleepHours').value||null,note:$('#patientNote').value};
  Object.entries(contextNames).forEach(([key,name])=>context[key]=contextValue(name));return context;
}
function renderContext(){
  const key=reportKey(reportData),c=contextDrafts.get(key)||reportData.context;
  $('#contextForm').dataset.period=key;
  $('#contextFields').innerHTML=`<label>平均每天睡多久（含午睡）<div><input id="sleepHours" type="number" min="0.1" max="24" step="0.1" placeholder="未填写" aria-label="自报平均睡眠小时"> 小时</div></label>`+Object.entries(reportData.patient.context_labels).map(([key,label])=>`<fieldset class="choice-field"><legend>${escape(label)}</legend><div class="choice-group" role="radiogroup" aria-label="${escape(label)}">${[['unknown','未填写'],['yes','是'],['no','否']].map(([value,text])=>`<label class="choice-option"><input type="radio" name="${contextNames[key]}" value="${value}"><span>${text}</span></label>`).join('')}</div></fieldset>`).join('');
  $('#sleepHours').value=c.sleep_hours??'';$('#patientNote').value=c.note;
  Object.entries(contextNames).forEach(([field,name])=>setContextValue(name,c[field]));
  $('#contextPeriod').textContent=`只填写 ${reportData.current.start} 至 ${reportData.current.end} 的总体情况。未填写保持未知，不沿用其他期间的答案。`;
  $('#contextPreview').textContent=reportData.patient.feeling;
  updateDraftStatus();
}
function updateDraftStatus(){
  const dirty=contextDrafts.has(contextKey());
  $('#contextStatus').textContent=dirty?'有未保存的修改；建议和导出仍基于已保存内容。切换期间会暂存本次草稿。':'感受按本期间保存在本机。';
  $('#discardContext').hidden=!dirty;
  if(reportData)$('#contextPreview').textContent=dirty?'有未保存的修改，保存后可导出':reportData.patient.feeling;
  updateExportState();
}
$('#contextForm').oninput=()=>{contextDrafts.set(contextKey(),readForm());updateDraftStatus();};
$('#contextForm').onsubmit=async event=>{
  event.preventDefault();if(!reportData||reportLoading)return;
  const key=contextKey(),[start,end]=key.split('|'),context=readForm(),serialized=JSON.stringify(context);
  $('#saveContext').disabled=true;
  try{
    await api('context',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({start,end,context})});
    if(JSON.stringify(contextDrafts.get(key)||context)===serialized)contextDrafts.delete(key);
    if(dateRange.join('|')===key){await loadReport(true);if(!contextDrafts.has(key))$('#contextStatus').textContent='已保存，建议和导出已更新。';}
  }catch(error){$('#contextStatus').textContent='保存失败：'+error.message;}
  finally{$('#saveContext').disabled=false;updateExportState();}
};
$('#discardContext').onclick=()=>{contextDrafts.delete(contextKey());renderContext();};
$('#generateReport').onclick=()=>{
  const start=$('#reportStart').value,end=$('#reportEnd').value;
  if(!start||!end||start>end||start<overview.days[0].date||end>overview.days.at(-1).date){showError('请选择记录范围内有效的分析日期。');return;}
  dateRange=[start,end];$('#rangeStart').value=start;$('#rangeEnd').value=end;
  $$('#reportPeriod button').forEach(b=>b.classList.remove('selected'));showError();loadReport(true);
};
$$('#reportPeriod button').forEach(button=>button.onclick=()=>{presetRange(Number(button.dataset.days),false);$$('#reportPeriod button').forEach(b=>b.classList.toggle('selected',b===button));loadReport();});
$$('#patientCompare button').forEach(button=>button.onclick=()=>{compareMode=button.dataset.compare;$$('#patientCompare button').forEach(b=>b.classList.toggle('selected',b===button));if(reportData)renderPatientComparison();});
$('#openExport').onclick=()=>{if(!reportData)return;$('#exportPeriod').textContent=`${reportData.current.start} 至 ${reportData.current.end} · ${reportData.device.model}`;$('#exportDialog').showModal();};
for(const id of ['mobilePdf','mobileHtml'])$('#'+id).onclick=async event=>{
  event.preventDefault();const link=event.currentTarget;if(link.getAttribute('aria-disabled')==='true')return;
  const url=link.href,filename=`pap-phone-${reportData.current.start}-${reportData.current.end}.${id==='mobilePdf'?'pdf':'html'}`;
  link.setAttribute('aria-disabled','true');$('#exportStatus').textContent=id==='mobilePdf'?'正在生成手机 PDF…':'正在生成离线网页…';
  uiLog('mobile-export-start '+id);
  try{
    const response=await fetch(url);
    if(!response.ok){const data=await response.json();throw Error(data.error||'导出失败');}
    const objectUrl=URL.createObjectURL(await response.blob()),a=document.createElement('a');
    a.href=objectUrl;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(objectUrl),60000);
    $('#exportStatus').textContent='文件已生成，已发起下载；独立版请在保存窗口选择位置。';uiLog('mobile-export-ready '+id);
  }catch(error){$('#exportStatus').textContent='导出失败：'+error.message;uiLog('mobile-export-error '+id);}
  finally{updateExportState();}
};
$('#closeExport').onclick=()=>$('#exportDialog').close();

// Works with a mouse, keyboard and touch; no native popup menus.
let termAnchor=null;
function closeTerm(){if(termAnchor){termAnchor.removeAttribute('aria-describedby');termAnchor.setAttribute('aria-expanded','false');}termAnchor=null;$('#termTooltip').hidden=true;}
function showTerm(button){
  const term=button.dataset.explanation?[button.dataset.title,button.dataset.explanation]:reportData?.patient.glossary[button.dataset.term];if(!term)return;
  closeTerm();termAnchor=button;
  const tip=$('#termTooltip');tip.innerHTML=`<strong>${escape(term[0])}</strong><p>${escape(term[1])}</p>`;tip.hidden=false;
  button.setAttribute('aria-describedby','termTooltip');button.setAttribute('aria-expanded','true');
  const rect=button.getBoundingClientRect(),box=tip.getBoundingClientRect();
  tip.style.left=Math.max(8,Math.min(rect.left,innerWidth-box.width-8))+'px';
  tip.style.top=(rect.bottom+box.height+12<innerHeight?rect.bottom+8:Math.max(8,rect.top-box.height-8))+'px';
}
document.addEventListener('pointerover',e=>{const b=e.target.closest('[data-term]');if(b&&e.pointerType!=='touch')showTerm(b);});
document.addEventListener('focusin',e=>{const b=e.target.closest('[data-term]');if(b)showTerm(b);else closeTerm();});
document.addEventListener('click',e=>{const b=e.target.closest('[data-term]');if(b)showTerm(b);else if(!e.target.closest('#termTooltip'))closeTerm();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeTerm();});
document.addEventListener('pointerout',e=>{if(e.target.closest('[data-term]')&&!e.relatedTarget?.closest?.('[data-term],#termTooltip'))closeTerm();});
window.addEventListener('scroll',closeTerm,true);window.addEventListener('resize',closeTerm);
refresh();
