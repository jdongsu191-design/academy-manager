const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const elements = new Map();
const element = id => { if (!elements.has(id)) elements.set(id, {value:'',textContent:''}); return elements.get(id); };
const listeners = {};
let opens = 0, lastMessage = '', ticks = [];
const popup = {closed:false,focus(){},postMessage(m){this.last=m;}};
const context = {Map,Error,TypeError,Promise,AbortController,crypto:require('node:crypto').webcrypto,
 document:{getElementById:element},location:{origin:'https://test.example'},
 _ko:{busy:false},koRender(){},koReset(){},koSetFile(){},koScope(){},koMsg(m){lastMessage=m;},
 setInterval(fn){ticks.push(fn);return ticks.length;},clearInterval(){},setTimeout(){return 1;},clearTimeout(){},
 addEventListener(type,fn){listeners[type]=fn;},open(){opens++;return popup;}};
context.window=context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../assets/ko-codex.js'),'utf8'),context);
context.koCodexRun(false);
assert.equal(opens,0,'analysis must not create approval windows');
context.koCodexConnect();
assert.equal(opens,1);
context.koCodexConnect();
assert.equal(opens,1,'pending popup must not reload');
listeners.message({origin:'https://evil.example',source:popup,data:{type:'bmaps-ready'}});
assert.equal(element('ko-codex-status').textContent,'승인 대기 중');
listeners.message({origin:'http://127.0.0.1:8765',source:popup,data:{type:'bmaps-ready'}});
assert.equal(element('ko-codex-status').textContent,'Codex 연결됨');
assert.equal(popup.last.type,'bmaps-ack');
context.koCodexConnect();
assert.equal(opens,1,'approved popup must stay approved');
context.koCodexRun(false);
assert.equal(opens,1);
assert.match(lastMessage,/PDF/);
listeners.message({origin:'http://127.0.0.1:8765',source:popup,data:{type:'bmaps-disconnected'}});
assert.equal(element('ko-codex-status').textContent,'연결 안 됨');
assert.match(lastMessage,/해제/);
context.koCodexRun(false);
assert.equal(opens,1,'disconnected analysis must not open more popups');
console.log('PASS: repeated connect, analysis, origin validation, acknowledgement, disconnect');
