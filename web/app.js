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
const channels = {
  flow: {name:'流量（原始通道）',unit:'L/min',color:'#326c92',height:150},
  ipap: {name:'吸气压力 · IPAP',unit:'cmH₂O',color:'#417763',height:100,help:'吸气阶段的压力通道，用来帮助气流进入。按 OSCAR 的 BMC 旧格式解释；不是医生设定值，也不是压力越高睡得越好。'},
  epap: {name:'呼气压力 · EPAP',unit:'cmH₂O',color:'#6b819b',height:100,help:'呼气阶段维持气道开放的压力通道。此前单一“设备压力”显示的是这一通道。与吸气压力一起参考；本机通道含义仍待原厂软件核验。'},
  leak: {name:'设备漏气通道',unit:'L/min',color:'#a2793e',height:100},
  tidal: {name:'潮气量',unit:'mL',color:'#607f9a',height:95},
  ventilation: {name:'分钟通气量',unit:'L/min',color:'#6b8152',height:95},
  rate: {name:'呼吸频率',unit:'次/min',color:'#84709a',height:95}
};
const eventNames = {OSA:'阻塞性暂停',CSA:'中枢性暂停',HYP:'低通气'};
let overview = null, activeView = 'report', detail = null, dayKey = null;
let dateRange = null, windowRange = null, fullRange = null, requestId = 0;
let rowLimit = 40, eventFilter = 'all', selectedEvent = null, cursor = null;
let plots = [], cursorFrame = null;

const fmt = (value, digits=1) => value == null ? '—' : Number(value).toFixed(digits);
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const duration = minutes => {
  if (minutes == null) return '—';
  const total = Math.round(minutes);
  return `${Math.floor(total/60)} 小时 ${total%60} 分`;
};
const clock = (seconds, precise=false) => {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s/3600)+12;
  return `${h>=24?'次日 ':''}${String(h%24).padStart(2,'0')}:${String(Math.floor(s%3600/60)).padStart(2,'0')}${precise?':'+String(s%60).padStart(2,'0'):''}`;
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
    const response = await fetch('api/'+path, options);
    const data = await response.json();
    uiLog(`api-end ${label} status=${response.status} duration_ms=${Math.round(performance.now()-started)}`);
    if (!response.ok || data.error) throw Error(data.error || '读取失败');
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
  $('#title').textContent = {report:'我的睡眠',detail:'每日详情',overview:'期间统计',data:'数据管理'}[view];
  $('#export').hidden = view === 'report';
  $('#export').textContent = {report:'导出分析期间摘要',detail:'导出当天摘要',overview:'导出期间摘要',data:'导出全部摘要'}[view];
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
    $('#importStamp').textContent = '导入时间 '+overview.imported_at.replace('T',' ');
    $('#statusText').textContent = `${overview.device.model} · ${overview.days.length} 个治疗日 · 本地副本`;
    for (const id of ['date','rangeStart','rangeEnd']) {
      $('#'+id).min = overview.days[0].date;
      $('#'+id).max = overview.days.at(-1).date;
    }
    if (!dateRange) presetRange(30, false);
    renderInfo();
    const bad = overview.files.filter(file => file.unreadable_ranges?.length);
    $('#notice').hidden = !bad.length;
    const bytes = bad.reduce((sum,file) => sum+file.unreadable_ranges.reduce((s,r) => s+r[1],0),0);
    $('#notice').textContent = '部分波形未能读取，相关时段无法回看；已读取的摘要仍可查看。详情见“数据管理”。';
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
    card('平均使用时长', settled.length ? duration(total/settled.length) : '—',`分母：${settled.length} 个已结算记录日`) +
    card('累计设备使用', fmt(total/60,1)+'<small>小时</small>','读取设备历史摘要') +
    card('事件记录频率', total ? fmt(events/(total/60),2)+'<small>条目 /h</small>' : '—',`${events} 条记录 ÷ 使用小时数 · 估算`) +
    card('已结算记录',`${settled.length}<small>/ ${days.length} 天</small>`,`${missing} 天无摘要 · ${current} 天未结算`);
  $('#coverage').textContent = `统计期间 ${dateRange[0]} 至 ${dateRange[1]}。${days.filter(day => day.wave).length} 天有保留波形；缺失日期不作零使用处理，未结算日不参与时长和事件频率平均。`;
  $('#rangeText').textContent = `${dateRange[0]} — ${dateRange[1]}`;
  renderRows(); redraw();
}
function renderRows() {
  const query = $('#search').value.trim();
  const days = selectedDays().filter(day => day.date.includes(query) && (!$('#onlyWave').checked || day.wave)).reverse();
  $('#rows').innerHTML = days.slice(0,rowLimit).map(day => {
    const state = day.missing ? '无摘要' : day.wave ? '有保留波形' : '无保留波形';
    return `<tr ${day.missing?'':`data-date="${day.date}" tabindex="0"`}><td>${day.date}</td><td>${day.current?'未结算':duration(day.minutes)}</td><td>${fmt(day.index,2)}</td>${['OSA','CSA','HYP'].map(kind => `<td>${day.counts[kind]??'—'}</td>`).join('')}<td><span class="badge ${day.wave?'wave':''}">${state}</span></td><td>${day.missing?'':'查看'}</td></tr>`;
  }).join('');
  $('#rowCount').textContent = `显示 ${Math.min(rowLimit,days.length)} / ${days.length} 天`;
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
    tip(event,`${day.date}\n${metric==='minutes'?'使用时长':'事件记录频率'}：${values[i]==null?(day.current?'未结算':'无摘要'):fmt(values[i],2)+(metric==='minutes'?' 小时':' 条目 /h')}\n${day.wave?'有保留波形':day.missing?'没有摘要记录':'无保留波形'}`);
  };
  canvas.onmouseleave=hideTip;
  canvas.onclick=event=>{const day=days[at(event)];if(!day.missing)openDay(day.date);};
}

async function openDay(date) {
  dayKey=date;$('#date').value=date;detail=null;selectedEvent=null;cursor=null;plots=[];
  windowRange=null;eventFilter='all';$('#charts').replaceChildren();$('#dayMetrics').replaceChildren();
  $('#eventList').replaceChildren();$('#stats').replaceChildren();$('#segments').replaceChildren();$('#timeline').replaceChildren();
  $('#waveNotice').textContent='正在读取 '+date+' 的记录…';
  $('#dayState').textContent='读取中';
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
    if(id===requestId){showError('无法读取 '+date+'：'+error.message);if(!detail){$('#dayState').textContent='读取失败';$('#waveNotice').textContent='读取失败，没有显示该日期的数据。';}}
  } finally {if(id===requestId)$('#detailBody').classList.remove('loading');}
}
function renderDetail() {
  const day=detail,total=day.events.length,frequency=day.minutes&&!day.current?total/(day.minutes/60):null;
  const counts=Object.fromEntries(['OSA','CSA','HYP'].map(kind=>[kind,day.events.filter(event=>event.kind===kind).length]));
  $('#dayState').textContent=day.current?'当前日 · 未结算':'历史摘要';
  $('#dayMetrics').innerHTML=
    card('设备使用时长',day.current?'未结算':duration(day.minutes),'历史摘要；非睡眠时长')+
    card('事件记录频率',fmt(frequency,2)+(frequency==null?'':'<small>条目 /h</small>'),`${total} 条记录 ÷ 设备使用小时 · 估算`)+
    card('保留波形时长',duration(day.wave_seconds/60),`${day.segments.length} 个记录段 · 按波形包估算`)+
    card('呼吸事件条目',`${counts.OSA}<small>OSA</small>${counts.CSA}<small>CSA</small>${counts.HYP}<small>HYP</small>`,'记录时间精确到分钟');
  const coverage=day.minutes?day.wave_seconds/(day.minutes*60):null;
  $('#waveNotice').textContent=day.wave_seconds?
    `保留波形约 ${day.wave_seconds.toLocaleString()} 秒（每包按 1 秒计）${coverage!=null?'，约为摘要使用时长的 '+Math.round(coverage*100)+'%':''}。${day.duplicates?'保留 '+day.duplicates+' 个同秒时间戳的波形包。':''}统计仅覆盖现有数据。`:
    '无保留波形：可能已被覆盖、未保存或无法读取。可查阅设备摘要及事件列表。';
  $('#noWave').hidden=!!day.wave_seconds;
  for(const selector of ['.time-nav','.segment-line','.event-timeline','.workspace-help'])$(selector).hidden=!day.wave_seconds;
  $$('#zoom button').forEach(button=>button.disabled=!day.wave_seconds);
  $('#advanced').disabled=!day.wave_seconds;
  $('#stats').innerHTML=Object.entries(channels).filter(([key])=>key!=='flow').map(([key,channel])=>`<tr><td>${channel.name}${channelHelp(key,channel)}<small>${channel.unit}</small></td><td>${fmt(day.stats[key]?.median,key==='tidal'?0:1)}</td><td>${fmt(day.stats[key]?.p95,key==='tidal'?0:1)}</td></tr>`).join('');
  $('#segments').innerHTML=day.segments.map(([lo,hi],i)=>`<button data-segment="${i}" title="保留 ${hi-lo} 秒连续记录">${clock(lo)}–${clock(hi)} (${Math.round((hi-lo)/60)}分)</button>`).join('');
  $$('[data-segment]').forEach(button=>button.onclick=()=>{const [lo,hi]=day.segments[Number(button.dataset.segment)];setWindow(Math.max(0,lo-5),Math.min(86400,hi+5));});
  $('#prev').disabled=overview.days[0].date===dayKey;$('#next').disabled=overview.days.at(-1).date===dayKey;
  renderEvents();renderCharts();updateTime();
}
function renderEvents() {
  const filtered=detail.events.map((event,index)=>({...event,index})).filter(event=>eventFilter==='all'||event.kind===eventFilter);
  $('#eventCount').textContent=`${filtered.length} / ${detail.events.length} 条`;
  $$('#eventFilters button').forEach(button=>button.classList.toggle('selected',button.dataset.kind===eventFilter));
  $('#eventList').innerHTML=filtered.map(event=>`<tr data-event="${event.index}" tabindex="0" class="${selectedEvent===event.index?'selected':''}" aria-selected="${selectedEvent===event.index}"><td>${clock(event.second)}</td><td class="${event.kind}" title="${eventNames[event.kind]}">${event.kind}</td><td>${event.duration}</td></tr>`).join('')||'<tr><td colspan="3">没有符合条件的事件记录</td></tr>';
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
    return `<button class="marker ${event.kind} ${selectedEvent===event.index?'selected':''}" data-marker="${event.index}" style="left:${x}%;width:${Math.max(.25,end-x)}%;top:${{OSA:0,CSA:16,HYP:32}[event.kind]}px" aria-label="${event.kind} ${clock(event.second)}" title="${eventNames[event.kind]} ${clock(event.second)}（分钟精度）"></button>`;
  }).join('');
  $$('[data-marker]').forEach(button=>button.onclick=()=>selectEvent(Number(button.dataset.marker)));
  $('#sampleHint').textContent=hi-lo<=60?'流量：全部 25 Hz 采样点':'概览保留极值抽样；光标读数为附近显示点';
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
function channelHelp(key,channel) {
  return channel.help?`<button class="term-help" data-term="${key}" data-title="${escape(channel.name)}" data-explanation="${escape(channel.help)}" aria-label="解释${escape(channel.name)}">?</button>`:'';
}
function visibleChannels() {return Object.entries(channels).filter(([key])=>$('#advanced').checked||['flow','ipap','epap','leak'].includes(key));}
function renderCharts() {
  $('#charts').innerHTML=detail.wave_seconds?visibleChannels().map(([key,channel])=>`<div class="chart-row"><div class="chart-title"><strong>${channel.name}</strong>${channelHelp(key,channel)}<span class="unit">${channel.unit}</span><output id="value-${key}" aria-label="${channel.name}光标读数">—</output></div><canvas data-series="${key}" height="${channel.height}" aria-label="${channel.name}时间曲线"></canvas></div>`).join(''):'';
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
    $('#value-'+key).textContent=!inSegment||!point||point[1]==null?'无记录':`${fmt(point[1],key==='tidal'?0:2)} ${channel.unit} · ${clock(point[0],true)}`;
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
  const errors=overview.files.flatMap(file=>(file.unreadable_ranges||[]).map(range=>`${file.name}：文件偏移 ${range[0].toLocaleString()}，跳过 ${range[1].toLocaleString()} 字节`));
  const fields=[['设备',overview.device.model],['序列号',overview.device.serial],['记录范围',`${overview.days[0].date} — ${overview.days.at(-1).date}`],['有保留波形',waves.length?`${waves.length} 天（${waves[0].date} — ${waves.at(-1).date}，非连续）`:'无'],['导入时间',overview.imported_at.replace('T',' ')],['导入来源',overview.source],['存储位置','当前服务的数据目录（桌面电脑或 NAS）'],['快照文件',`${overview.files.length} 个文件，${fmt(overview.files.reduce((sum,file)=>sum+file.size,0)/1024/1024)} MiB`],['无效数据包',`${overview.invalid_packets.toLocaleString()} 个（含未使用空间与不可读区间）`],['读取异常',errors.length?`${errors.length} 个不可读区间；见下方明细`:'无']];
  $('#dataInfo').innerHTML=fields.map(([key,value])=>`<dt>${key}</dt><dd>${escape(value)}</dd>`).join('');
  $('#readErrors').innerHTML=errors.length?errors.map(escape).join('<br>'):'未发现文件读取异常。';
}
function exportCSV(event) {
  if(!overview){event.preventDefault();return;}
  const range=activeView==='detail'?[dayKey,dayKey]:['overview','report'].includes(activeView)?dateRange:[overview.days[0].date,overview.days.at(-1).date];
  $('#export').href='api/export?'+new URLSearchParams({start:range[0],end:range[1]});
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
  if(!start||!end||start>end||start<overview.days[0].date||end>overview.days.at(-1).date){showError('请选择记录范围内有效的开始和结束日期。');return;}
  showError();dateRange=[start,end];rowLimit=40;$$('#period button').forEach(button=>button.classList.remove('selected'));renderOverview();
};
$('#search').oninput=()=>{rowLimit=40;renderRows();};$('#onlyWave').onchange=()=>{rowLimit=40;renderRows();};
$('#more').onclick=()=>{rowLimit+=60;renderRows();};
$('#latest').onclick=()=>openDay([...overview.days].reverse().find(day=>day.wave)?.date||overview.days.at(-1).date);
$('#date').onchange=()=>{
  if(overview.days.some(day=>day.date===$('#date').value))openDay($('#date').value);
  else{showError('所选日期没有记录。');$('#date').value=dayKey;}
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
      if(!/\.zip$/i.test(file.name)||file.size>8*1024**3)throw new Error('请选择不超过 8 GiB 的 ZIP 文件');
      await new Promise((resolve,reject)=>{
        const xhr=new XMLHttpRequest();xhr.open('POST','api/upload');xhr.setRequestHeader('Content-Type','application/zip');
        xhr.upload.onprogress=e=>{$('#importProgress').textContent=e.lengthComputable?`正在上传 ${Math.round(e.loaded/e.total*100)}% · 上传后自动解析`:'正在上传';};
        xhr.onload=()=>{let body;try{body=JSON.parse(xhr.responseText);}catch{reject(new Error('上传响应无效'));return;}xhr.status===200?resolve():reject(new Error(body.error||'上传失败'));};
        xhr.onerror=()=>reject(new Error('连接中断，请检查网络后重新上传'));xhr.send(file);
      });
    }else{
      if(!$('#sourcePath').value)throw new Error('请先选择 ZIP 文件，或使用桌面工具栏选择数据');
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
