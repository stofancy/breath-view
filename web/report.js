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
  $('#reportComparison').innerHTML=`<table><thead><tr><th>${t('report.comparisonMetric')}</th><th>${t('report.current')}</th><th>${t('report.adjacent')}</th></tr></thead><tbody>${[
    [t('report.settledDays'),`${p.settled_days}/${p.calendar_days}`,`${prev.settled_days}/${prev.calendar_days}`],
    [t('report.averageTreatment'),duration(p.mean_minutes),duration(prev.mean_minutes)],
    [t('report.weightedRate'),fmt(p.frequency,2),fmt(prev.frequency,2)],
    [t('report.underFour'),p.under4_days,prev.under4_days],
    [t('report.waveDays'),p.wave_days,prev.wave_days]
  ].map(row=>'<tr>'+row.map((cell,i)=>`<${i?'td':'th'}>${cell}</${i?'td':'th'}>`).join('')+'</tr>').join('')}</tbody></table><p class="small-note">${t('report.previousPeriod',{start:prev.start,end:prev.end})}${t('common.sentenceEnd')}${r.comparison.eligible?t('report.comparisonEligible'):t('report.comparisonIneligible')}</p>`;
  $('#reportQuestions').innerHTML=r.questions.map(q=>`<li>${escape(q)}</li>`).join('');
  $('#reportFindings').innerHTML=r.findings.map(f=>`<section class="finding"><h3>${escape(f.title)}</h3><dl><dt>${t('report.findingObservation')}</dt><dd>${escape(f.observed)}</dd><dt>${t('report.findingMeaning')}</dt><dd>${escape(f.meaning)}</dd><dt>${t('report.findingAction')}</dt><dd>${escape(f.action)}</dd></dl>${f.refs.length?'<div class="finding-sources">'+t('report.findingEvidenceLabel')+f.refs.map(id=>{const source=r.sources.find(s=>s.id===id);return `<a href="${source.url}" rel="noreferrer">${escape(id)}</a>`;}).join(t('common.sourceSeparator'))+'</div>':''}</section>`).join('');
  $('#reportDays').innerHTML=r.review_days.map(day=>`<tr data-review-day="${day.date}" tabindex="0"><td><button class="report-date" data-review-day="${day.date}">${day.date}</button></td><td>${day.reasons.map(escape).join(t('common.listSeparator'))}</td><td>${duration(day.minutes)}</td><td>${fmt(day.frequency,2)}</td><td>${day.wave?t('common.available'):t('common.unavailable')}</td></tr>`).join('')||`<tr><td colspan="5">${t('report.reportNoDays')}</td></tr>`;
  $('#reportWaves').innerHTML=r.wave_reviews.length?r.wave_reviews.map(d=>{
    if(d.error)return `<p>${d.date}: ${t('report.reportWaveError',{error:escape(d.error)})}</p>`;
    const ipap=d.stats.ipap||{},epap=d.stats.epap||{},leak=d.stats.leak||{};
    const gaps=d.gaps.length?'<div>'+d.gaps.slice(0,5).map(g=>'<button class="outline" data-review-gap="'+d.date+'" data-start="'+g.start+'" data-end="'+g.end+'">'+clock(g.start)+'–'+clock(g.end)+' · '+t('report.gapMinutes',{minutes:fmt(g.minutes,0)})+'</button>').join(' ')+'</div>':'';
    return `<div class="wave-review"><button class="report-date" data-review-day="${d.date}">${d.date} · ${t('report.waveOpen')}</button><span>${t('report.waveRetained',{duration:duration(d.wave_seconds/60),summary:duration(d.summary_minutes),coverage:fmt(d.coverage==null?null:d.coverage*100,0)})}</span><span>${t('report.ipapP95',{median:fmt(ipap.median),p95:fmt(ipap.p95)})}</span><span>${t('report.epapP95',{median:fmt(epap.median),p95:fmt(epap.p95)})}</span><span>${t('report.leakP95',{median:fmt(leak.median),p95:fmt(leak.p95)})}</span><span>${t('report.waveOverlap',{withWave:d.events_with_wave,events:d.events,gaps:d.gaps.length})}</span>${gaps}</div>`;
  }).join(''):`<p class="small-note">${t('report.noWavePriority')}</p>`;
  $$('[data-review-day]').forEach(button=>{button.onclick=event=>{event.stopPropagation();openDay(button.dataset.reviewDay);};button.onkeydown=event=>{if(event.key==='Enter'){event.stopPropagation();openDay(button.dataset.reviewDay);}};});
  $$('[data-review-gap]').forEach(button=>button.onclick=async()=>{await openDay(button.dataset.reviewGap);if(dayKey===button.dataset.reviewGap&&detail)setWindow(Math.max(0,Number(button.dataset.start)-120),Math.min(86400,Number(button.dataset.end)+120));});
  $('#comparisonRule').textContent=r.comparison.rule;
  $('#reportSources').innerHTML=r.sources.map(source=>`<li><a href="${source.url}" rel="noreferrer">${escape(source.title)}</a></li>`).join('');
}

const contextNames={sleepiness:'sleepiness',mask_problem:'maskProblem',mask_off:'maskOff',unrefreshed:'unrefreshed',gasping:'gasping',drowsy_driving:'drowsyDriving'};
const contextKey=()=>$('#contextForm').dataset.period;
const reportKey=r=>`${r.current.start}|${r.current.end}`;
const help=(key)=>`<button class="term-help" data-term="${key}" aria-label="${escape(t('report.termHelp',{term:reportData.patient.glossary[key][0]}))}">?</button>`;
const trendText=c=>c.eligible?`${fmt(c.period.frequency,2)} → ${fmt(reportData.current.frequency,2)} ${t('report.metric.entriesPerHour')}`:t('report.trendCalculable',{settledDays:c.period.settled_days,calendarDays:c.period.calendar_days});
function updateExportState(){
  const disabled=reportLoading||!reportData||contextDrafts.has(reportKey(reportData));
  $('#openExport').disabled=disabled;
  ['reportDownload','mobilePdf','mobileHtml'].forEach(id=>$('#'+id).setAttribute('aria-disabled',String(disabled)));
}
async function loadReport(force=false){
  if(!overview||!dateRange)return;
  $('#reportStart').value=dateRange[0];$('#reportEnd').value=dateRange[1];
  for(const id of ['reportStart','reportEnd']){$('#'+id).min=overview.days[0].date;$('#'+id).max=overview.days.at(-1).date;}
  if(!force&&!reportLoading&&reportData&&reportKey(reportData)===dateRange.join('|')&&reportData.imported_at===overview.imported_at&&reportData.locale===i18n.locale)return;
  const seq=++reportRequest,params=new URLSearchParams({start:dateRange[0],end:dateRange[1]});
  reportLoading=true;updateExportState();
  $('#reportStatus').textContent=t('status.reportLoading');
  $('#reportContent').setAttribute('aria-busy','true');
  try{
    const data=await api('report?'+params);
    if(seq!==reportRequest)return;
    reportData=data;renderReport();
    $('#reportDownload').href='api/'+localizedPath('report.html?'+params);
    $('#mobilePdf').href='api/'+localizedPath('mobile.pdf?'+params);
    $('#mobileHtml').href='api/'+localizedPath('mobile.html?'+params);
    $('#reportStatus').textContent=t('status.report',{start:data.current.start,end:data.current.end,latest:data.patient.latest_settled||t('common.none')});
  }catch(error){if(seq===reportRequest){$('#reportStatus').textContent=t('status.reportFailed',{error:error.message});$('#reportContent').hidden=true;reportData=null;}}
  finally{if(seq===reportRequest){reportLoading=false;$('#reportContent').setAttribute('aria-busy','false');updateExportState();}}
}
function renderReport(){
  const r=reportData,p=r.current,v=r.patient,a=v.assessment;
  $('#reportContent').hidden=false;
  $('#patientPeriod').textContent=t('report.periodLabel',{days:p.calendar_days});
  $('#patientTitle').textContent=v.title;$('#patientDetail').textContent=v.detail;$('#patientBoundary').textContent=v.boundary;
  $('#assessmentReasons').innerHTML=a.reasons.map(reason=>`<li>${escape(reason)}</li>`).join('');
  $('#assessmentConfidence').textContent=a.confidence_note;
  $('#assessmentRules').innerHTML=a.rules.map(rule=>`<li>${escape(rule)}</li>`).join('');
  $('#patientMetrics').innerHTML=`
    <article class="panel patient-metric"><div>${t('report.metric.frequency')} ${help('frequency')}</div><strong>${fmt(p.frequency,2)} <small>${t('report.metric.entriesPerHour')}</small></strong><span>${t('report.metric.estimateDivision',{entries:sumCounts(p.counts),hours:fmt(p.total_minutes/60,1)})} ${help('ahi')}</span></article>
    <article class="panel patient-metric assessment-metric" data-state="${a.state}"><div>${t('report.metric.assessment')} ${help('assessment')}</div><strong class="text-value">${escape(a.brief)}</strong><span>${escape(a.confidence)}</span></article>
    <article class="panel patient-metric"><div>${t('report.metric.averageTreatment')} ${help('usage')}</div><strong class="time-value">${duration(p.mean_minutes)}</strong><span>${t('report.metric.daysUse',{useDays:p.use_days,settledDays:p.settled_days})}</span></article>`;
  renderPatientComparison();
  const f=v.followup;
  $('#patientFollowup').dataset.level=f.level;
  $('#patientFollowup').innerHTML=`<div class="eyebrow">${t('report.followupHeading')}</div><h2>${escape(f.title)}</h2><p>${escape(f.reason)}</p><div class="next-step">${escape(f.action)}</div><button id="editFeelings" class="outline">${Object.values(r.context).some(x=>x==='yes'||x==='no')?t('report.updateFeelings'):t('report.addFeelings')}</button><details class="followup-why"><summary>${t('report.followupWhy')}</summary><p>${t('report.followupWhyText')}</p>${f.refs.map(id=>{const source=r.sources.find(s=>s.id===id);return source?`<a href="${escape(source.url)}" rel="noreferrer">${escape(source.title)}</a>`:'';}).join('<br>')}</details>`;
  $('#editFeelings').onclick=()=>{$('#contextPanel').open=true;$('#contextPanel').scrollIntoView({block:'start'});$('#sleepHours').focus({preventScroll:true});};
  $('#patientCoverage').textContent=v.coverage+' '+t('report.imported',{value:r.imported_at?.replace('T',' ')||t('common.none')});
  $('#patientTypes').innerHTML=['OSA','CSA','HYP'].map(k=>`<div>${escape(v.glossary[k][0])} ${help(k)}<strong>${p.counts[k]} <small>${t('report.metric.entries')}</small></strong><span>${fmt(p.type_rates[k],2)} ${t('report.metric.entriesPerHour')}</span></div>`).join('');
  $('#patientGlossary').innerHTML=Object.values(v.glossary).map(([name,meaning])=>`<details class="glossary-item"><summary>${escape(name)}</summary><p>${escape(meaning)}</p></details>`).join('');
  renderProfessional();renderContext();updateExportState();
}
function sumCounts(counts){return Object.values(counts).reduce((a,b)=>a+b,0);}
function renderPatientComparison(){
  const c=reportData.patient.comparisons[compareMode],p=reportData.current;
  const usage=c.minutes_delta;
  const usageText=usage==null?'':Math.round(Math.abs(usage))===0?t('report.usageSimilar'):t('report.usageChange',{direction:usage>0?t('report.increased'):t('report.decreased'),minutes:Math.round(Math.abs(usage))});
  const periodLabel=compareMode==='year'?t('report.yearLabel'):t('report.previousLabel');
  $('#patientChange').innerHTML=`<div class="change-head" data-direction="${c.direction}"><strong>${escape(c.text)}</strong><span>${escape(trendText(c))}</span></div><p class="small-note">${periodLabel}${t('common.labelColon')}${c.period.start} ${t('common.to')} ${c.period.end} · ${t('report.trendCalculable',{settledDays:c.period.settled_days,calendarDays:c.period.calendar_days})}</p>${usageText?`<p class="usage-change">${usageText}${t('common.sentenceEnd')}${t('report.usageNote')}</p>`:''}`;
  const points=reportData.patient.trend,w=640,h=150,left=32,right=12,top=18,bottom=28,plotHeight=h-top-bottom;
  const values=points.filter(x=>x.frequency!=null).map(x=>x.frequency);
  const max=Math.max(1,...values),step=(w-left-right)/points.length;
  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${escape(t('report.trendAria'))}"><line x1="${left}" y1="${h-bottom}" x2="${w-right}" y2="${h-bottom}" stroke="#c7d5db"/><text x="4" y="${top+4}">${fmt(max,1)}</text><text x="12" y="${h-bottom}">0</text>`;
  points.forEach((d,i)=>{
    const x=left+i*step+step*.12,bw=Math.max(.2,step*.76);
    if(d.frequency==null){svg+=`<rect x="${x}" y="${h-bottom-3}" width="${bw}" height="3" fill="#b4bec5"><title>${escape(t('report.trendEmpty',{date:d.date,state:d.state==='pending'?t('common.pending'):t('common.noCalculable')}))}</title></rect>`;return;}
    const bh=Math.max(2,d.frequency/max*plotHeight),label=t('report.trendLabel',{date:d.date,frequency:fmt(d.frequency,2),duration:duration(d.minutes)});
    svg+=`<rect class="trend-day" tabindex="0" role="button" aria-label="${escape(label)}" data-patient-day="${d.date}" x="${x}" y="${h-bottom-bh}" width="${bw}" height="${bh}" rx="1" fill="#4b7e92"><title>${escape(label)}</title></rect>`;
  });
  svg+=`<text x="${left}" y="${h-5}">${p.start.slice(5)}</text><text x="${w-right}" y="${h-5}" text-anchor="end">${p.end.slice(5)}</text></svg>`;
  $('#patientChart').innerHTML=svg;
  $('#patientTrendTable').innerHTML=`<table><thead><tr><th>${t('report.tableDate')}</th><th>${t('report.tableRate')}</th><th>${t('report.tableTreatment')}</th></tr></thead><tbody>${points.map(d=>`<tr><td>${d.state==='settled'?`<button class="report-date" data-patient-day="${d.date}">${d.date}</button>`:d.date}</td><td>${d.frequency==null?(d.state==='pending'?t('common.pending'):'—'):fmt(d.frequency,2)}</td><td>${duration(d.minutes)}</td></tr>`).join('')}</tbody></table>`;
  $$('[data-patient-day]').forEach(el=>{el.onclick=()=>openDay(el.dataset.patientDay);el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openDay(el.dataset.patientDay);}};});
}
function readForm(){
  const context={sleep_hours:$('#sleepHours').value||null,note:$('#patientNote').value};
  Object.entries(contextNames).forEach(([key,name])=>context[key]=contextValue(name));return context;
}
function renderContext(){
  const key=reportKey(reportData),c=contextDrafts.get(key)||reportData.context;
  $('#contextForm').dataset.period=key;
  const choices=[['unknown',t('context.unknown')],['yes',t('context.yes')],['no',t('context.no')]];
  $('#contextFields').innerHTML=`<label>${t('report.contextSleep')}<div><input id="sleepHours" type="number" min="0.1" max="24" step="0.1" placeholder="${escape(t('report.sleepPlaceholder'))}" aria-label="${escape(t('report.sleepAria'))}"> ${t('report.hoursUnit')}</div></label>`+Object.entries(reportData.patient.context_labels).map(([key,label])=>`<fieldset class="choice-field"><legend>${escape(label)}</legend><div class="choice-group" role="radiogroup" aria-label="${escape(label)}">${choices.map(([value,text])=>`<label class="choice-option"><input type="radio" name="${contextNames[key]}" value="${value}"><span>${text}</span></label>`).join('')}</div></fieldset>`).join('');
  $('#sleepHours').value=c.sleep_hours??'';$('#patientNote').value=c.note;
  Object.entries(contextNames).forEach(([field,name])=>setContextValue(name,c[field]));
  $('#contextPeriod').textContent=t('report.contextPeriod',{start:reportData.current.start,end:reportData.current.end});
  $('#contextPreview').textContent=reportData.patient.feeling;
  updateDraftStatus();
}
function updateDraftStatus(){
  const dirty=contextDrafts.has(contextKey());
  $('#contextStatus').textContent=dirty?t('status.draft'):t('status.contextSaved');
  $('#discardContext').hidden=!dirty;
  if(reportData)$('#contextPreview').textContent=dirty?t('status.draftPreview'):reportData.patient.feeling;
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
    if(dateRange.join('|')===key){await loadReport(true);if(!contextDrafts.has(key))$('#contextStatus').textContent=t('status.saved');}
  }catch(error){$('#contextStatus').textContent=t('status.saveFailed',{error:error.message});}
  finally{$('#saveContext').disabled=false;updateExportState();}
};
$('#discardContext').onclick=()=>{contextDrafts.delete(contextKey());renderContext();};
$('#generateReport').onclick=()=>{
  const start=$('#reportStart').value,end=$('#reportEnd').value;
  if(!start||!end||start>end||start<overview.days[0].date||end>overview.days.at(-1).date){showError(t('status.invalidReportRange'));return;}
  dateRange=[start,end];$('#rangeStart').value=start;$('#rangeEnd').value=end;
  $$('#reportPeriod button').forEach(b=>b.classList.remove('selected'));showError();loadReport(true);
};
$$('#reportPeriod button').forEach(button=>button.onclick=()=>{presetRange(Number(button.dataset.days),false);$$('#reportPeriod button').forEach(b=>b.classList.toggle('selected',b===button));loadReport();});
$$('#patientCompare button').forEach(button=>button.onclick=()=>{compareMode=button.dataset.compare;$$('#patientCompare button').forEach(b=>b.classList.toggle('selected',b===button));if(reportData)renderPatientComparison();});
$('#openExport').onclick=()=>{if(!reportData)return;$('#exportPeriod').textContent=t('report.openPeriod',{start:reportData.current.start,end:reportData.current.end,model:reportData.device.model});$('#exportDialog').showModal();};
for(const id of ['mobilePdf','mobileHtml'])$('#'+id).onclick=async event=>{
  event.preventDefault();const link=event.currentTarget;if(link.getAttribute('aria-disabled')==='true')return;
  const url=link.href,filename=`pap-phone-${reportData.current.start}-${reportData.current.end}.${id==='mobilePdf'?'pdf':'html'}`;
  link.setAttribute('aria-disabled','true');$('#exportStatus').textContent=id==='mobilePdf'?t('status.exportingPdf'):t('status.exportingHtml');
  uiLog('mobile-export-start '+id);
  try{
    const response=await fetch(url);
    if(!response.ok){const data=await response.json();throw Error(data.error||t('status.exportFailed',{error:t('error.readFailed')}));}
    const objectUrl=URL.createObjectURL(await response.blob()),a=document.createElement('a');
    a.href=objectUrl;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(objectUrl),60000);
    $('#exportStatus').textContent=t('status.fileReady');uiLog('mobile-export-ready '+id);
  }catch(error){$('#exportStatus').textContent=t('status.exportFailed',{error:error.message});uiLog('mobile-export-error '+id);}
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
window.addEventListener('breath-view:locale',()=>{if(overview&&dateRange&&activeView==='report')loadReport(true);});
refresh();
