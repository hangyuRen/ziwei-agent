// DOM regression checks; run with JSDOM_PATH pointing to an installed jsdom.
const {JSDOM}=require(process.env.JSDOM_PATH||'jsdom');
const fs=require('node:fs');const assert=require('node:assert/strict');
const html=fs.readFileSync('static/index.html','utf8'),script=fs.readFileSync('static/app.js','utf8');
const key='2000-01-01-0-male',sid='00000000-0000-4000-8000-000000000001';
const names=['overview','personality','love','career','wealth','health','family','children','move','friends','home','spirit','parents'];
const chart={chart_key:key,birth:{year:2000,month:1,day:1,hour:0,gender:'male'},sections:Object.fromEntries(names.map(k=>[k,'测试原文：'+k]))};
const form={name:'小林',calendar:'solar',year:2000,month:1,day:1,hour:0,clock_hour:0,minute:0,gender:'male',leap_month:false};
const saved=(changes={})=>({version:1,owner:1,page:'chart',mode:'analysis',topic:'career',session:null,chart:key,name:'小林',input_birth:form,form,draft:'',scrollY:0,chatScroll:0,...changes});
const settle=async()=>{for(let i=0;i<12;i++)await new Promise(resolve=>setImmediate(resolve))};
async function open(state,options={}){
 const dom=new JSDOM(html,{url:'http://ziwei.test/',runScripts:'outside-only',pretendToBeVisual:true});const w=dom.window,requests=[];
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'))};
 w.prompt=w.confirm=()=>{throw Error('Native dialog used')};
 w.scrollTo=()=>{};w.HTMLElement.prototype.scrollIntoView=()=>{};w.HTMLElement.prototype.scrollBy=()=>{};
 if(state)w.sessionStorage.setItem(`ziwei.view.v1.${state.owner??'guest'}`,JSON.stringify(state));
 w.fetch=async(path,init={})=>{
  requests.push({path,method:init.method||'GET'});let data,status=200;
  if(path==='/api/auth/me'){status=options.guest?401:200;data=options.guest?{detail:'请先登录'}:{id:options.owner||1,username:'测试用户'}}
  else if(path==='/api/auth/logout')data={ok:true};
  else if(path.startsWith('/api/calendar/lunar-years/'))data={year:+path.split('/').at(-1),leap_month:null,months:Object.fromEntries(Array.from({length:12},(_,i)=>[i+1,30]))};
  else if(path==='/api/sessions')data={items:[{id:sid,title:'事业对话',chart_key:key,last_interaction_at:'2026-11-08T00:00:00Z'}],has_more:false};
  else if(path.startsWith('/api/saved-charts?'))data={items:[],total:0,has_more:false};
  else if(path===`/api/sessions/${sid}`){status=options.deleted?404:200;data=options.deleted?{detail:'会话不存在'}:{id:sid,title:'事业对话',chart_key:key,chart_name:'小林'}}
  else if(path===`/api/sessions/${sid}/messages`)data={items:[{seq:1,role:'user',status:options.pending?'pending':'complete',request_id:'request',content:{text:'我的事业如何？'}},...(options.pending?[]:[{seq:2,role:'assistant',content:{text:'测试回答'}}])],has_more:false};
  else if(path.startsWith(`/api/sessions/${sid}/timeline`))data={items:[{role:'user',seq:1,preview:'我的事业如何？'}],has_more:false};
  else if(path.startsWith('/api/charts/'))data=chart;
  else if(path.includes('/events?')){
   const event=`id: 3\nevent: answer_delta\ndata: {"text":"继续回答"}\n\nid: 4\nevent: message_end\ndata: {"seq":4,"answer":"继续回答","title":"事业对话"}\n\n`;
   return {ok:true,body:new ReadableStream({start(controller){controller.enqueue(new TextEncoder().encode(event));controller.close()}})};
  }else throw Error('Unexpected request '+path);
  return {ok:status<400,status,json:async()=>data};
 };
 w.TextDecoder=TextDecoder;w.eval(script);await settle();return {dom,w,requests};
}
(async()=>{
 let t=await open(saved());
 assert(t.w.document.querySelector('#birthView').classList.contains('hidden'));
 assert.equal(t.w.document.querySelector('#insightTitle').textContent,'事业');
 assert.equal(t.w.document.querySelector('#chartTitle').textContent,'小林');
 t.w.document.querySelector('#tabs [data-section="wealth"]').click();
 t.w.dispatchEvent(new t.w.Event('pagehide'));
 const refresh=JSON.parse(t.w.sessionStorage.getItem('ziwei.view.v1.1'));t.dom.window.close();
 t=await open(refresh);assert.equal(t.w.document.querySelector('#insightTitle').textContent,'财运');t.dom.window.close();
 t=await open(saved({session:sid,mode:'chat',draft:'还没发送的问题'}));
 assert(!t.w.document.querySelector('#chatPanel').classList.contains('hidden'));
 assert.equal(t.w.document.querySelector('#chatTitle').textContent,'事业对话');
 assert.equal(t.w.document.querySelector('#question').value,'还没发送的问题');
 assert.equal(t.w.document.querySelectorAll('#messages .bubble').length,2);
 assert.equal(t.requests.filter(r=>r.method==='POST').length,0);t.dom.window.close();
 t=await open(saved({session:sid,mode:'analysis',topic:'wealth'}));
 assert(!t.w.document.querySelector('#analysisPanel').classList.contains('hidden'));
 assert.equal(t.w.document.querySelector('#insightTitle').textContent,'财运');t.dom.window.close();
 t=await open(saved({page:'birth',form:{...form,calendar:'lunar',year:2001,month:12,day:8,clock_hour:19,minute:5}}));
 assert(!t.w.document.querySelector('#birthView').classList.contains('hidden'));
 assert.equal(t.w.document.querySelector('#month').selectedOptions[0].textContent,'腊月');
 assert.equal(t.w.document.querySelector('#day').selectedOptions[0].textContent,'初八');
 assert(t.w.document.querySelector('#hourHint').textContent.includes('19:05'));t.dom.window.close();
 t=await open(saved({owner:null}),{guest:true});
 assert(t.w.document.querySelector('#birthView').classList.contains('hidden'));
 assert.equal(t.w.document.querySelector('#chartTitle').textContent,'小林');t.dom.window.close();
 t=await open(saved(),{owner:2});assert(!t.w.document.querySelector('#birthView').classList.contains('hidden'));t.dom.window.close();
 t=await open(saved({session:sid,mode:'chat'}),{deleted:true});assert(!t.w.document.querySelector('#birthView').classList.contains('hidden'));t.dom.window.close();
 t=await open(saved({session:sid,mode:'chat'}),{pending:true});
 assert(t.w.document.querySelector('#messages').textContent.includes('继续回答'));
 assert.equal(t.requests.filter(r=>r.path.includes('/events?')).length,1);
 assert.equal(t.requests.filter(r=>r.method==='POST').length,0);t.dom.window.close();
 t=await open(saved());t.w.document.querySelector('#logoutButton').click();await settle();assert.equal(t.w.sessionStorage.getItem('ziwei.view.v1.1'),null);assert.equal(t.w.document.querySelector('#birthName').value,'');t.dom.window.close();
 t=await open(saved());
 assert(t.w.document.querySelector('.siteHeader #chartMenu'));
 assert.equal(t.w.document.querySelector('.brandLogo').getAttribute('src'),'/static/logo.png');
 assert.equal(t.w.document.querySelectorAll('.chatHeading p,.chatHeading .eyebrow').length,0);
 let answer=t.w.actionDialog({title:'重命名对话',value:'旧标题',confirm:'保存'});await settle();
 const input=t.w.document.querySelector('#actionInput');assert.equal(input.value,'旧标题');
 input.value='  ';t.w.document.querySelector('#actionForm').dispatchEvent(new t.w.Event('submit',{cancelable:true}));
 assert(t.w.document.querySelector('#actionError').textContent);assert(t.w.document.querySelector('#actionDialog').open);
 input.value=' 新标题 ';t.w.document.querySelector('#actionForm').dispatchEvent(new t.w.Event('submit',{cancelable:true}));assert.equal(await answer,'新标题');
 answer=t.w.actionDialog({title:'删除对话',danger:true});await settle();
 assert(t.w.document.querySelector('#actionConfirm').classList.contains('danger'));
 t.w.document.querySelector('#actionDialog').dispatchEvent(new t.w.Event('cancel',{cancelable:true}));assert.equal(await answer,null);
 t.dom.window.close();
 console.log('PASS: refresh round trip, analysis topic, chat session, draft, lunar form, guest, account isolation, deleted session, pending SSE without duplicate POST');
})().catch(e=>{console.error(e);process.exitCode=1});
