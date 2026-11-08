const money = value => new Intl.NumberFormat('ru-RU',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value)||0)+' ₽';
const state = {data:null, charts:[], selectedCategory:null, headItems:[]};
const byId = id => document.getElementById(id);
// Тема оформления: светлая/тёмная. Явный выбор пользователя хранится в
// localStorage (THEME_KEY); без выбора — системная prefers-color-scheme.
const THEME_KEY='theme';
function resolveTheme(pref, systemDark){
  if(pref==='light'||pref==='dark') return pref;
  return systemDark?'dark':'light';
}
function nextTheme(current){ return current==='dark'?'light':'dark'; }
function cssVar(name, fallback){
  try{
    const v=getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }catch(e){ return fallback; }
}
function currentTheme(){ return document.documentElement.dataset.theme==='dark'?'dark':'light'; }
function applyTheme(theme, persist){
  document.documentElement.dataset.theme=theme;
  const dark = theme==='dark';
  const btn=byId('theme-toggle');
  if(btn){
    btn.textContent=dark?'☀️':'🌙';
    btn.setAttribute('aria-label', dark?'Включить светлую тему':'Включить тёмную тему');
  }
  const meta=document.querySelector('meta[name="theme-color"]');
  if(meta) meta.content=dark?'#182433':'#206bc4';
  if(state.data){ state.charts.forEach(c=>{ if(c&&c.dispose) c.dispose(); }); state.charts=[]; render(); }
  if(persist){ try{ localStorage.setItem(THEME_KEY, theme); }catch(e){} }
}
function initTheme(){
  let stored=null;
  try{ stored=localStorage.getItem(THEME_KEY); }catch(e){}
  const sysDark=!!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  applyTheme(resolveTheme(stored, sysDark), false);
  const btn=byId('theme-toggle');
  if(btn) btn.addEventListener('click',()=>applyTheme(nextTheme(currentTheme()), true));
  if(window.matchMedia){
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e=>{
      let s=null;
      try{ s=localStorage.getItem(THEME_KEY); }catch(err){}
      if(s===null) applyTheme(resolveTheme('', e.matches), false);
    });
  }
}

async function fetchWithRetry(fetcher, url, options, attempts, delayMs){
  let lastError = null;
  for(let i = 0; i < attempts; i++){
    try{
      return await fetcher(url, options);
    }catch(e){
      lastError = e;
      if(i + 1 < attempts) await new Promise(r => setTimeout(r, delayMs));
    }
  }
  throw lastError;
}
async function loadData(){
  const response = await fetchWithRetry(fetch, 'data.json?ts='+Date.now(), {cache:'no-store'}, 3, 1000);
  if(!response.ok) throw new Error('Не удалось загрузить данные');
  state.data = await response.json();
  render();
}
function parseLegacyUpdatedAt(text){
  const m = /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})/.exec(text||'');
  if(!m) return '';
  return `${m[1]}T${m[2]}:00+03:00`;
}
function dataAgeText(isoString, nowMs){  const updated = Date.parse(isoString||'');
  if(!isoString || isNaN(updated)) return {text:'Нет данных', stale:true};
  const hours = Math.max(0, Math.floor((nowMs - updated) / 3600000));
  const text = hours < 1 ? 'обновлено менее часа назад' : hours < 48 ? `обновлено ${hours} ч назад` : `обновлено ${Math.floor(hours/24)} дн. назад`;
  return {text, stale: hours > 24};
}
function renderKPI(data){
  const s=(data.summary||{});
  byId('kpi-title').textContent='За текущий месяц';
  byId('month-total').textContent=money(s.month_total);
  byId('kpi-month-label').textContent=s.month_label;
  var prevLabel=prevMonthLabel(s.month_label||'');
  var pItems=monthItemsByLabel(data, prevLabel);
  byId('prev-total').textContent=money(pItems.reduce((a,t)=>a+t.total,0));
  byId('prev-month-label').textContent=prevLabel;
  byId('total-title').textContent='Всего расходов';
  byId('total').textContent=money(s.total);
  byId('total-label').textContent='за всё время';
  byId('average').textContent=money(s.average_month);
}
function render(){
  const d=state.data||{};
  renderKPI(d);
  byId('updated').textContent='🕐 '+(d.updated_at||'—');
  const ageIso = d.updated_at_iso || parseLegacyUpdatedAt(d.updated_at);
  const age = dataAgeText(ageIso, Date.now());
  const statusEl = byId('data-status');
  statusEl.textContent = ageIso ? age.text : 'Нет данных';
  statusEl.classList.toggle('stale', !!age.stale);
  window.__dashboardData=d;
  applyPeriod(d);
  renderMonthlyChart(d.months||[]);
  renderDeltas(d);
}
let period = 'month';
function monthItemsByLabel(data, label){ return (data.transactions||[]).filter(t => ((t.date)||'').indexOf(label||'')===0).map(t => ({category: t.category, total: (t.amount!=null?t.amount:t.total)})); }
function monthItems(data){ return monthItemsByLabel(data, (data.summary||{}).month_label||''); }
function aggregateByCategory(items){ const m = {}; items.forEach(x => { m[x.category] = (m[x.category]||0) + x.total; }); return Object.keys(m).map(k => ({category: k, total: m[k]})); }
function prevMonthLabel(label){ var p=(label||'').split('-'); if(p.length<2||!+p[0]||!+p[1]) return ''; var y=+p[0], m=+p[1]-1; if(m<1){m=12;y--;} return y+'-'+(m<10?'0':'')+m; }
function avgItems(data){ var s=(data.summary||{}); var n=Number(s.months_span)||((data.months)||[]).length||1; return (data.categories||[]).map(x => ({category: x.category, total: x.total/n})); }
function periodCount(data){ var s=data.summary||{}; var all=Number(s.count||0); if(period==='all') return {value:all, label:'записей'}; if(period==='avg'){ var n=Number(s.months_span)||((data.months)||[]).length||1; return {value: Math.round(all/n), label:'записей/мес'}; } var label = (period==='prev') ? prevMonthLabel(s.month_label||'') : (s.month_label||''); return {value: monthItemsByLabel(data,label).length, label:'записей'}; }
function categoryDeltas(transactions, currLabel){ var prev=prevMonthLabel(currLabel); function sum(l){ var m={}; (transactions||[]).forEach(t=>{ if(((t.date)||'').indexOf(l)===0){ m[t.category]=(m[t.category]||0)+t.amount; } }); return m; } var a=sum(currLabel), b=sum(prev); var keys={}; Object.keys(a).forEach(k=>keys[k]=1); Object.keys(b).forEach(k=>keys[k]=1); return Object.keys(keys).map(k=>{ var c=a[k]||0, p=b[k]||0; return {category:k, curr:c, prev:p, pct:(p>0)?Math.round((c-p)/p*100):null}; }).sort((x,y)=>y.curr-x.curr); }
function renderDeltas(data){ var s=data.summary||{}; var rows=categoryDeltas(data.transactions||[], s.month_label||''); var el=document.getElementById('category-deltas'); if(!el) return; el.innerHTML=rows.map(r=>{ var pill=r.pct===null?'<span class="delta-pill delta-new">новая</span>':'<span class="delta-pill '+(r.pct>=0?'delta-up':'delta-down')+'">'+(r.pct>=0?'▲ ':'▼ ')+Math.abs(r.pct)+'%</span>'; return '<div class="delta-row"><span class="delta-name">'+escapeHtml(r.category)+'</span>'+pill+'</div>'; }).join(''); var lb=document.getElementById('deltas-label'); if(lb) lb.textContent='Сравнение с '+prevMonthLabel(s.month_label||''); }
function applyPeriod(data){
  if(period==='avg'){ renderCategoryBars(avgItems(data)); byId('month-label').textContent='Среднее в месяц'; }
  else {
  const isMonth = period === 'month';
  const s=data.summary||{};
  const mItems = monthItems(data)||[];
  var prevLabel = prevMonthLabel(s.month_label||'');
  var pItems = monthItemsByLabel(data, prevLabel);
  var isPrev = period==='prev';
  var headItems = isMonth ? aggregateByCategory(mItems) : (isPrev ? aggregateByCategory(pItems) : (data.categories||[]));
  renderCategoryBars(headItems);
  byId('month-label').textContent = isMonth ? s.month_label : (isPrev ? prevLabel : 'Всё время');
  }
  state.selectedCategory = null;
  const counts = periodCount(data);
  byId('count').textContent = Number(counts.value||0).toLocaleString('ru-RU');
  byId('count-label').textContent = counts.label;
  document.querySelectorAll('[data-period]').forEach(b => { const on = b.dataset.period === period; if(b.classList.contains('seg-btn')||b.classList.contains('kpi-card')){b.classList.toggle('active', on);} b.setAttribute('aria-selected', on); });
  renderTransactionsForPeriod();
}
document.querySelectorAll('[data-period]').forEach(b => b.addEventListener('click', () => { period = b.dataset.period; applyPeriod(window.__dashboardData); }));
function chartBase(){
  const cv = typeof cssVar === 'function' ? cssVar : (n,f)=>f;
  return{animationDuration:450,tooltip:{trigger:'item',confine:true,backgroundColor:cv('--card','#fff'),borderColor:cv('--border','#e6e9ee'),textStyle:{color:cv('--text','#182433'),fontFamily:'system-ui'}},textStyle:{fontFamily:'system-ui'}}}
// Палитра по категориям. Раньше цвет сектора задавался только индексом в
// series[].data, поэтому ECharts красил по порядку, а порядок в режимах
// «месяц» и «всё время» разный: при переключении цвета прыгали. Теперь цвет
// привязан к имени категории и не зависит от режима. Порядок — как
// DEFAULT_CATEGORIES в categories.py, чтобы новые категории не ломали раскладку.
function categoryPalette(){return{
 'Продукты':'#206bc4', 'Дом и быт':'#2fb344', 'Транспорт':'#8b5cf6',
 'Здоровье':'#ef4444', 'Одежда':'#f59e0b', 'Ребёнок':'#ec4899',
 'Развлечения / Отдых':'#06b6d4', 'Кафе и рестораны':'#7c3aed',
 'Связь и интернет':'#0ea5e9', 'Коммунальные платежи':'#14b8a6',
 'Образование':'#a16207', 'Маркетплейсы':'#db2777',
 'Переводы другим людям':'#65a30d', 'Налоги':'#b91c1c',
 'Спорт и красота':'#9a3412', 'Прочее':'#64748b'
};}
function categoryColor(name){
  const key = (name == null ? '' : String(name)).trim();
  const palette = categoryPalette();
  if(Object.prototype.hasOwnProperty.call(palette, key)) return palette[key];
  // Категории нет в палитре (например, приехала из бота): цвет из хэша имени,
  // детерминированный, чтобы не менялся при перерисовке.
  let h = 0; const text = key || '—';
  for(let i=0;i<text.length;i++) h = (h*31 + text.charCodeAt(i)) >>> 0;
  return `hsl(${h % 360},58%,48%)`;
}
function buildCategoryData(items){return (items||[]).map(x => ({name:x.category, value:Number(x.total)||0, itemStyle:{color:categoryColor(x.category)}}));}
function buildBarData(items){return buildCategoryData(items).slice().sort((a,b)=>b.value-a.value);}
function selectedOpacity(name){ return (!state.selectedCategory || name === state.selectedCategory) ? 1 : 0.35; }
function renderCategoryBars(items){
  const el=byId('category-bars'); if(!el||!window.echarts)return;
  const cv = typeof cssVar === 'function' ? cssVar : (n,f)=>f;
  const chart=state.charts[0]||echarts.init(el); state.charts[0]=chart;
  state.headItems=(items||[]).slice();
  const data=buildBarData(items).map(d=>({...d,itemStyle:{...d.itemStyle,opacity:selectedOpacity(d.name)}}));
  el.style.height=Math.max(260, data.length*40+80)+'px';
  chart.setOption({...chartBase(),tooltip:{...chartBase().tooltip,trigger:'item',formatter:p=>`${p.name}<br><b>${money(p.value)}</b>`},grid:{left:8,right:64,top:8,bottom:8,containLabel:true},xAxis:{type:'value',axisLabel:{fontSize:10,color:cv('--muted','#667382')},splitLine:{lineStyle:{color:cv('--border','#e6e9ee')}}},yAxis:{type:'category',data:data.map(x=>x.name),axisLabel:{fontSize:11,color:cv('--text','#182433')}},series:[{type:'bar',data:data,label:{show:true,position:'right',formatter:p=>money(p.value),fontSize:10,color:cv('--text','#182433')}}]},true);
  chart.resize();
  if(chart.off) chart.off('click');
  if(chart.on) chart.on('click', onCategoryBarClick);
  updateBarsHint();
}
function periodName(){
  if(period==='month') return 'Текущий месяц';
  if(period==='prev') return 'Прошлый месяц';
  if(period==='avg') return 'Среднее';
  return 'Всё время';
}
function updateBarsHint(){
  const hint=byId('bars-hint'); if(!hint) return;
  hint.textContent = state.selectedCategory
    ? `Показана категория «${state.selectedCategory}» — нажмите на столбец ещё раз, чтобы показать все`
    : 'Нажмите на столбец, чтобы показать только эту категорию в операциях';
}
function onCategoryBarClick(params){
  const name = params && params.name;
  if(!name) return;
  state.selectedCategory = (state.selectedCategory === name) ? null : name;
  renderCategoryBars(state.headItems);
  renderTransactionsForPeriod();
}
let monthlyPointCount = 0;
let monthlyZoomFactor = 1;
const MONTHLY_ZOOM_MIN = 0.5, MONTHLY_ZOOM_MAX = 3, MONTHLY_ZOOM_STEP = 1.25;
// Ширина считается от базовой (как раньше при зуме 1), а зум масштабирует её
// целиком: иначе флор max(родитель, 640) съедает весь эффект кнопок и график
// визуально не меняется (при 3 точках ширина стояла на месте при любом зуме).
function monthlyChartBase(clientWidth, pointCount){ return Math.max(clientWidth||0, pointCount*80, 640); }
function monthlyChartWidth(clientWidth, pointCount, zoom){ return Math.max(320, monthlyChartBase(clientWidth, pointCount)*zoom); }
function setMonthlyZoom(dir){ monthlyZoomFactor = Math.min(MONTHLY_ZOOM_MAX, Math.max(MONTHLY_ZOOM_MIN, monthlyZoomFactor * (dir > 0 ? MONTHLY_ZOOM_STEP : 1/MONTHLY_ZOOM_STEP))); return monthlyZoomFactor; }
function fitMonthlyChart(){ var el=document.getElementById('monthly-chart'); if(!el||!el.parentElement) return; el.style.width=monthlyChartWidth(el.parentElement.clientWidth, monthlyPointCount, monthlyZoomFactor)+'px'; }
function applyMonthlyZoom(dir){ setMonthlyZoom(dir); fitMonthlyChart(); var chart=state.charts[1]; if(chart) chart.resize(); }
document.querySelectorAll('.chart-zoom button').forEach(b => b.addEventListener('click', () => { applyMonthlyZoom(b.id === 'chart-zoom-in' ? 1 : -1); }));
function renderMonthlyChart(items){
  const el=byId('monthly-chart'); if(!el||!window.echarts)return;
  const cv = typeof cssVar === 'function' ? cssVar : (n,f)=>f;
  const chart=state.charts[1]||echarts.init(el); state.charts[1]=chart;
  monthlyPointCount = (items||[]).length;
  chart.setOption({...chartBase(),grid:{left:42,right:12,top:18,bottom:36},tooltip:{...chartBase().tooltip,trigger:'axis',formatter:p=>`${p[0]?.axisValue}<br><b>${money(p[0]?.value)}</b>`},xAxis:{type:'category',data:items.map(x=>x.month),axisLabel:{fontSize:10,rotate:items.length>7?35:0,color:cv('--text','#182433')},splitLine:{lineStyle:{color:cv('--border','#e6e9ee')}}},yAxis:{type:'value',axisLabel:{fontSize:10,color:cv('--muted','#667382'),formatter:v=>v>=1000000?(v/1000000)+'M':v>=1000?(v/1000)+'k':v},splitLine:{lineStyle:{color:cv('--border','#e6e9ee')}}},series:[{type:'line',smooth:true,symbol:'circle',symbolSize:6,lineStyle:{width:3,color:'#206bc4'},areaStyle:{color:'#206bc422'},itemStyle:{color:'#206bc4'},data:items.map(x=>Number(x.total)||0)}]},true);
  fitMonthlyChart();
  chart.resize();
}
function periodMonthPrefix(data){
  const s=(data&&data.summary)||{};
  if(period==='month') return s.month_label||'';
  if(period==='prev') return prevMonthLabel(s.month_label||'');
  return '';
}
function renderTransactionsForPeriod(){
  const d=state.data||{};
  const prefix=periodMonthPrefix(d);
  const items=d.transactions||[];
  const label = prefix || periodName();
  renderTransactions(items, prefix, state.selectedCategory, label);
  const title=byId('operations-title');
  if(title) title.textContent = state.selectedCategory
    ? `Операции · ${state.selectedCategory}`
    : 'Операции';
}
function renderTransactions(items, monthLabel, category, scopeLabel){
  const query=(byId('search').value||'').trim().toLowerCase();
  const monthPrefix=monthLabel||'';
  const isoDate=x=>/^\d{4}-\d{2}-\d{2}/.test(x.date||'')?x.date:'';
  const monthItems=(items||[]).filter(x=>monthPrefix===''||isoDate(x).indexOf(monthPrefix)===0);
  const catFiltered=!category?monthItems:monthItems.filter(x=>(x.category||'')===category);
  const filtered=catFiltered.filter(x=>[x.date,x.category,x.subcategory,x.comment].join(' ').toLowerCase().includes(query));
  const scope = scopeLabel || (monthPrefix||'—');
  const catSuffix = category ? ` · ${category}` : '';
  byId('transaction-count').textContent=`Показано ${filtered.length} из ${catFiltered.length} (${scope}${catSuffix})`;
  byId('transactions-body').innerHTML=filtered.slice(0,200).map(x=>`<tr><td>${x.date||'—'}</td><td><span class="category-badge">${escapeHtml(x.category||'Прочее')}</span></td><td>${escapeHtml(displayNote(x)||'—')}</td><td class="amount">${money(x.amount)}</td></tr>`).join('')||'<tr><td colspan="4">Ничего не найдено</td></tr>';
}
// Описание операции для витрины: техническая метка идемпотентности бота
// (u{update_id} из Telegram, пишется в колонку «Комментарий» листа) —
// не часть описания траты, поэтому вырезается. Поиск по ней при этом
// продолжает работать: фильтр выше смотрит в сырые поля.
function displayNote(x){ const sub=(x.subcategory||'').trim(); if(sub) return sub; return (x.comment||'').replace(/\bu\d{6,}\b/g,'').trim(); }
function escapeHtml(value){return String(value).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
byId('refresh').addEventListener('click',()=>loadData().catch(showError));
byId('search').addEventListener('input',()=>state.data&&renderTransactionsForPeriod());
window.addEventListener('resize',()=>{fitMonthlyChart();state.charts.forEach(x=>x&&x.resize());});
function showError(){byId('updated').textContent='Ошибка загрузки';}
initTheme();
loadData().catch(showError);
if('serviceWorker' in navigator) window.addEventListener('load',()=>navigator.serviceWorker.register('sw.js'));
