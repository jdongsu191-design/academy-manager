const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const elements = new Map();
const element = id => { if (!elements.has(id)) elements.set(id, {value:'',textContent:''}); return elements.get(id); };
const listeners = {};
let opens = 0, lastMessage = '', ticks = [];
const popup = {closed:false,focus(){},postMessage(m){this.last=m;}};
let requests=[];
const context = {fetch:async(url,opts)=>{requests.push({url,opts});return {ok:true,json:async()=>({ok:true})}},Map,Error,TypeError,Promise,AbortController,crypto:require('node:crypto').webcrypto,
 document:{getElementById:element,querySelectorAll:()=>[]},location:{origin:'https://test.example'},
 _ko:{busy:false},koRender(){},koReset(){},koSetFile(){},koScope(){},koMsg(m){lastMessage=m;},
 setInterval(fn){ticks.push(fn);return ticks.length;},clearInterval(){},setTimeout(){return 1;},clearTimeout(){},
 addEventListener(type,fn){listeners[type]=fn;},open(){opens++;return popup;}};
(async()=>{
context.window=context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../assets/ko-codex.js'),'utf8'),context);
await context.koCodexRun(false);
assert.equal(opens,0,'analysis must not create approval windows');
context.koCodexConnect();
assert.equal(opens,1);
context.koCodexConnect();
assert.equal(opens,1,'pending popup must not reload');
await listeners.message({origin:'https://evil.example',source:popup,data:{type:'bmaps-ready',token:'a'.repeat(43)}});
assert.equal(element('ko-codex-status').textContent,'승인 대기 중');
await listeners.message({origin:'http://127.0.0.1:8765',source:popup,data:{type:'bmaps-ready',token:'a'.repeat(43)}});
assert.equal(element('ko-codex-status').textContent,'Codex 연결됨 · 창 닫기 가능');
assert.equal(popup.last.type,'bmaps-ack');
await context.koCodexCheck();
assert.equal(opens,1,'approved popup must stay approved');
popup.closed=true;
await listeners.message({origin:'http://127.0.0.1:8765',source:popup,data:{type:'bmaps-window-closed'}});
for(const tick of ticks.slice(0,1)) tick();
await context.koCodexCheck();
assert.equal(element('ko-codex-status').textContent,'Codex 연결됨 · 창 닫기 가능');
assert.ok(requests.length>=3,'health requests must reach worker after popup closes');
assert.equal(requests.at(-1).opts.headers.Authorization,'Bearer '+'a'.repeat(43));
await context.koCodexRun(false);
assert.equal(opens,1);
assert.match(lastMessage,/PDF/);
// A single analysis sends both files and only applies answers after the exam completes.
const order=[];
context.sessionStorage={getItem:()=>null,setItem(){},removeItem(){}};
context._ko.file={name:'exam.pdf',size:12};context.koAnswerFile={name:'answers.pdf',size:10};
context.koInvalidateAnswers=()=>order.push('invalidate');
context.koAcceptAnswers=r=>{assert.equal(r.rows[0].answer,4);order.push('answers');};
context.koPrepareExam=()=>order.push('prepare');
context.fetch=async(url)=>({ok:true,json:async()=>{
 if(url.endsWith('/answers')){order.push('read');return {rows:[{no:1,answer:4}]};}
 if(url.includes('/jobs?')){order.push('job');return {id:'job1'};}
 if(url.endsWith('/jobs/job1'))return {status:'complete',result:{sets:[],codexReview:[]}};
 return {ok:true};
}});
await context.koCodexRun(false);
assert.deepEqual(order,['invalidate','read','job','answers','prepare']);
assert.equal(context._ko.busy,false);
order.length=0;
context.fetch=async(url)=>({ok:true,json:async()=>{if(url.endsWith('/answers'))throw Error('bad answer PDF');return {ok:true};}});
await context.koCodexRun(false);
assert.deepEqual(order,['invalidate'],'failed answer parsing must not publish stale answers or start a problem job');
assert.equal(context._ko.busy,false);
await listeners.message({origin:'http://127.0.0.1:8765',source:popup,data:{type:'bmaps-disconnected'}});
assert.equal(element('ko-codex-status').textContent,'연결 안 됨');
assert.match(lastMessage,/해제/);
await context.koCodexRun(false);
assert.equal(opens,1,'disconnected analysis must not open more popups');
console.log('PASS: repeated connect, analysis, origin validation, acknowledgement, disconnect');

})().catch(e=>{console.error(e);process.exitCode=1});
