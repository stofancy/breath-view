'use strict';
let reportData=null, reportRequest=0;
async function loadReport(force=false) {
  if(!overview||!dateRange)return;
  $('#reportStart').value=dateRange[0];$('#reportEnd').value=dateRange[1];
  for(const id of ['reportStart','reportEnd']){$('#'+id).min=overview.days[0].date;$('#'+id).max=overview.days.at(-1).date;}
  if(!force&&reportData&&reportData.current.start===dateRange[0]&&reportData.current.end===dateRange[1]&&reportData.imported_at===overview.imported_at)return;
  const seq=++reportRequest,params=new URLSearchParams({start:dateRange[0],end:dateRange[1]});
  $('#reportStatus').textContent='正在计算期间汇总与重点日期波形…';
  $('#reportContent').classList.add('loading');$('#contextForm').classList.add('loading');
  $('#reportDownload').setAttribute('aria-disabled','true');
  try {
    const data=await api('report?'+params);
    if(seq!==reportRequest)return;
    reportData=data;renderReport();
    $('#reportStatus').textContent=`生成时间 ${data.generated_at.replace('T',' ')} · 数据导入 ${data.imported_at?.replace('T',' ')||'未记录'} · 分析规则 ${data.version}`;
    $('#reportDownload').href='api/report.html?'+params;
    $('#reportDownload').setAttribute('aria-disabled','false');
  }catch(error){if(seq===reportRequest){$('#reportStatus').textContent='生成失败：'+error.message;$('#reportContent').hidden=true;}}
  finally{if(seq===reportRequest){$('#reportContent').classList.remove('loading');$('#contextForm').classList.remove('loading');}}
}
function renderReport() {
  const r=reportData,p=r.current,prev=r.previous;
  $('#reportContent').hidden=false;$('#reportSummary').textContent=r.summary;
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
    const pressure=d.stats.pressure||{},leak=d.stats.leak||{};
    return `<div class="wave-review"><button class="report-date" data-review-day="${d.date}">${d.date} · 打开波形</button><span>保留 ${duration(d.wave_seconds/60)} / 摘要 ${duration(d.summary_minutes)}（约 ${fmt(d.coverage==null?null:d.coverage*100,0)}%）</span><span>压力中位 / P95：${fmt(pressure.median)} / ${fmt(pressure.p95)} cmH₂O</span><span>设备漏气中位 / P95：${fmt(leak.median)} / ${fmt(leak.p95)} L/min</span><span>${d.events_with_wave}/${d.events} 个事件分钟与波形有交集；${d.gaps.length} 个至少 5 分钟的无记录间隔。</span>${d.gaps.length?'<div>'+d.gaps.slice(0,5).map(g=>`<button class="outline" data-review-gap="${d.date}" data-start="${g.start}" data-end="${g.end}">${clock(g.start)}–${clock(g.end)}（${fmt(g.minutes,0)}分）</button>`).join(' ')+'</div>':''}</div>`;
  }).join(''):'<p class="small-note">优先复核的日期没有可用波形；未据此推测压力或漏气变化。</p>';
  $$('[data-review-day]').forEach(button=>{button.onclick=event=>{event.stopPropagation();openDay(button.dataset.reviewDay);};button.onkeydown=event=>{if(event.key==='Enter'){event.stopPropagation();openDay(button.dataset.reviewDay);}};});
  $$('[data-review-gap]').forEach(button=>button.onclick=async()=>{await openDay(button.dataset.reviewGap);if(dayKey===button.dataset.reviewGap&&detail)setWindow(Math.max(0,Number(button.dataset.start)-120),Math.min(86400,Number(button.dataset.end)+120));});
  $('#comparisonRule').textContent=r.comparison.rule;
  $('#reportSources').innerHTML=r.sources.map(source=>`<li><a href="${source.url}" rel="noreferrer">${escape(source.title)}</a></li>`).join('');
  $('#sleepHours').value=r.context.sleep_hours??'';
  $('#sleepiness').value=r.context.sleepiness;$('#maskProblem').value=r.context.mask_problem;$('#maskOff').value=r.context.mask_off;
  $('#patientNote').value=r.context.note;$('#contextStatus').textContent=`自述适用期间：${p.start} — ${p.end}`;
}
$('#generateReport').onclick=()=>{
  const start=$('#reportStart').value,end=$('#reportEnd').value;
  if(!start||!end||start>end||start<overview.days[0].date||end>overview.days.at(-1).date){showError('请选择记录范围内有效的分析日期。');return;}
  dateRange=[start,end];$('#rangeStart').value=start;$('#rangeEnd').value=end;
  $$('#reportPeriod button').forEach(button=>button.classList.remove('selected'));showError();loadReport(true);
};
$$('#reportPeriod button').forEach(button=>button.onclick=()=>{presetRange(Number(button.dataset.days),false);$$('#reportPeriod button').forEach(b=>b.classList.toggle('selected',b===button));loadReport();});
$('#contextForm').onsubmit=async event=>{
  event.preventDefault();if(!reportData)return;
  const r=reportData.current;
  const context={sleep_hours:$('#sleepHours').value||null,sleepiness:$('#sleepiness').value,mask_problem:$('#maskProblem').value,mask_off:$('#maskOff').value,note:$('#patientNote').value};
  $('#saveContext').disabled=true;
  try{await api('context',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({start:r.start,end:r.end,context})});await loadReport(true);$('#contextStatus').textContent='已保存到本机并更新本期间分析。';}
  catch(error){$('#contextStatus').textContent='保存失败：'+error.message;}
  finally{$('#saveContext').disabled=false;}
};
$('#contextForm').oninput=()=>{$('#contextStatus').textContent='自述有未保存的修改。';};
refresh();
