const labels={overview:'总览',personality:'性格',love:'感情',career:'事业',wealth:'财运',health:'健康',family:'兄弟',children:'子女',move:'迁移',friends:'人际',home:'田宅',spirit:'福德',parents:'父母'};
const $=id=>document.getElementById(id);let user=null,sid=null,chartKey=null,sections={},sessionCursor=null,questionCursor=0,olderSeq=null,streamAbort=null,viewVersion=0,registerMode=false,loadingOlder=false;
const hourNames=['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'];for (let i = 0; i < 24; i++) {$('hour').add(new Option(`${i} 时`, String(i)));}for (let i = 0; i < 60; i++) {$('minute').add(new Option(`${i} 分`, String(i)));}
let currentChart=null,chartOffset=0,activeMode='analysis',activeTopic='overview',restoringView=true;
let natalSchool='sanhe',siHuaLayer='natal',siHuaDaXian=null,natalBranch=null,transformationRequest=0;
const lunarMonths=['正月','二月','三月','四月','五月','六月','七月','八月','九月','十月','冬月','腊月'];
const lunarDays=Array.from({length:30},(_,i)=>i<10?'初'+['一','二','三','四','五','六','七','八','九','十'][i]:i===19?'二十':i===29?'三十':(i<19?'十':'廿')+['一','二','三','四','五','六','七','八','九'][i<19?i-10:i-20]);
const clockIndex=h=>Math.floor((Number(h)+1)/2)%12;
let calendarMode='solar',lunarYearInfo=null,calendarRequest=0;
function setSelectOptions(select,values,suffix,preferred){
  select.replaceChildren();
  for(const value of values)select.add(new Option(typeof suffix==='function'?suffix(value):`${value} ${suffix}`,String(value)));
  select.value=values.includes(Number(preferred))?String(preferred):String(values[0]);
}
async function updateCalendarDays(){
  const year=+$('year').value,month=+$('month').value,request=++calendarRequest;
  if(calendarMode==='lunar'){
    try{
      if(!lunarYearInfo||lunarYearInfo.year!==year)lunarYearInfo=await api(`/api/calendar/lunar-years/${year}`);
      if(request!==calendarRequest)return;
      const hasLeap=lunarYearInfo.leap_month===month;
      $('leapMonthWrap').classList.toggle('hidden',!hasLeap);
      if(!hasLeap)$('leapMonth').checked=false;
      const signed=$('leapMonth').checked?-month:month;
      setSelectOptions($('day'),Array.from({length:lunarYearInfo.months[String(signed)]},(_,i)=>i+1),n=>lunarDays[n-1],$('day').value);
      $('calendarHint').textContent='';
    }catch(e){$('calendarHint').textContent=e.message}
  }else{
    $('leapMonthWrap').classList.add('hidden');$('leapMonth').checked=false;
    setSelectOptions($('day'),Array.from({length:new Date(year,month,0).getDate()},(_,i)=>i+1),'日',$('day').value);
    $('calendarHint').textContent='';
  }
}
function setCalendar(mode){
  calendarMode=mode;
  $('calendarLabel').textContent=mode==='lunar'?'（农历）':'（公历）';
  for(const [id,active] of [['solarMode',mode==='solar'],['lunarMode',mode==='lunar']]){
    $(id).classList.toggle('active',active);$(id).setAttribute('aria-pressed',String(active));
  }
  setSelectOptions($('year'),Array.from({length:2026-(mode==='lunar'?1999:2000)+1},(_,i)=>2026-i),'年',$('year').value||2000);
  setSelectOptions($('month'),Array.from({length:12},(_,i)=>i+1),mode==='lunar'?n=>lunarMonths[n-1]:'月',$('month').value||1);
  updateCalendarDays();
}
setSelectOptions($('month'),Array.from({length:12},(_,i)=>i+1),'月',1);
setCalendar('solar');$('year').value='2000';updateCalendarDays();
$('solarMode').onclick=()=>setCalendar('solar');$('lunarMode').onclick=()=>setCalendar('lunar');
$('year').onchange=updateCalendarDays;$('month').onchange=updateCalendarDays;$('leapMonth').onchange=updateCalendarDays;
function updateHourHint() {
  const h = Number($('hour').value);
  const m = Number($('minute').value);
  const i = clockIndex(h);
  const pad = n => String(n).padStart(2, '0');

  const ranges = [
    '23:00–01:00',
    '01:00–03:00',
    '03:00–05:00',
    '05:00–07:00',
    '07:00–09:00',
    '09:00–11:00',
    '11:00–13:00',
    '13:00–15:00',
    '15:00–17:00',
    '17:00–19:00',
    '19:00–21:00',
    '21:00–23:00'
  ];

  const name = hourNames[i];

  $('hourBadge').textContent = name;
  $('hourHint').textContent =
    `${pad(h)}:${pad(m)} · ${name}时 （${ranges[i]}）`;

  // 如果启用了“不知道出生时间”
  const unknown = $('unknownBirthTime');

  if (unknown?.checked) {
    $('hourBadge').textContent = '子';
    $('hourHint').textContent =
      '出生时间未知 · 暂以子时（23:00–01:00）起盘';
  }
}

$('hour').onchange = updateHourHint;
$('minute').onchange = updateHourHint;

$('unknownBirthTime')?.addEventListener('change', e => {
  if (e.target.checked) {
    $('hour').value = '23';
    $('minute').value = '0';
  }

  $('hour').disabled = e.target.checked;
  $('minute').disabled = e.target.checked;

  updateHourHint();
});

updateHourHint();
function showBirth(){ document.body.classList.remove('chartActive'); $('chartMenu').classList.add('hidden');$('headerModes').classList.add('hidden');$('chartMenu').open=false;$('birthView').classList.remove('hidden');$('chartBox').classList.add('hidden');window.scrollTo({top:0,behavior:'smooth'});persistView() }
function showMode(mode){
  activeMode=mode;const inChart=$('birthView').classList.contains('hidden');$('chartMenu').classList.toggle('hidden',!inChart);$('headerModes').classList.toggle('hidden',!inChart);
  $('chartMenu').open=false;
  const chat=mode==='chat';
  $('analysisPanel').classList.toggle('hidden',chat);
  $('natalPanel').classList.toggle('hidden',!currentChart?.natal_chart);
  $('chatPanel').classList.toggle('hidden',!chat);
  document.querySelector('.chartLayout').classList.toggle('chatFocus',chat);
  document.querySelector('.chartLayout').classList.toggle('noNatal',!currentChart?.natal_chart);
  $('analysisMode').classList.toggle('active',!chat);
  $('chatMode').classList.toggle('active',chat);
  $('analysisMode').setAttribute('aria-selected',String(!chat));
  $('chatMode').setAttribute('aria-selected',String(chat));
  if(chat) syncChatEmpty();
  persistView();
}
$('homeBrand').onclick=showBirth;$('backToBirth').onclick=showBirth;$('analysisMode').onclick=()=>showMode('analysis');$('chatMode').onclick=()=>showMode('chat');
$('newChart').onclick=()=>{showBirth();$('year').value='2000';$('month').value='1';$('day').value='1';$('hour').value='0';$('minute').value='0';$('birthName').value='';resetLocation();$('gender').value='male';setCalendar('solar');updateHourHint()};
$('allRecords').onclick=()=>{showBirth();document.querySelector('.recentHeader').scrollIntoView({behavior:'smooth'})};
function authHeaders(){return {}}; // Browser authentication uses the HttpOnly cookie.
async function api(path,method='GET',data,signal){const r=await fetch(path,{method,credentials:'same-origin',headers:{...authHeaders(),...(data?{'Content-Type':'application/json'}:{})},body:data?JSON.stringify(data):undefined,signal});const j=await r.json().catch(()=>({}));if(!r.ok){const error=Error(typeof j.detail==='string'?j.detail:JSON.stringify(j.detail||r.statusText));error.status=r.status;if(r.status===401&&user)clearAuthState();throw error}return j}
function notice(s){$('notice').textContent=s}function setAuth(){$('account').textContent=user?user.username:'访客';$('authButton').classList.toggle('hidden',!!user);$('logoutButton').classList.toggle('hidden',!user);$('newChat').classList.toggle('hidden',!user);$('chatNewSession').classList.toggle('hidden',!user);$('ask').disabled=!user;$('question').disabled=!user;$('question').placeholder=user?'请输入问题':'登录后可提问并保存历史';$('guestHint').classList.toggle('hidden',!!user);if(!user){$('savedChartList').replaceChildren();$('savedChartCount').textContent='';$('clearCharts').classList.add('hidden');$('moreCharts').classList.add('hidden');$('savedChartHint').textContent='登录后，排盘记录会保存到账号。';$('sessionList').replaceChildren();$('chatSessionList').replaceChildren();$('recentCount').textContent='';$('questionNav').replaceChildren()}}
function abortView(){viewVersion++;streamAbort?.abort();streamAbort=null}
function plain(text){return (text||'').replace(/\*\*/g,'').replace(/【[^】]+】/g,'').replace(/\s+/g,' ').trim()}
function preview(text){let m=(text||'').match(/\*\*【一句话定调】\*\*\s*([^\n]+)/);return plain(m?.[1]||(text||'').split(/\n\n/)[1]||'').slice(0,92)}
function mainStars(text){return (text||'').match(/本宫主星[：:]([^\n]+)/)?.[1]?.trim()||''}
const analysisTopics=[['overview','总览'],['wealth','财运'],['career','事业'],['love','感情'],['personality','性格'],['health','健康'],['family','兄弟'],['children','子女'],['move','迁移'],['friends','人际'],['home','田宅'],['spirit','福德'],['parents','父母']];
function reportGroups(text){
  const groups=[];
  for(const block of (text||'').split(/\n\s*\n/).map(x=>x.trim()).filter(Boolean)){
    const heading=block.match(/^\*\*【([^】]+)】\*\*\s*$/)||block.match(/^#{2,4}\s+(.+)$/);
    if(heading){groups.push({title:heading[1],blocks:[]});continue}
    if(!groups.length)groups.push({title:'原文',blocks:[]});
    groups.at(-1).blocks.push(block);
  }
  return groups;
}
function reportParagraph(parent,text,cls=''){
  const p=document.createElement('p');p.className=cls;p.textContent=text.replace(/\*\*/g,'');parent.append(p);
}
function reportDisclosure(parent,title,blocks){
  if(!blocks.length)return;
  const detail=document.createElement('details');detail.className='reportDisclosure';
  const summary=document.createElement('summary');summary.textContent=title;detail.append(summary);
  const content=document.createElement('div');content.className='disclosureContent';
  for(const block of blocks)reportParagraph(content,block);
  detail.append(content);parent.append(detail);
}
function renderReportContent(text){
  const article=$('chartContent');article.replaceChildren();
  const groups=reportGroups(text),intro=groups[0];
  if(intro){
    const lead=document.createElement('section');lead.className='reportIntro';
    const kicker=document.createElement('span');kicker.className='reportKicker';kicker.textContent='命盘提要';lead.append(kicker);
    intro.blocks.forEach((block,index)=>reportParagraph(lead,block,index===0?'primaryFinding':'actionFinding'));
    article.append(lead);
  }
  for(const group of groups.slice(1)){
    if(group.title==='一句话定调'){
      const quote=document.createElement('blockquote');quote.className='reportQuote';quote.textContent=group.blocks.map(plain).join(' ');article.append(quote);
    }else if(group.title==='核心论断'){
      const core=document.createElement('section');core.className='reportCore';
      const heading=document.createElement('h3');heading.textContent=group.title;core.append(heading);
      if(group.blocks[0])reportParagraph(core,group.blocks[0]);
      article.append(core);
      reportDisclosure(article,'展开更多核心论断',group.blocks.slice(1));
    }else reportDisclosure(article,group.title,group.blocks);
  }
}
function renderReport(id){
  activeTopic=id;
  const title=id==='overview'?'命格总览':labels[id];
  $('insightTitle').textContent=title;
  $('insightStar').textContent=mainStars(sections[id])?'原文主星 · '+mainStars(sections[id]):'命盘原文 · '+title;
  $('insightSummary').textContent=preview(sections[id]);
  $('detailTitle').textContent=title+' · 原文解读';
  renderReportContent(sections[id]);
  for(const b of $('tabs').children)b.classList.toggle('active',b.dataset.section===id);
  showMode('analysis');
  document.querySelector('.analysisScroll').scrollTop=0;
}
function showChart(j){
 document.body.classList.add('chartActive');
 renderNatal(j);
  currentChart=j;
  $('birthView').classList.add('hidden');
  chartKey=j.chart_key;sections=j.sections;
  $('chartBox').classList.remove('hidden');
  $('chartTitle').textContent=j.name||j.input_birth?.name||`${j.birth.year}年${j.birth.month}月${j.birth.day}日 · ${j.birth.gender==='male'?'男命':'女命'}`;
  const input=j.input_birth;
  const sourceDate=input?.calendar==='lunar'?`农历 ${input.year}年${input.leap_month?'闰':''}${input.month}月${input.day}日 → `:'';
  $('chartMeta').textContent=`${sourceDate}公历 ${j.birth.year}年${j.birth.month}月${j.birth.day}日 · ${hourNames[j.birth.hour]}时`;
  $('tabs').replaceChildren();
  for(const [id,name] of analysisTopics){const b=document.createElement('button');b.dataset.section=id;b.textContent=name;b.onclick=()=>renderReport(id);$('tabs').append(b)}
  renderReport('overview');window.scrollTo({top:0,behavior:'instant'});
}
$('loadChart').onclick=async()=>{
 const name=$('birthName').value.trim();$('nameError').textContent='';
 if(!$('birthLocation').value){$('chartNotice').textContent='请选择出生区县';$('locationTrigger').focus();return}
 if(!name){$('nameError').textContent='请输入姓名，为这张命盘命名';$('birthName').focus();return}
 const button=$('loadChart');button.disabled=true;
 try{
  $('chartNotice').textContent='正在查找…';
  const input={location_id:$('birthLocation').value,time_fold:+$('timeFold').value,name,calendar:calendarMode,year:+$('year').value,month:+$('month').value,day:+$('day').value,leap_month:$('leapMonth').checked,clock_hour:+$('hour').value,minute:+$('minute').value,hour:clockIndex($('hour').value),gender:$('gender').value};
  const j=await api(user?'/api/saved-charts':'/api/charts/resolve','POST',input);
  await selectSession(null);showChart(j);$('chartNotice').textContent='';if(user)await loadSavedCharts(true);
 }catch(e){$('chartNotice').textContent=e.message}finally{button.disabled=false}
};
function savedDate(input){return input.calendar==='lunar'?`农历${input.year}年${input.leap_month?'闰':''}${lunarMonths[input.month-1]}${lunarDays[input.day-1]}`:`公历${input.year}年${input.month}月${input.day}日`}
async function fillBirth(input){
 await restoreLocation(input);
 $('birthName').value=input.name||'';setCalendar(input.calendar||'solar');$('year').value=String(input.year);$('month').value=String(input.month);
 return updateCalendarDays().then(()=>{$('leapMonth').checked=!!input.leap_month;return updateCalendarDays()}).then(()=>{
  $('day').value=String(input.day);$('hour').value=String(input.clock_hour??(input.hour===0?0:input.hour*2));$('minute').value=String(input.minute||0);$('gender').value=input.gender;updateHourHint();
 });
}
function recordAction(kind,label){
 const b=document.createElement('button');b.type='button';b.className=`recordAction ${kind}`;b.title=label;b.setAttribute('aria-label',label);
 b.innerHTML=kind==='rename'?'<svg viewBox="0 0 20 20" width="16" height="16" fill="none" aria-hidden="true"><path d="m12.5 3.5 4 4M3 17l4.5-1L17 6.5a2.8 2.8 0 0 0-4-4L3.5 12 3 17Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>':'<span aria-hidden="true">×</span>';
 return b;
}
async function loadSavedCharts(reset=false){
 if(!user)return;const owner=user.id;if(reset){chartOffset=0;$('savedChartList').replaceChildren()}
 const j=await api(`/api/saved-charts?offset=${chartOffset}`);if(user?.id!==owner)return;chartOffset+=j.items.length;
 for(const item of j.items){
  const wrap=document.createElement('div'),actions=document.createElement('div'),b=document.createElement('button'),title=document.createElement('strong'),meta=document.createElement('span');b.type='button';b.className='savedChart';wrap.className='savedChartEntry';wrap.dataset.chartId=item.id;actions.className='recordActions';
  title.textContent=`${item.name} · ${savedDate(item.input_birth)} · ${hourNames[item.input_birth.hour]}时`;
  meta.textContent=`${item.input_birth.gender==='male'?'男':'女'} · ${new Date(item.updated_at).toLocaleString('zh-CN')}`;b.append(title,meta);
  b.onclick=async()=>{try{await selectSession(null);const c=await api('/api/charts/resolve','POST',item.input_birth);await fillBirth(item.input_birth);showChart({...c,name:item.name,input_birth:item.input_birth,saved_chart_id:item.id})}catch(e){$('chartNotice').textContent=e.message}};
  const rename=recordAction('rename',`重命名命盘：${item.name}`),del=recordAction('delete',`删除命盘：${item.name}`);
  rename.onclick=async()=>{const name=await actionDialog({title:'重命名命盘',message:'为这张命盘设置一个方便查找的名称。',value:item.name,label:'命盘名称',maxLength:80,confirm:'保存'});if(!name)return;try{
   const updated=await api(`/api/saved-charts/${item.id}`,'PATCH',{name});
   if(currentChart?.saved_chart_id===item.id){currentChart={...currentChart,name:updated.name,input_birth:updated.input_birth};$('chartTitle').textContent=updated.name;$('birthName').value=updated.name;renderNatal(currentChart);persistView()}
   await loadSavedCharts(true);
  }catch(e){$('savedChartHint').textContent=e.message}};
  del.onclick=async()=>{if(!await actionDialog({title:'删除这张命盘？',message:`将删除“${item.name}”的排盘记录，对话记录会保留。`,confirm:'删除命盘',danger:true}))return;try{await api(`/api/saved-charts/${item.id}`,'DELETE');if(currentChart?.saved_chart_id===item.id)delete currentChart.saved_chart_id;await loadSavedCharts(true)}catch(e){$('savedChartHint').textContent=e.message}};
  actions.append(rename,del);wrap.append(b,actions);$('savedChartList').append(wrap);
 }
 $('savedChartCount').textContent=String(j.total);$('savedChartHint').textContent=j.total?'已保存到账号':'还没有排盘记录，起盘后会自动保存。';$('clearCharts').classList.toggle('hidden',!j.total);$('moreCharts').classList.toggle('hidden',!j.has_more);
}
$('moreCharts').onclick=()=>loadSavedCharts().catch(e=>$('savedChartHint').textContent=e.message);
$('clearCharts').onclick=async()=>{if(!await actionDialog({title:'清空排盘记录？',message:'将清空当前账号保存的所有排盘，对话记录会保留。',confirm:'清空记录',danger:true}))return;try{await api('/api/saved-charts','DELETE');await loadSavedCharts(true)}catch(e){$('savedChartHint').textContent=e.message}};

function syncChatEmpty(){ $('chatEmpty').classList.toggle('hidden',$('messages').children.length>0) }
function appendInline(parent,text,refs){
  const pattern=/\*\*([^*]+)\*\*|`([^`]+)`|\[天纪#(\d+)\]/g;let last=0,match;
  while((match=pattern.exec(text))){
    parent.append(document.createTextNode(text.slice(last,match.index)));
    if(match[3]){
      const ref=refs.get(Number(match[3])),bvid=ref?.bvid;
      if(bvid&&/^BV[0-9A-Za-z]+$/.test(bvid)){
        const seconds=(ref.t_hms||'').split(':').reduce((n,x)=>n*60+Number(x||0),0);
        const a=document.createElement('a');a.className='citationLink';a.textContent='出处 ↗';
        a.href=`https://www.bilibili.com/video/${bvid}?p=${Math.max(1,Number(ref.part)||1)}&t=${Number.isFinite(seconds)?seconds:0}`;
        a.target='_blank';a.rel='noopener noreferrer';
        a.title=`《天纪》引文 #${match[3]} · ${ref.t_hms||'视频出处'}`;parent.append(a);
      }else{const span=document.createElement('span');span.className='citationUnlinked';span.textContent=`〔天纪#${match[3]}〕`;parent.append(span)}
    }else{
      const el=document.createElement(match[1]?'strong':'code');
      if(match[1])appendInline(el,match[1],refs);else el.textContent=match[2];
      parent.append(el);
    }
    last=pattern.lastIndex;
  }
  parent.append(document.createTextNode(text.slice(last)));
}
function renderMessageText(parent,text,sourceRefs=[]){
  const refs=new Map(sourceRefs.map(ref=>[Number(ref.id),ref]));
  let list=null;
  for(const line of text.split(/\n/)){
    const trimmed=line.trim();
    if(!trimmed){list=null;continue}
    const bullet=trimmed.match(/^[-*]\s+(.+)$/),numbered=trimmed.match(/^\d+[.)]\s+(.+)$/),heading=trimmed.match(/^#{1,4}\s+(.+)$/);
    if(bullet||numbered){
      const tag=bullet?'ul':'ol';
      if(!list||list.tagName.toLowerCase()!==tag){list=document.createElement(tag);parent.append(list)}
      const item=document.createElement('li');appendInline(item,(bullet||numbered)[1],refs);list.append(item);
    }else{
      list=null;const el=document.createElement(heading?'h4':'p');appendInline(el,heading?heading[1]:trimmed,refs);parent.append(el);
    }
  }
}
function aiDisclaimer(){const span=document.createElement('span');span.className='aiDisclaimer';span.textContent='内容由AI生成 仅供参考。';return span}
function bubble(row){
  const div=document.createElement('div');div.className='bubble '+(row.role==='user'?'user':'assistant');div.dataset.seq=row.seq;
  const tag=document.createElement('span'),body=document.createElement('div');tag.className='bubbleRole';body.className='bubbleBody';
  tag.textContent=row.role==='user'?'你':'紫微研习';renderMessageText(body,row.content.text||'',row.content.source_refs||[]);div.append(tag);if(row.role==='assistant'&&row.content.reasoning){const thought=reasoningPanel(row.content.reasoning,false);div.append(thought)}div.append(body);if(row.role==='assistant')div.append(aiDisclaimer());return div;
}
function renderRows(rows,prepend=false){
  const box=$('messages'),history=$('history'),oldHeight=history.scrollHeight,oldTop=history.scrollTop;
  for(const row of (prepend?[...rows].reverse():rows)){
    if(box.querySelector(`[data-seq="${row.seq}"]`))continue;
    if(prepend)box.prepend(bubble(row));else box.append(bubble(row));
  }
  syncChatEmpty();
  if(prepend)history.scrollTop=oldTop+history.scrollHeight-oldHeight;else history.scrollTop=history.scrollHeight;
}
function sessionEntry(item){
  const wrap=document.createElement('div'),b=document.createElement('button'),meta=document.createElement('div'),actions=document.createElement('div');
  wrap.className='sessionEntry';b.className='session'+(String(item.id)===sid?' active':'');b.textContent=item.title;b.dataset.sid=item.id;b.onclick=()=>selectSession(String(item.id));
  meta.className='sessionMeta';meta.textContent=new Date(item.last_interaction_at).toLocaleString('zh-CN');actions.className='sessionActions';
  const rename=recordAction('rename',`重命名对话：${item.title}`),del=recordAction('delete',`删除对话：${item.title}`);
  rename.onclick=async()=>{const title=await actionDialog({title:'重命名对话',message:'为这次对话设置一个方便查找的标题。',value:item.title,confirm:'保存'});if(!title)return;try{await api(`/api/sessions/${item.id}`,'PATCH',{title});await loadSessions(true);if(sid===String(item.id))$('chatTitle').textContent=title}catch(e){notice(e.message)}};
  del.onclick=async()=>{if(!await actionDialog({title:'删除这次对话？',message:'删除后，这次对话将不再出现在记录中。',confirm:'删除对话',danger:true}))return;try{await api(`/api/sessions/${item.id}`,'DELETE');if(sid===String(item.id))await selectSession(null);await loadSessions(true)}catch(e){notice(e.message)}};
  actions.append(rename,del);wrap.append(b,meta,actions);return wrap;
}
async function loadSessions(reset=false){
  if(!user)return;const owner=user.id;
  if(reset){sessionCursor=null;$('sessionList').replaceChildren();$('chatSessionList').replaceChildren()}
  const j=await api('/api/sessions'+(sessionCursor?'?cursor='+encodeURIComponent(sessionCursor):''));if(user?.id!==owner)return;sessionCursor=j.next_cursor;
  for(const item of j.items){$('sessionList').append(sessionEntry(item));$('chatSessionList').append(sessionEntry(item))}
  $('recentCount').textContent=$('sessionList').children.length?`${$('sessionList').children.length} 条`:'暂无';
  $('moreSessions').classList.toggle('hidden',!j.has_more);$('chatMoreSessions').classList.toggle('hidden',!j.has_more);
}
$('moreSessions').onclick=()=>loadSessions();$('chatMoreSessions').onclick=()=>loadSessions();
async function loadQuestions(reset=false){
  if(!sid)return;const current=sid;
  if(reset){questionCursor=0;$('questionNav').replaceChildren()}
  const j=await api(`/api/sessions/${current}/timeline?cursor=${questionCursor}`);
  if(current!==sid)return;
  for(const item of j.items){
    if(item.role!=='user')continue;
    const b=document.createElement('button');
    b.className='questionTick '+item.role;b.dataset.seq=String(item.seq);b.dataset.preview=item.preview;b.title=item.preview;
    b.setAttribute('aria-label',`定位${item.role==='user'?'提问':'回复'} ${item.seq}：${item.preview}`);
    b.onmouseenter=b.onfocus=()=>{
      const tip=$('questionTooltip'),rail=document.querySelector('.questionRail');
      tip.textContent=item.preview;tip.style.setProperty('--tooltip-top',`${b.getBoundingClientRect().top-rail.getBoundingClientRect().top+b.offsetHeight/2}px`);
      tip.classList.remove('hidden');
    };
    b.onmouseleave=b.onblur=()=>$('questionTooltip').classList.add('hidden');
    b.onclick=()=>jumpTo(item.seq);$('questionNav').append(b);
  }
  questionCursor=j.next_cursor||0;
  $('moreQuestions').classList.toggle('hidden',!j.has_more);
  syncRailToScroll();
}
$('moreQuestions').onclick=()=>loadQuestions();
function showEmptyChat(){document.body.classList.add('chartActive');$('birthView').classList.add('hidden');$('chartBox').classList.remove('hidden');$('chartTitle').textContent='未绑定命盘的会话';$('chartMeta').textContent='可查看历史对话';showMode('chat');window.scrollTo({top:0,behavior:'smooth'})}
async function selectSession(id,options={}){abortView();sid=id;const v=viewVersion;$('messages').replaceChildren();syncChatEmpty();$('questionNav').replaceChildren();$('chatTitle').textContent='对话';notice('');for(const b of document.querySelectorAll('.session'))b.classList.toggle('active',b.dataset.sid===id);if(!id){olderSeq=null;$('older').classList.add('hidden');persistView();return}try{let [s,m]=await Promise.all([api(`/api/sessions/${id}`),api(`/api/sessions/${id}/messages`)]);if(v!==viewVersion)return;$('chatTitle').textContent=s.title;olderSeq=m.next_before_seq;$('older').classList.toggle('hidden',!m.has_more);renderRows(m.items);await loadQuestions(true);if(s.chart_key){let c=s.input_birth?await api('/api/charts/resolve','POST',s.input_birth):await api('/api/charts/'+encodeURIComponent(s.chart_key));if(v===viewVersion){showChart({...c,name:s.chart_name});showMode(options.mode||'chat')}}else{currentChart=null;chartKey=null;showEmptyChat()}
 if(v===viewVersion){
  persistView();
  const pending=[...m.items].reverse().find(row=>row.role==='user'&&row.status==='pending'&&row.request_id);
  if(pending&&options.resume!==false&&activeMode==='chat'){
   $('ask').disabled=true;notice('正在恢复回答…');
   followEvents(id,pending.request_id,v).finally(()=>{if(sid===id&&!streamAbort)$('ask').disabled=!user});
  }
 }
 }catch(e){if(options.restore)throw e;if(v===viewVersion)notice(e.message)}}
$('newChat').onclick=async()=>{await selectSession(null);if(currentChart){showChart(currentChart);showMode('chat');notice('新会话将在首次提问时创建。')}else{$('chartNotice').textContent='请先选择生辰并起盘。';showBirth()}};
$('chatNewSession').onclick=()=>$('newChat').click();
$('older').onclick=async()=>{if(!sid||!olderSeq||loadingOlder)return;const current=sid,v=viewVersion;loadingOlder=true;try{let j=await api(`/api/sessions/${current}/messages?before_seq=${olderSeq}`);if(current!==sid||v!==viewVersion)return;olderSeq=j.next_before_seq;$('older').classList.toggle('hidden',!j.has_more);renderRows(j.items,true)}catch(e){if(current===sid)notice(e.message)}finally{loadingOlder=false}};
function syncRailToScroll(){
  const frame=$('history').getBoundingClientRect();let active=null;
  for(const message of $('messages').querySelectorAll('.bubble.user')){
    if(message.getBoundingClientRect().top<=frame.top+frame.height*.4)active=message;
  }
  if(!active)active=$('messages').querySelector('.bubble.user');
  for(const tick of $('questionNav').querySelectorAll('.questionTick'))tick.classList.toggle('active',tick.dataset.seq===active?.dataset.seq);
}
$('history').onscroll=()=>{if($('history').scrollTop<20&&olderSeq&&!loadingOlder)$('older').click();syncRailToScroll()};
async function jumpTo(seq){if(!sid)return;const current=sid,v=viewVersion;let found=$('messages').querySelector(`[data-seq="${seq}"]`);if(!found){let j=await api(`/api/sessions/${current}/messages/around?seq=${seq}`);if(current!==sid||v!==viewVersion)return;$('messages').replaceChildren();renderRows(j.items);olderSeq=j.items[0]?.seq||null;$('older').classList.toggle('hidden',!olderSeq)}found=$('messages').querySelector(`[data-seq="${seq}"]`);if(found){const area=$('history'),rect=found.getBoundingClientRect(),frame=area.getBoundingClientRect();area.scrollBy({top:rect.top-frame.top-frame.height/3,behavior:'smooth'})}found?.classList.add('focus');setTimeout(()=>found?.classList.remove('focus'),1600);for(const b of $('questionNav').querySelectorAll('.questionTick'))b.classList.toggle('active',b.dataset.seq===String(seq))}
function reasoningPanel(text='',open=true){
 const panel=document.createElement('details'),title=document.createElement('summary'),body=document.createElement('div');
 panel.className='reasoningPanel';panel.open=open;title.textContent=open?'正在思考…':'思考过程 · 已结束';body.className='reasoningText';body.textContent=text;panel.append(title,body);return panel;
}
function liveMessage(requestId){
 const div=document.createElement('div'),tag=document.createElement('span'),body=document.createElement('div'),thought=reasoningPanel();
 div.className='bubble assistant streaming';div.dataset.requestId=requestId;tag.className='bubbleRole';tag.textContent='紫微研习';body.className='bubbleBody streamingAnswer';thought.classList.add('hidden');div.append(tag,thought,body,aiDisclaimer());$('messages').append(div);syncChatEmpty();
 return {div,thought,body};
}
async function followEvents(id,requestId,v){
  const controller=new AbortController();streamAbort=controller;let after=0,live=null;
  const finishThought=()=>{if(live){live.thought.open=false;live.thought.querySelector('summary').textContent='思考过程 · 已结束'}};
  try{
    for(let retry=0;retry<4;retry++){
      try{
        const r=await fetch(`/api/sessions/${id}/events?request_id=${requestId}&after_seq=${after}`,{credentials:'same-origin',headers:authHeaders(),signal:controller.signal});
        if(!r.ok){if(r.status===401)clearAuthState();throw Error('事件连接失败：'+r.status)}
        const reader=r.body.getReader(),decoder=new TextDecoder();let buffer='';
        while(true){
          const chunk=await reader.read();if(chunk.done)break;
          buffer+=decoder.decode(chunk.value,{stream:true});const blocks=buffer.split('\n\n');buffer=blocks.pop();
          for(const block of blocks){
            const event=block.match(/^event: (.+)$/m)?.[1],raw=block.match(/^data: (.+)$/m)?.[1],eid=block.match(/^id: (\d+)$/m)?.[1];
            if(eid)after=+eid;
            if(!raw)continue;if(v!==viewVersion)return;
            const data=JSON.parse(raw);
            if(event==='reasoning_delta'||event==='answer_delta'){
              live??=liveMessage(requestId);const history=$('history'),nearBottom=history.scrollHeight-history.scrollTop-history.clientHeight<100;
              if(event==='reasoning_delta'){live.thought.classList.remove('hidden');live.thought.querySelector('.reasoningText').append(document.createTextNode(data.text));notice('正在思考…')}
              else{finishThought();live.body.append(document.createTextNode(data.text));notice('正在回答…')}
              if(nearBottom)history.scrollTop=history.scrollHeight;continue;
            }
            if(event==='reasoning_end'){finishThought();continue}
            if(event==='message_end'){
              live?.div.remove();live=null;
              renderRows([{seq:data.seq,role:'assistant',content:{text:data.answer,reasoning:data.reasoning||'',source_refs:data.source_refs||[]}}]);
              $('chatTitle').textContent=data.title||$('chatTitle').textContent;
              notice('');await Promise.all([loadSessions(true),loadQuestions(true)]);return;
            }
            if(event==='error'){finishThought();if(live)live.div.classList.add('streamFailed');notice(data.error||'回答失败，请重试');return}
            if(event==='tool_start')notice('正在读取命盘与知识资料…');
          }
        }
        if(v!==viewVersion)return;
        const status=await api(`/api/sessions/${id}/requests/${requestId}`);
        if(status.status==='complete'){live?.div.remove();await selectSession(id);return}
        if(status.status==='failed'){finishThought();notice(status.error||'回答失败，请重试');return}
      }catch(e){if(controller.signal.aborted)return;if(retry===3)notice(e.message)}
    }
  }finally{if(streamAbort===controller)streamAbort=null}
}
function newRequestId(){
  if(globalThis.crypto?.randomUUID)return crypto.randomUUID();
  if(!globalThis.crypto?.getRandomValues)throw Error('浏览器不支持安全随机数，请使用较新的浏览器');
  const bytes=crypto.getRandomValues(new Uint8Array(16));
  bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const h=Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
  return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}
$('question').addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&e.keyCode!==229){e.preventDefault();$('ask').click()}
});
$('ask').onclick=async()=>{
  const message=$('question').value.trim();
  if(!user){$('authDialog').showModal();return}
  if(!message)return;
  let id=sid;
  try{
    if(!id){
      const s=await api('/api/sessions','POST',{chart_key:chartKey,chart_name:currentChart?.name||currentChart?.input_birth?.name||null,input_birth:currentChart?.input_birth||null});id=String(s.id);
      await loadSessions(true);await selectSession(id);
    }
    const requestId=newRequestId(),v=viewVersion;
    $('ask').disabled=true;
    const result=await api(`/api/sessions/${id}/messages`,'POST',{client_request_id:requestId,message});
    $('question').value='';
    renderRows([{seq:result.user_seq,role:'user',content:{text:message}}]);
    notice('正在生成回答…');await loadQuestions(true);
    await followEvents(id,requestId,v);
  }catch(e){notice(e.message)}finally{$('ask').disabled=!user}
};
function setAuthMode(register){
  registerMode=register;
  $('authTitle').textContent=register?'创建账号':'登录后继续';
  $('authSubmit').textContent=register?'注册并登录':'登录并继续';
  $('authLoginTab').classList.toggle('active',!register);
  $('authSwitch').classList.toggle('active',register);
  for(const id of ['usernameLabel','emailLabel','confirmLabel'])$(id).classList.toggle('hidden',!register);
  $('accountLabel').classList.toggle('hidden',register);
  $('passwordHelp').classList.toggle('hidden',!register);
  $('password').placeholder=register?'至少 10 位密码':'请输入密码';
  $('authNotice').textContent='';
}
$('authButton').onclick=()=>{$('authDialog').showModal();setAuthMode(false)};
$('authClose').onclick=()=>$('authDialog').close();
$('authLoginTab').onclick=()=>setAuthMode(false);
$('authSwitch').onclick=()=>setAuthMode(true);
$('password').addEventListener('input',()=>{
  if(!registerMode)return;
  const n=$('password').value.length;
  $('passwordHelp').textContent=n>0&&n<10?`还需 ${10-n} 位，密码至少 10 位`:'密码至少 10 位，最多 128 位';
  $('passwordHelp').classList.toggle('invalid',n>0&&n<10);
});
$('authForm').onsubmit=async e=>{
  e.preventDefault();
  const username=$('username').value.trim(),email=$('email').value.trim(),password=$('password').value;
  if(registerMode){
    let error='',field=null;
    if(!/^[a-zA-Z0-9_]{3,64}$/.test(username)){error='用户名须为 3–64 位英文字母、数字或下划线';field=$('username')}
    else if(email&&(email.length>255||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))){error='请输入有效的邮箱地址';field=$('email')}
    else if(password.length<10){error='密码至少需要 10 位';field=$('password')}
    else if(password.length>128){error='密码不能超过 128 位';field=$('password')}
    else if(password!==$('confirm').value){error='两次输入的密码不一致';field=$('confirm')}
    if(error){$('authNotice').textContent=error;field.focus();return}
  }
  try{
    let account;
    if(registerMode){await api('/api/auth/register','POST',{username,email:email||null,password,confirm_password:$('confirm').value});account=username}
    else account=$('loginAccount').value.trim();
    const j=await api('/api/auth/login','POST',{account,password});
    user=j.user;setAuth();$('authDialog').close();
    $('password').value='';$('confirm').value='';await Promise.all([loadSessions(true),loadSavedCharts(true)]);
  }catch(e){$('authNotice').textContent=e.message}
};
function clearAuthState(){if(user)discardView();abortView();user=null;sid=null;currentChart=null;chartKey=null;sections={};resetLocation();$('birthName').value='';$('question').value='';$('year').value='2000';$('month').value='1';setCalendar('solar');$('day').value='1';$('hour').value='0';$('minute').value='0';$('gender').value='male';updateHourHint();setAuth();$('messages').replaceChildren();$('chatTitle').textContent='对话';showMode('analysis');showBirth()}
$('logoutButton').onclick=async()=>{try{await api('/api/auth/logout','POST');clearAuthState();notice('已退出')}catch(e){notice('退出失败，请重试：'+e.message)}};
function viewStorageKey(){return `ziwei.view.v1.${user?.id??'guest'}`}
function birthDraft(){return {location_id:$('birthLocation').value,time_fold:+$('timeFold').value,name:$('birthName').value,calendar:calendarMode,year:+$('year').value,month:+$('month').value,day:+$('day').value,leap_month:$('leapMonth').checked,clock_hour:+$('hour').value,minute:+$('minute').value,hour:clockIndex($('hour').value),gender:$('gender').value}}
function persistView(){
 if(restoringView)return;
 const state={version:1,owner:user?.id??null,page:$('birthView').classList.contains('hidden')?'chart':'birth',mode:activeMode,topic:activeTopic,
  session:sid,chart:chartKey,saved_chart_id:currentChart?.saved_chart_id||null,name:currentChart?.name||currentChart?.input_birth?.name||'',input_birth:currentChart?.input_birth||null,
  natalSchool,siHuaLayer,siHuaDaXian,natalBranch,siHuaYear:currentChart?.natal_chart?.transformations?.annual?.year,
  form:birthDraft(),draft:$('question').value,scrollY:window.scrollY,chatScroll:$('history').scrollTop};
 try{sessionStorage.setItem(viewStorageKey(),JSON.stringify(state))}catch(e){}
}
function discardView(){try{sessionStorage.removeItem(viewStorageKey())}catch(e){}}
async function restoreView(){
 let saved;
 try{const raw=sessionStorage.getItem(viewStorageKey());if(!raw||raw.length>20000)return;saved=JSON.parse(raw)}catch(e){return}
 if(!saved||typeof saved!=='object'||saved.version!==1||saved.owner!==(user?.id??null)||!['birth','chart'].includes(saved.page))return;
 if(['sanhe','feixing','sihua'].includes(saved.natalSchool))natalSchool=saved.natalSchool;
 if(['natal','daxian','annual'].includes(saved.siHuaLayer))siHuaLayer=saved.siHuaLayer;
 siHuaDaXian=Number.isInteger(saved.siHuaDaXian)&&saved.siHuaDaXian>=-1&&saved.siHuaDaXian<12?saved.siHuaDaXian:null;
 natalBranch=Number.isInteger(saved.natalBranch)&&saved.natalBranch>=0&&saved.natalBranch<12?saved.natalBranch:null;
 if(saved.form)await fillBirth(saved.form);
 if(saved.page==='chart'){
  if(saved.session&&user){await selectSession(saved.session,{mode:saved.mode==='analysis'?'analysis':'chat',resume:saved.mode==='chat',restore:true})}
  else if(saved.chart){const chart=saved.input_birth?await api('/api/charts/resolve','POST',saved.input_birth):await api('/api/charts/'+encodeURIComponent(saved.chart));showChart({...chart,name:saved.name,input_birth:saved.input_birth,saved_chart_id:saved.saved_chart_id})}
  else{showBirth();return}
  if(saved.topic&&Object.hasOwn(sections,saved.topic)&&saved.mode!=='chat')renderReport(saved.topic);
  else if(saved.mode==='chat')showMode('chat');
 }
 if(currentChart&&Number.isInteger(saved.siHuaYear)&&saved.siHuaYear>=1800&&saved.siHuaYear<=2200&&saved.siHuaYear!==currentChart.natal_chart?.transformations?.annual?.year)await loadTransformationYear(saved.siHuaYear);
 $('question').value=typeof saved.draft==='string'?saved.draft.slice(0,4000):'';
 requestAnimationFrame(()=>{
  window.scrollTo({top:Number(saved.scrollY)||0,behavior:'instant'});
  if(activeMode==='chat')$('history').scrollTop=Number(saved.chatScroll)||0;
 });
}
window.addEventListener('pagehide',persistView);
async function restoreAuth(){
 $('authButton').disabled=true;
 try{
  try{
   user=await api('/api/auth/me');setAuth();
   await Promise.all([loadSessions(true),loadSavedCharts(true)]);
  }catch(e){
   if(e.status===401){clearAuthState()}
   else{throw e}
  }
  await restoreView();
 }catch(e){
  if(e.status===404||e.status===403){discardView();sid=null;currentChart=null;chartKey=null;sections={};showBirth();$('chartNotice').textContent='原命盘或会话已不可用，请重新选择。'}
  else{$('chartNotice').textContent='暂时无法恢复页面，请稍后刷新重试。'}
 }finally{restoringView=false;$('authButton').disabled=false}
}
setAuth();
restoreAuth();

let actionQueue=Promise.resolve();
function actionDialog(options){const pending=actionQueue.then(()=>openActionDialog(options));actionQueue=pending.catch(()=>null);return pending}
function openActionDialog(options){return new Promise(resolve=>{
 const dialog=$('actionDialog'),input=$('actionInput'),form=$('actionForm'),editable=typeof options.value==='string';
 $('actionTitle').textContent=options.title;$('actionMessage').textContent=options.message||'';$('actionError').textContent='';
 $('actionField').classList.toggle('hidden',!editable);$('actionLabel').textContent=options.label||'会话标题';input.maxLength=options.maxLength||160;input.value=editable?options.value:'';
 $('actionConfirm').textContent=options.confirm||'确认';$('actionConfirm').classList.toggle('danger',!!options.danger);
 let finished=false;
 const done=value=>{if(finished)return;finished=true;dialog.close();input.value='';resolve(value)};
 form.onsubmit=e=>{e.preventDefault();const value=input.value.trim();if(editable&&(!value||value.length>input.maxLength)){$('actionError').textContent=!value?`请输入${options.label||'会话标题'}`:`最多输入 ${input.maxLength} 个字符`;input.focus();return}done(editable?value:true)};
 $('actionCancel').onclick=()=>done(null);dialog.oncancel=e=>{e.preventDefault();done(null)};dialog.onclose=()=>done(null);
 dialog.onclick=e=>{const r=dialog.getBoundingClientRect();if(e.target===dialog&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom))done(null)};
 dialog.showModal();if(editable){input.focus();input.select()}else $('actionCancel').focus();
})}
if(globalThis.ResizeObserver)new ResizeObserver(entries=>document.documentElement.style.setProperty('--nav-height',entries[0].target.offsetHeight+'px')).observe(document.querySelector('.siteHeader'));

function renderNatal(j){
 const chart=j.natal_chart;
 if(!chart){$('natalPanel').classList.add('hidden');return}
 $('natalPanel').classList.remove('hidden');
 $('natalMeta').textContent=chart.lunar_date+' · '+chart.five_elements_class;
 $('solarCorrection').textContent=j.time_correction?'已按出生地校正真太阳时':'按已保存的日期与时辰起盘';
 document.querySelector('.natalLiveBadge').textContent=j.time_correction?'真太阳时':'本命盘';
 if(currentChart&&currentChart.chart_key!==j.chart_key){natalBranch=null;siHuaDaXian=null;++transformationRequest}
 const transforms=chart.transformations;
 if(siHuaDaXian===null)siHuaDaXian=chart.currentDaXianIndex;
 for(const button of document.querySelectorAll('[data-chart-school]'))button.setAttribute('aria-pressed',String(button.dataset.chartSchool===natalSchool));
 $('siHuaControls').classList.toggle('hidden',natalSchool!=='sihua');$('siHuaLayer').value=siHuaLayer;
 $('daXianField').classList.toggle('hidden',siHuaLayer!=='daxian');$('annualField').classList.toggle('hidden',siHuaLayer!=='annual');
 const decadeSelect=$('siHuaDaXian');decadeSelect.replaceChildren();
 if(siHuaDaXian===-1){const option=new Option('尚未进入大限','-1');option.disabled=true;decadeSelect.add(option)}
 for(const decade of transforms?.daXians||[])decadeSelect.add(new Option(`${decade.startAge}–${decade.endAge}岁 · ${decade.palaceName}`,String(decade.index)));
 decadeSelect.value=String(siHuaDaXian);$('siHuaYear').value=String(transforms?.annual?.year||new Date().getFullYear());
 $('chartSchoolHint').textContent=natalSchool==='sanhe'?'':natalSchool==='feixing'?'':'';
 PalaceBoard.render($('natalBoard'),j,palace=>{
  if(activeMode!=='analysis'||natalSchool!=='sanhe')return;
  const topics={'命宫':'overview','财帛':'wealth','官禄':'career','夫妻':'love','疾厄':'health','兄弟':'family','子女':'children','迁移':'move','仆役':'friends','田宅':'home','福德':'spirit','父母':'parents'};
  if(topics[palace.name])renderReport(topics[palace.name]);
 },{mode:natalSchool,layer:siHuaLayer,daXianIndex:siHuaDaXian,selectedBranch:natalBranch,onSelection:branch=>{natalBranch=branch;persistView()}});
}

for(const button of document.querySelectorAll('[data-chart-school]'))button.onclick=()=>{
 if(!currentChart)return;natalSchool=button.dataset.chartSchool;natalBranch=null;$('chartSchoolStatus').textContent='';renderNatal(currentChart);persistView();
};
$('siHuaLayer').onchange=()=>{siHuaLayer=$('siHuaLayer').value;natalBranch=null;renderNatal(currentChart);persistView()};
$('siHuaDaXian').onchange=()=>{siHuaDaXian=Number($('siHuaDaXian').value);natalBranch=null;renderNatal(currentChart);persistView()};
async function loadTransformationYear(year){
 if(!currentChart)return;
 if(!Number.isInteger(year)||year<1800||year>2200){$('chartSchoolStatus').textContent='请输入 1800–2200 之间的流年年份。';return}
 const key=currentChart.chart_key,request=++transformationRequest;$('chartSchoolStatus').textContent='正在计算流年四化…';
 try{const result=await api(`/api/charts/${encodeURIComponent(key)}/transformations?year=${year}`);if(request!==transformationRequest||currentChart?.chart_key!==key)return;
  currentChart.natal_chart.transformations=result;$('chartSchoolStatus').textContent='';renderNatal(currentChart);persistView();
 }catch(e){if(request===transformationRequest){$('chartSchoolStatus').textContent=e.message;$('siHuaYear').value=String(currentChart?.natal_chart?.transformations?.annual?.year||'')}}
}
$('siHuaYear').onchange=()=>loadTransformationYear(Number($('siHuaYear').value));


let locationRequest=0,locationTimer,pickerProvince='',pickerCity='',pickerProvinces=[];
function setPickerOpen(open){
 $('locationPopover').classList.toggle('hidden',!open);$('locationTrigger').setAttribute('aria-expanded',String(open));
 if(open){const r=$('locationTrigger').getBoundingClientRect();$('locationPicker').classList.toggle('opensUp',window.innerHeight-r.bottom<440&&r.top>440);loadLocations();setTimeout(()=>$('locationSearch').focus(),0)}
 else{++locationRequest;clearTimeout(locationTimer)}
}
function resetLocation(){
 ++locationRequest;pickerProvince='';pickerCity='';$('birthRegion').value='domestic';$('birthLocation').value='';$('selectedLocationText').textContent='选择出生地';$('locationTrigger').classList.remove('hasLocation');$('locationSearch').value='';$('timeFold').value='0';$('locationHint').textContent='请选择出生区县，中国大陆按北京时间填写。';setPickerOpen(false);
}
function selectLocation(c){
 ++locationRequest;$('birthLocation').value=c.id;$('birthRegion').value='domestic';pickerProvince=c.province_id||'';pickerCity=c.city_id||'';$('locationSearch').value='';
 $('selectedLocationText').textContent=c.full_name||c.display_name||c.name;$('locationTrigger').classList.add('hasLocation');
 $('locationHint').textContent=`${c.timezone} · 参考经度 ${Number(c.longitude).toFixed(4)}° · 按出生日期校正真太阳时`;
 setPickerOpen(false);$('locationTrigger').focus();persistView();
}
function locationEmpty(target,text){const p=document.createElement('p');p.className='locationEmpty';p.textContent=text;target.replaceChildren(p)}
function districtButton(c,searchResult=false){
 const b=document.createElement('button');b.type='button';b.className='locationDistrict'+(searchResult?' locationSearchResult':'');b.dataset.locationId=c.id;
 b.textContent=c.whole_city?'全市（不设区县）':c.display_name;
 if(searchResult){const sub=document.createElement('small');sub.textContent=c.full_name;b.append(sub)}
 b.classList.toggle('selected',c.id===$('birthLocation').value);b.setAttribute('aria-pressed',String(c.id===$('birthLocation').value));b.title=c.full_name;b.onclick=()=>selectLocation(c);return b;
}
function renderLocationOptions(target,items,selected,kind,choose){
 target.replaceChildren();
 for(const item of items){
  const b=document.createElement('button');b.type='button';b.className=kind;b.textContent=item.label;b.dataset.locationId=item.id;b.classList.toggle('selected',item.id===selected);b.setAttribute('aria-pressed',String(item.id===selected));b.onclick=()=>choose(item.id);target.append(b);
 }
}
function renderLocationProvinces(){renderLocationOptions($('locationGroups'),pickerProvinces,pickerProvince,'locationProvince',id=>{pickerProvince=id;pickerCity='';$('locationSearch').value='';loadLocations()})}
async function loadLocations(){
 const v=++locationRequest,q=$('locationSearch').value.trim();clearTimeout(locationTimer);
 $('locationColumns').classList.toggle('hidden',!!q);$('locationResults').classList.toggle('hidden',!q);$('locationSearchClear').classList.toggle('hidden',!q);
 renderLocationProvinces();$('locationCities').replaceChildren();$('locationDistricts').replaceChildren();$('locationResults').replaceChildren();$('locationStatus').textContent=q?'正在搜索区县…':'正在加载省市区县…';
 try{
  const data=await api('/api/location-picker?'+new URLSearchParams({province:pickerProvince,city:pickerCity,q}));if(v!==locationRequest)return;
  pickerProvinces=data.provinces;pickerCity=data.city_id;renderLocationProvinces();
  renderLocationOptions($('locationCities'),data.cities,pickerCity,'locationCity',id=>{pickerCity=id;loadLocations()});
  if(!pickerProvince)locationEmpty($('locationCities'),'请先选择省级地区');
  if(!pickerCity)locationEmpty($('locationDistricts'),'请选择城市');
  else $('locationDistricts').replaceChildren(...data.districts.map(c=>districtButton(c)));
  if(q){
   if(data.results.length)$('locationResults').replaceChildren(...data.results.map(c=>districtButton(c,true)));
   else locationEmpty($('locationResults'),'没有找到区县，请尝试完整名称或按省市逐级选择。');
   $('locationStatus').textContent=`找到 ${data.results.length} 个结果，请按完整归属选择。`;
  }else $('locationStatus').textContent=pickerCity?`本市共 ${data.districts.length} 个区县选项，请选择出生区县。`:`已收录 ${data.counts.province} 个省级地区，请依次选择城市和区县。`;
 }catch(e){if(v===locationRequest)$('locationStatus').textContent=e.message}
}
$('locationTrigger').onclick=()=>setPickerOpen($('locationPopover').classList.contains('hidden'));
$('locationSearch').oninput=()=>{clearTimeout(locationTimer);++locationRequest;const q=$('locationSearch').value.trim();$('locationColumns').classList.toggle('hidden',!!q);$('locationResults').classList.toggle('hidden',!q);$('locationSearchClear').classList.toggle('hidden',!q);$('locationResults').replaceChildren();$('locationCities').replaceChildren();$('locationDistricts').replaceChildren();$('locationStatus').textContent='正在搜索区县…';locationTimer=setTimeout(loadLocations,220)};
$('locationSearchClear').onclick=()=>{$('locationSearch').value='';loadLocations();$('locationSearch').focus()};
document.addEventListener('click',e=>{if(!e.composedPath().includes($('locationPicker')))setPickerOpen(false)});
$('locationPicker').addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();setPickerOpen(false);$('locationTrigger').focus()}});
async function restoreLocation(input){
 const request=++locationRequest;$('timeFold').value=String(input.time_fold||0);
 if(!input.location_id){resetLocation();return}
 try{const c=await api('/api/locations/'+encodeURIComponent(input.location_id));if(request!==locationRequest)return;selectLocation(c);$('timeFold').value=String(input.time_fold||0)}catch(e){$('locationHint').textContent=e.message}
}
