'use strict';
// Standalone QtWebEngine troubleshooting trace. It records control and
// lifecycle events without recording patient-entered values or note text.
const uiTarget = target => {
  const node=target?.closest?.('[id],[name],button,input,textarea,select')||target;
  return node?.id||node?.getAttribute?.('name')||node?.tagName||'unknown';
};
const uiLog = (event, target) => {
  const suffix=target?` target=${uiTarget(target)}`:'';
  console.info(`[ui] ${event}${suffix}`);
};
document.addEventListener('DOMContentLoaded',()=>uiLog('dom-ready'));
document.addEventListener('pointerdown',event=>uiLog('pointerdown',event.target),true);
document.addEventListener('pointerup',event=>uiLog('pointerup',event.target),true);
document.addEventListener('focusin',event=>uiLog('focusin',event.target),true);
document.addEventListener('change',event=>uiLog('change',event.target),true);
document.addEventListener('input',event=>uiLog('input',event.target),true);
document.addEventListener('submit',event=>uiLog('submit',event.target),true);
window.addEventListener('error',event=>console.error(`[ui] error message=${event.message||'unknown'} source=${event.filename||'unknown'} line=${event.lineno||0}`));
window.addEventListener('unhandledrejection',event=>console.error(`[ui] unhandledrejection reason=${String(event.reason||'unknown')}`));
setInterval(()=>uiLog(`heartbeat view=${activeView||'starting'}`),5000);
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const i18n = window.breathI18n;
const localizedPath = path => i18n.localizedApiPath(path);
const channels = {
  flow: {name:'channel.flow',unit:'L/min',color:'#326c92',height:150},
  ipap: {name:'channel.ipap',unit:'cmH₂O',color:'#417763',height:100,help:'channel.ipapHelp'},
  epap: {name:'channel.epap',unit:'cmH₂O',color:'#6b819b',height:100,help:'channel.epapHelp'},
  leak: {name:'channel.leak',unit:'L/min',color:'#a2793e',height:100},
  tidal: {name:'channel.tidal',unit:'mL',color:'#607f9a',height:95},
  ventilation: {name:'channel.ventilation',unit:'L/min',color:'#6b8152',height:95},
  rate: {name:'channel.rate',unit:'channel.rateUnit',color:'#84709a',height:95}
};
const eventNames = {OSA:'event.OSA',CSA:'event.CSA',HYP:'event.HYP'};
const channelName = channel => t(channel.name);
const channelUnit = channel => t(channel.unit);
const eventName = kind => t(eventNames[kind] || kind);
function channelHelp(key,channel) {
  return channel.help?`<button class="term-help" data-term="${key}" data-title="${escape(channelName(channel))}" data-explanation="${escape(t(channel.help))}" aria-label="${escape(t('channel.helpAria',{name:channelName(channel)}))}">?</button>`:'';
}
let overview = null, activeView = 'report', detail = null, dayKey = null;
let dateRange = null, windowRange = null, fullRange = null, requestId = 0;
let rowLimit = 40, eventFilter = 'all', selectedEvent = null, cursor = null;
let plots = [], cursorFrame = null;

const fmt = (value, digits=1) => value == null ? '—' : Number(value).toFixed(digits);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const duration = minutes => {
  if (minutes == null) return '—';
  const total = Math.round(minutes);
  return t('duration',{hours:Math.floor(total/60),minutes:total%60});
};
const clock = (seconds, precise=false) => {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s/3600)+12;
  return `${h>=24?t('clock.nextDay'):''}${String(h%24).padStart(2,'0')}:${String(Math.floor(s%3600/60)).padStart(2,'0')}${precise?':'+String(s%60).padStart(2,'0'):''}`;
};
function card(label, value, note) {
  return `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value">${value}</div><div class="metric-note">${note}</div></div>`;
}
function showError(message='') {
  $('#error').hidden = !message;
  $('#error').textContent = message;
}
async function api(path, options) {
  const label=String(path).split('?')[0],started=performance.now();
  uiLog(`api-start ${label}`);
  try {
    const response = await fetch('api/'+localizedPath(path), options);
    const data = await response.json();
    uiLog(`api-end ${label} status=${response.status} duration_ms=${Math.round(performance.now()-started)}`);
    if (!response.ok || data.error) throw Error(data.error || t('error.readFailed'));
    return data;
  } catch(error) {
    uiLog(`api-error ${label} duration_ms=${Math.round(performance.now()-started)}`);
    throw error;
  }
}
function switchView(view) {
  uiLog(`view ${view}`);
  activeView = view;
  $$('.view').forEach(section => section.hidden = section.id !== view || !overview);
  $$('.nav').forEach(button => {
    button.classList.toggle('active', button.dataset.view === view);
    button.setAttribute('aria-current', button.dataset.view === view ? 'page' : 'false');
  });
  $('#title').textContent = t('header.'+view);
  $('#export').hidden = view === 'report';
  $('#export').textContent = t('export.'+view);
  showError();
  if (overview && view === 'overview') renderOverview();
  if (overview && view === 'report') loadReport();
  if (overview && view === 'detail' && !dayKey) {
    openDay([...overview.days].reverse().find(day => day.wave)?.date || overview.days.at(-1).date);
  }
  requestAnimationFrame(redraw);
}
async function refresh() {
  try {
    const data = await api('overview');
    overview = data.empty ? null : data;
    $('#empty').hidden = !!overview;
    $('#export').setAttribute('aria-disabled',!overview);
    if (!overview) {
      $$('.view').forEach(section => section.hidden = true);
      return;
    }
    $('#device').textContent = overview.device.model;
    $('#dateCoverage').textContent = `${overview.days[0].date} — ${overview.days.at(-1).date}`;
    $('#importStamp').textContent = t('status.importTime',{value:overview.imported_at.replace('T',' ')});
    $('#statusText').textContent = t('status.device',{model:overview.device.model,days:overview.days.length});
    for (const id of ['date','rangeStart','rangeEnd']) {
      $('#'+id).min = overview.days[0].date;
      $('#'+id).max = overview.days.at(-1).date;
    }
    if (!dateRange) presetRange(30, false);
    renderInfo();
    const bad = overview.files.filter(file => file.unreadable_ranges?.length);
    $('#notice').hidden = !bad.length;
    const bytes = bad.reduce((sum,file) => sum+file.unreadable_ranges.reduce((s,r) => s+r[1],0),0);
    $('#notice').textContent = t('notice.partialWave');
    switchView(activeView);
  } catch (error) { showError(error.message); }
}

// Summary calculations distinguish missing records, current records and zero usage.
function presetRange(days, render=true) {
  const end = [...overview.days].reverse().find(day=>!day.current&&day.minutes!=null)?.date || overview.days.at(-1).date;
  const start = new Date(end+'T12:00:00Z');
  if (days) start.setUTCDate(start.getUTCDate()-days+1);
  else start.setTime(new Date(overview.days[0].date+'T12:00:00Z').getTime());
  dateRange = [start.toISOString().slice(0,10),end];
  $('#rangeStart').value = dateRange[0];
  $('#rangeEnd').value = dateRange[1];
  $$('#period button').forEach(button => button.classList.toggle('selected', Number(button.dataset.days) === days));
  rowLimit = 40;
  if (render) renderOverview();
}
function selectedDays() {
  const lookup = new Map(overview.days.map(day => [day.date,day]));
  const result = [], end = new Date(dateRange[1]+'T12:00:00Z');
  for (let d = new Date(dateRange[0]+'T12:00:00Z'); d <= end; d.setUTCDate(d.getUTCDate()+1)) {
    const date = d.toISOString().slice(0,10);
    result.push(lookup.get(date) || {date,minutes:null,index:null,counts:{},missing:true,wave:false});
  }
  return result;
}
function renderOverview() {
  const days = selectedDays();
  const settled = days.filter(day => day.minutes != null && !day.current);
  const total = settled.reduce((sum,day) => sum+day.minutes,0);
  const events = settled.reduce((sum,day) => sum+Object.values(day.counts).reduce((a,b) => a+b,0),0);
  const missing = days.filter(day => day.missing).length;
  const current = days.filter(day => day.current).length;
  $('#metrics').innerHTML =
    card(t('metric.averageUse'), settled.length ? duration(total/settled.length) : '—',t('metric.settledDenominator',{count:settled.length})) +
    card(t('metric.totalUse'), fmt(total/60,1)+`<small>${t('metric.hours')}</small>`,t('metric.summaryRead')) +
    card(t('metric.eventRate'), total ? fmt(events/(total/60),2)+`<small>${t('metric.entriesPerHour')}</small>` : '—',t('metric.estimate',{events})) +
    card(t('metric.settled'),t('metric.days',{settled:settled.length,total:days.length}),t('metric.dayState',{missing,current}));
  $('#coverage').textContent = t('coverage.period',{start:dateRange[0],end:dateRange[1],waveDays:days.filter(day => day.wave).length});
  $('#rangeText').textContent = `${dateRange[0]} — ${dateRange[1]}`;
  renderRows(); redraw();
}
function renderRows() {
  const query = $('#search').value.trim();
  const days = selectedDays().filter(day => day.date.includes(query) && (!$('#onlyWave').checked || day.wave)).reverse();
  $('#rows').innerHTML = days.slice(0,rowLimit).map(day => {
    const state = day.missing ? t('status.noSummary') : day.wave ? t('status.waveAvailable') : t('status.waveMissing');
    return `<tr ${day.missing?'':`data-date="${day.date}" tabindex="0"`}><td>${day.date}</td><td>${day.current?t('status.pending'):duration(day.minutes)}</td><td>${fmt(day.index,2)}</td>${['OSA','CSA','HYP'].map(kind => `<td>${day.counts[kind]??'—'}</td>`).join('')}<td><span class="badge ${day.wave?'wave':''}">${state}</span></td><td>${day.missing?'':t('status.view')}</td></tr>`;
  }).join('');
  $('#rowCount').textContent = t('status.showCount',{shown:Math.min(rowLimit,days.length),total:days.length});
  $('#more').hidden = rowLimit >= days.length;
  $$('#rows tr[data-date]').forEach(row => {
    row.onclick = () => openDay(row.dataset.date);
    row.onkeydown = event => { if (event.key === 'Enter') openDay(row.dataset.date); };
  });
}
function canvasContext(canvas) {
  const width = Math.max(100,canvas.getBoundingClientRect().width);
  const height = Number(canvas.dataset.logicalHeight || canvas.getAttribute('height')) || 130;
  const scale = devicePixelRatio || 1;
  canvas.dataset.logicalHeight = height;
  canvas.width = width*scale; canvas.height = height*scale; canvas.style.height = height+'px';
  const ctx = canvas.getContext('2d'); ctx.scale(scale,scale); ctx.font = '10px sans-serif';
  return {ctx,width,height};
}
function tip(event,text) {
  const box = $('#tooltip'); box.textContent = text; box.hidden = false;
  box.style.left = Math.max(4,Math.min(innerWidth-250,event.clientX+12))+'px';
  box.style.top = Math.max(4,Math.min(innerHeight-100,event.clientY+12))+'px';
}
function hideTip() { $('#tooltip').hidden = true; }
function plotOverview(canvas,days,metric) {
  const {ctx,width,height} = canvasContext(canvas);
  const left=40,right=width-12,top=8,bottom=height-25;
  const values = days.map(day => metric === 'minutes' ? day.minutes == null ? null : day.minutes/60 : day.index);
  const max = Math.max(metric === 'minutes' ? 8 : 2,...values.filter(value => value != null))*1.12;
  ctx.strokeStyle='#e1e6eb';ctx.fillStyle='#6d7d89';
  for (let i=0;i<=4;i++) {
    const y=bottom-(bottom-top)*i/4;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();
    ctx.fillText((max*i/4).toFixed(1),3,y+3);
  }
  const bar=(right-left)/days.length;
  days.forEach((day,i) => {
    const value=values[i],x=left+i*bar;
    ctx.fillStyle=value==null ? day.current ? '#d5bd7c' : '#cbd3da' : metric==='minutes' ? '#5182a1' : '#a08f5a';
    const h=value==null ? 3 : (bottom-top)*value/max;
    ctx.fillRect(x+bar*.15,bottom-h,Math.max(.5,bar*.7),h);
  });
  ctx.fillStyle='#697d8b';
  for (const i of [...new Set([0,Math.floor(days.length/3),Math.floor(days.length*2/3),days.length-1])]) {
    ctx.textAlign=i===days.length-1?'right':'left';ctx.fillText(days[i].date,left+i*bar,bottom+18);
  }
  const at=event=>Math.max(0,Math.min(days.length-1,Math.floor((event.offsetX-left)/bar)));
  canvas.onmousemove=event=>{
    const i=at(event),day=days[i];
    const metricLabel = metric === 'minutes' ? t('plot.usageValue') : t('plot.rateValue');
    const value = values[i]==null ? (day.current ? t('status.pending') : t('status.noSummary')) : fmt(values[i],2)+(metric==='minutes'?' '+t('metric.hours'):' '+t('metric.entriesPerHour'));
    const status = day.wave ? t('status.waveAvailable') : day.missing ? t('status.noSummary') : t('status.waveMissing');
    tip(event,t('plot.waveStatus',{date:day.date,metric:metricLabel,value,status}));
  };
  canvas.onmouseleave=hideTip;
  canvas.onclick=event=>{const day=days[at(event)];if(!day.missing)openDay(day.date);};
}

async function openDay(date) {
  dayKey=date;$('#date').value=date;detail=null;selectedEvent=null;cursor=null;plots=[];
  windowRange=null;eventFilter='all';$('#charts').replaceChildren();$('#dayMetrics').replaceChildren();
  $('#eventList').replaceChildren();$('#stats').replaceChildren();$('#segments').replaceChildren();$('#timeline').replaceChildren();
  $('#waveNotice').textContent=t('status.loadingDay',{date});
  $('#dayState').textContent=t('error.reading');
  $('#noWave').hidden=true;
  $('.time-nav').hidden=true;
  $('.event-timeline').hidden=true;
  switchView('detail'); await loadDay(true);
}
async function loadDay(reset=false, requested=windowRange) {
  const id=++requestId, date=dayKey;
  $('#detailBody').classList.add('loading');showError();
  try {
    const params=new URLSearchParams({date});
    if (requested&&!reset) {params.set('start',requested[0]);params.set('end',requested[1]);}
    const data=await api('day?'+params);
    if(id!==requestId)return;
    detail=data;windowRange=data.range||requested||[0,86400];
    if(reset)fullRange=[...windowRange];
    cursor=null;renderDetail();
  } catch(error) {
    if(id===requestId){showError(t('status.unreadable',{date,error:error.message}));if(!detail){$('#dayState').textContent=t('error.readFailedState');$('#waveNotice').textContent=t('error.noWave');}}
  } finally {if(id===requestId)$('#detailBody').classList.remove('loading');}
}
function renderDetail() {
  const day=detail,total=day.events.length,frequency=day.minutes&&!day.current?total/(day.minutes/60):null;
  const counts=Object.fromEntries(['OSA','CSA','HYP'].map(kind=>[kind,day.events.filter(event=>event.kind===kind).length]));
  $('#dayState').textContent=day.current?t('detail.currentState'):t('detail.historyState');
  $('#dayMetrics').innerHTML=
    card(t('metric.totalUse'),day.current?t('status.pending'):duration(day.minutes),t('detail.deviceUseNote'))+
    card(t('metric.eventRate'),fmt(frequency,2)+(frequency==null?'':`<small>${t('metric.entriesPerHour')}</small>`),t('detail.eventRateDivision',{events:total}))+
    card(t('detail.wave'),duration(day.wave_seconds/60),t('detail.waveDuration',{segments:day.segments.length}))+
    card(t('detail.events'),`${counts.OSA}<small>OSA</small>${counts.CSA}<small>CSA</small>${counts.HYP}<small>HYP</small>`,t('detail.eventEntries'));
  const coverage=day.minutes?day.wave_seconds/(day.minutes*60):null;
  $('#waveNotice').textContent=day.wave_seconds?
    t('detail.waveCoverage',{seconds:day.wave_seconds.toLocaleString(),coverage:coverage!=null?t('status.waveCoverage',{percent:Math.round(coverage*100)}):'',duplicates:day.duplicates?t('status.duplicates',{count:day.duplicates})+' ':''}):
    t('detail.noWaveStatus');
  $('#noWave').hidden=!!day.wave_seconds;
  for(const selector of ['.time-nav','.segment-line','.event-timeline','.workspace-help'])$(selector).hidden=!day.wave_seconds;
  $$('#zoom button').forEach(button=>button.disabled=!day.wave_seconds);
  $('#advanced').disabled=!day.wave_seconds;
  $('#stats').innerHTML=Object.entries(channels).filter(([key])=>key!=='flow').map(([key,channel])=>`<tr><td>${channelName(channel)}${channelHelp(key,channel)}<small>${channelUnit(channel)}</small></td><td>${fmt(day.stats[key]?.median,key==='tidal'?0:1)}</td><td>${fmt(day.stats[key]?.p95,key==='tidal'?0:1)}</td></tr>`).join('');
  $('#segments').innerHTML=day.segments.map(([lo,hi],i)=>`<button data-segment="${i}" title="${t('detail.segmentTitle',{seconds:hi-lo})}">${clock(lo)}–${clock(hi)} (${Math.round((hi-lo)/60)}${t('common.minutes')})</button>`).join('');
  $$('[data-segment]').forEach(button=>button.onclick=()=>{const [lo,hi]=day.segments[Number(button.dataset.segment)];setWindow(Math.max(0,lo-5),Math.min(86400,hi+5));});
  $('#prev').disabled=overview.days[0].date===dayKey;$('#next').disabled=overview.days.at(-1).date===dayKey;
  renderEvents();renderCharts();updateTime();
}
function renderEvents() {
  const filtered=detail.events.map((event,index)=>({...event,index})).filter(event=>eventFilter==='all'||event.kind===eventFilter);
  $('#eventCount').textContent=t('status.events',{shown:filtered.length,total:detail.events.length});
  $$('#eventFilters button').forEach(button=>button.classList.toggle('selected',button.dataset.kind===eventFilter));
  $('#eventList').innerHTML=filtered.map(event=>`<tr data-event="${event.index}" tabindex="0" class="${selectedEvent===event.index?'selected':''}" aria-selected="${selectedEvent===event.index}"><td>${clock(event.second)}</td><td class="${event.kind}" title="${escape(eventName(event.kind))}">${event.kind}</td><td>${event.duration}</td></tr>`).join('')||`<tr><td colspan="3">${t('detail.noEventRows')}</td></tr>`;
  $$('[data-event]').forEach(row=>{
    row.onclick=()=>selectEvent(Number(row.dataset.event));
    row.onkeydown=event=>{if(event.key==='Enter')selectEvent(Number(row.dataset.event));};
  });
}
function selectEvent(index) {
  selectedEvent=index;const event=detail.events[index];
  if(detail.wave_seconds)setWindow(Math.max(0,event.second-120),Math.min(86400,event.second+180));
  else renderEvents();
}
function updateTime() {
  if(!windowRange)return;
  const [lo,hi]=windowRange;
  $('#windowLabel').textContent=clock(lo,true)+' — '+clock(hi,true);
  $('#pan').max=Math.max(0,86400-(hi-lo));$('#pan').value=lo;
  const isFull=fullRange&&Math.abs(lo-fullRange[0])<1&&Math.abs(hi-fullRange[1])<1;
  $$('#zoom button').forEach(button=>button.classList.toggle('selected',button.dataset.window==='all'?isFull:!isFull&&Math.abs(hi-lo-Number(button.dataset.window))<1));
  const visible=detail.events.map((event,index)=>({...event,index})).filter(event=>event.second+60>=lo&&event.second<=hi);
  $('#timeline').innerHTML=visible.map(event=>{
    const x=Math.max(0,(event.second-lo)/(hi-lo)*100),end=Math.min(100,(event.second+60-lo)/(hi-lo)*100);
    const label=t('marker.aria',{kind:event.kind,time:clock(event.second)});
    return `<button class="marker ${event.kind} ${selectedEvent===event.index?'selected':''}" data-marker="${event.index}" style="left:${x}%;width:${Math.max(.25,end-x)}%;top:${{OSA:0,CSA:16,HYP:32}[event.kind]}px" aria-label="${escape(label)}" title="${escape(eventName(event.kind)+' '+clock(event.second)+t('detail.eventMinute'))}"></button>`;
  }).join('');
  $$('[data-marker]').forEach(button=>button.onclick=()=>selectEvent(Number(button.dataset.marker)));
  $('#sampleHint').textContent=hi-lo<=60?t('detail.sampleAll'):t('detail.sampleOverviewText');
}
function setWindow(lo,hi) {
  lo=Math.max(0,lo);hi=Math.min(86400,hi);
  if(hi-lo<3||!detail?.wave_seconds)return;
  loadDay(false,[lo,hi]);
}
function panWindow(direction) {
  if(!windowRange||!detail?.wave_seconds)return;
  const width=windowRange[1]-windowRange[0],lo=Math.max(0,Math.min(86400-width,windowRange[0]+width*.8*direction));
  setWindow(lo,lo+width);
}
function visibleChannels() {return Object.entries(channels).filter(([key])=>$('#advanced').checked||['flow','ipap','epap','leak'].includes(key));}
function renderCharts() {
  $('#charts').innerHTML=detail.wave_seconds?visibleChannels().map(([key,channel])=>`<div class="chart-row"><div class="chart-title"><strong>${channelName(channel)}</strong>${channelHelp(key,channel)}<span class="unit">${channelUnit(channel)}</span><output id="value-${key}" aria-label="${escape(t('detail.cursorAria',{name:channelName(channel)}))}">—</output></div><canvas data-series="${key}" height="${channel.height}" aria-label="${escape(t('detail.chartAria',{name:channelName(channel)}))}"></canvas></div>`).join(''):'';
  redraw();
}
function nearest(points,time) {
  let lo=0,hi=points.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(points[mid][0]<time)lo=mid+1;else hi=mid;}
  const options=[points[lo-1],points[lo]].filter(Boolean);
  return options.sort((a,b)=>Math.abs(a[0]-time)-Math.abs(b[0]-time))[0];
}
function drawChart(canvas,key) {
  const points=detail.series[key]||[],channel=channels[key];
  const {ctx,width,height}=canvasContext(canvas);
  const left=46,right=width-5,top=7,bottom=height-23,[lo,hi]=windowRange;
  const values=points.map(point=>point[1]).filter(value=>value!=null);
  let min=values.length?Math.min(...values):0,max=values.length?Math.max(...values):1;
  if(min===max){min=Math.max(0,min-1);max+=1;}
  const pad=(max-min)*.08;min=Math.max(0,min-pad);max+=pad;
  const X=time=>left+(time-lo)/(hi-lo)*(right-left),Y=value=>bottom-(value-min)/(max-min)*(bottom-top);
  ctx.strokeStyle='#e1e7ec';ctx.fillStyle='#6f808c';
  for(let i=0;i<=2;i++) {
    const value=min+(max-min)*i/2,y=Y(value);ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();
    ctx.fillText(value.toFixed(key==='tidal'?0:1),1,y+3);
  }
  for(let i=0;i<=4;i++) {
    const time=lo+(hi-lo)*i/4;ctx.textAlign=i===4?'right':i===0?'left':'center';
    ctx.fillText(clock(time,hi-lo<=300),X(time),height-5);
  }
  ctx.save();ctx.beginPath();ctx.rect(left,top,right-left,bottom-top);ctx.clip();
  for(const event of detail.events) {
    if(event.second+60<lo||event.second>hi)continue;
    ctx.fillStyle={OSA:'#c58b5720',CSA:'#6d98b620',HYP:'#a8a05a20'}[event.kind];
    ctx.fillRect(X(event.second),top,Math.max(1,X(event.second+60)-X(event.second)),bottom-top);
  }
  ctx.strokeStyle=channel.color;ctx.lineWidth=1.15;ctx.beginPath();
  let pen=false;
  for(const [x,y] of points){if(y==null){pen=false;continue;}if(pen)ctx.lineTo(X(x),Y(y));else{ctx.moveTo(X(x),Y(y));pen=true;}}
  ctx.stroke();ctx.restore();
  const background=ctx.getImageData(0,0,canvas.width,canvas.height);
  const overlay=(time,drag)=>{
    ctx.putImageData(background,0,0);
    if(time==null){$('#value-'+key).textContent='—';return;}
    if(drag!=null){ctx.fillStyle='#447fa126';ctx.fillRect(X(Math.min(time,drag)),top,Math.abs(X(time)-X(drag)),bottom-top);}
    ctx.strokeStyle='#718797';ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(X(time),top);ctx.lineTo(X(time),bottom);ctx.stroke();ctx.setLineDash([]);
    const inSegment=detail.segments.some(([a,b])=>a<=time&&time<b),point=nearest(points,time);
    $('#value-'+key).textContent=!inSegment||!point||point[1]==null?t('detail.valueNoRecord'):t('detail.valueAt',{value:fmt(point[1],key==='tidal'?0:2),unit:channelUnit(channel),time:clock(point[0],true)});
  };
  plots.push({overlay});
  let drag=null;
  const at=event=>Math.max(lo,Math.min(hi,lo+(event.offsetX-left)/(right-left)*(hi-lo)));
  canvas.onmousedown=event=>{if(event.button===0)drag=at(event);};
  canvas.onmouseup=event=>{if(drag==null)return;const end=at(event),start=drag;drag=null;if(Math.abs(end-start)>=3)setWindow(Math.min(start,end),Math.max(start,end));};
  canvas.ondblclick=()=>setWindow(...fullRange);
  canvas.onmousemove=event=>{
    cursor=at(event);const selection=drag;
    if(cursorFrame)cancelAnimationFrame(cursorFrame);
    cursorFrame=requestAnimationFrame(()=>plots.forEach(plot=>plot.overlay(cursor,selection)));
  };
  canvas.onmouseleave=()=>{drag=null;cursor=null;if(cursorFrame)cancelAnimationFrame(cursorFrame);plots.forEach(plot=>plot.overlay(null));};
}
function redraw() {
  if(activeView==='overview'&&overview){const days=selectedDays();plotOverview($('#usage'),days,'minutes');plotOverview($('#eventsTrend'),days,'index');}
  if(activeView==='detail'&&detail&&windowRange){plots=[];$$('#charts canvas').forEach(canvas=>drawChart(canvas,canvas.dataset.series));}
}

function renderInfo() {
  const waves=overview.days.filter(day=>day.wave);
  const errors=overview.files.flatMap(file=>(file.unreadable_ranges||[]).map(range=>t('data.info.fileRange',{name:file.name,offset:range[0].toLocaleString(),bytes:range[1].toLocaleString()})));
  const fields=[[t('data.info.device'),overview.device.model],[t('data.info.serial'),overview.device.serial],[t('data.info.range'),`${overview.days[0].date} — ${overview.days.at(-1).date}`],[t('data.info.waveDays'),waves.length?t('data.info.waveDaysValue',{count:waves.length,start:waves[0].date,end:waves.at(-1).date}):t('data.info.noWave')],[t('data.info.imported'),overview.imported_at.replace('T',' ')],[t('data.info.source'),overview.source],[t('data.info.storage'),t('data.info.storageLocation')],[t('data.info.snapshot'),t('data.info.snapshotValue',{count:overview.files.length,size:fmt(overview.files.reduce((sum,file)=>sum+file.size,0)/1024/1024)})],[t('data.info.invalid'),t('data.info.invalidValue',{count:overview.invalid_packets.toLocaleString()})],[t('data.info.errors'),errors.length?t('data.info.errorValue',{count:errors.length}):t('data.info.noErrors')]];
  $('#dataInfo').innerHTML=fields.map(([key,value])=>`<dt>${key}</dt><dd>${escape(value)}</dd>`).join('');
  $('#readErrors').innerHTML=errors.length?errors.map(escape).join('<br>'):t('data.info.noErrors');
}
function exportCSV(event) {
  if(!overview){event.preventDefault();return;}
  const range=activeView==='detail'?[dayKey,dayKey]:['overview','report'].includes(activeView)?dateRange:[overview.days[0].date,overview.days.at(-1).date];
  $('#export').href='api/'+localizedPath('export?'+new URLSearchParams({start:range[0],end:range[1]}));
}

function showImport(){if(!$('#importDialog').open)$('#importDialog').showModal();api('status').then(s=>{$('#localSource').hidden=!s.local_paths;if(s.busy){$('#startImport').disabled=true;pollImport();}}).catch(e=>{$('#importProgress').textContent=e.message;});}
window.chooseFolder=path=>{$('#sourcePath').value=path;$('#archiveFile').value='';showImport();};
$('#archiveFile').onchange=()=>{$('#sourcePath').value='';};
async function pollImport() {
  try {
    const status=await api('status');$('#importProgress').textContent=status.error||status.message;
    if(status.busy){setTimeout(pollImport,800);return;}
    $('#startImport').disabled=false;
    if(!status.error){requestId++;detail=null;dayKey=null;dateRange=null;await refresh();$('#importDialog').close();}
  }catch(error){$('#importProgress').textContent=error.message;$('#startImport').disabled=false;}
}

// Event bindings; all actions use existing local data and the read-only decoder.
$$('.nav').forEach(button=>button.onclick=()=>switchView(button.dataset.view));
$$('#period button').forEach(button=>button.onclick=()=>presetRange(Number(button.dataset.days)));
$('#applyRange').onclick=()=>{
  const start=$('#rangeStart').value,end=$('#rangeEnd').value;
  if(!start||!end||start>end||start<overview.days[0].date||end>overview.days.at(-1).date){showError(t('status.invalidRange'));return;}
  showError();dateRange=[start,end];rowLimit=40;$$('#period button').forEach(button=>button.classList.remove('selected'));renderOverview();
};
$('#search').oninput=()=>{rowLimit=40;renderRows();};$('#onlyWave').onchange=()=>{rowLimit=40;renderRows();};
$('#more').onclick=()=>{rowLimit+=60;renderRows();};
$('#latest').onclick=()=>openDay([...overview.days].reverse().find(day=>day.wave)?.date||overview.days.at(-1).date);
$('#date').onchange=()=>{
  if(overview.days.some(day=>day.date===$('#date').value))openDay($('#date').value);
  else{showError(t('status.noRecordDay'));$('#date').value=dayKey;}
};
for(const [id,step] of [['prev',-1],['next',1]])$('#'+id).onclick=()=>{
  const next=overview.days[overview.days.findIndex(day=>day.date===dayKey)+step];if(next)openDay(next.date);
};
$$('#zoom button').forEach(button=>button.onclick=()=>{
  if(button.dataset.window==='all'){setWindow(...fullRange);return;}
  const width=Number(button.dataset.window);
  // Zoom around the chosen event, otherwise the first visible recorded sample;
  // a whole-night window may have a long gap at its geometric center.
  const focus=selectedEvent!=null?detail.events[selectedEvent].second+30:detail.segments.find(([lo,hi])=>hi>windowRange[0]&&lo<windowRange[1]);
  const center=typeof focus==='number'?focus:focus?Math.max(focus[0],windowRange[0])+width/2:(windowRange[0]+windowRange[1])/2;
  const lo=Math.max(0,Math.min(86400-width,center-width/2));setWindow(lo,lo+width);
});
$('#pan').onchange=()=>{const lo=Number($('#pan').value);setWindow(lo,lo+windowRange[1]-windowRange[0]);};
$('#panLeft').onclick=()=>panWindow(-1);$('#panRight').onclick=()=>panWindow(1);
$('#advanced').onchange=()=>{cursor=null;renderCharts();};
$$('#eventFilters button').forEach(button=>button.onclick=()=>{eventFilter=button.dataset.kind;renderEvents();});
$('#export').onclick=exportCSV;
for(const id of ['importNav','emptyImport','dataImport'])$('#'+id).onclick=showImport;
$('#closeDialog').onclick=()=>$('#importDialog').close();
$('#importForm').onsubmit=async event=>{
  event.preventDefault();
  $('#startImport').disabled=true;
  try{
    const file=$('#archiveFile').files[0];
    if(file){
      if(!/\.zip$/i.test(file.name)||file.size>8*1024**3)throw new Error(t('status.zip'));
      await new Promise((resolve,reject)=>{
        const xhr=new XMLHttpRequest();xhr.open('POST','api/'+localizedPath('upload'));xhr.setRequestHeader('Content-Type','application/zip');
        xhr.upload.onprogress=e=>{$('#importProgress').textContent=e.lengthComputable?t('status.uploadPercent',{percent:Math.round(e.loaded/e.total*100)}):t('status.uploading');};
        xhr.onload=()=>{let body;try{body=JSON.parse(xhr.responseText);}catch{reject(new Error(t('status.uploadInvalid')));return;}xhr.status===200?resolve():reject(new Error(body.error||t('status.uploadFailed')));};
        xhr.onerror=()=>reject(new Error(t('status.connection')));xhr.send(file);
      });
    }else{
      if(!$('#sourcePath').value)throw new Error(t('status.sourceRequired'));
      await api('import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:$('#sourcePath').value})});
    }
    pollImport();
  }catch(error){$('#importProgress').textContent=error.message;$('#startImport').disabled=false;}
};
document.onkeydown=event=>{
  if(activeView!=='detail'||$('#importDialog').open||['INPUT','TEXTAREA','SELECT','BUTTON'].includes(event.target.tagName))return;
  if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();panWindow(event.key==='ArrowLeft'?-1:1);}
};
let resizeTimer;window.onresize=()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(redraw,120);};
window.addEventListener('breath-view:locale',()=>{
  if(!overview)return;
  $('#device').textContent=overview.device.model;
  $('#importStamp').textContent=t('status.importTime',{value:overview.imported_at.replace('T',' ')});
  $('#statusText').textContent=t('status.device',{model:overview.device.model,days:overview.days.length});
  renderInfo();
  if(activeView==='overview')renderOverview();
  if(activeView==='detail'&&detail){renderDetail();}
});
