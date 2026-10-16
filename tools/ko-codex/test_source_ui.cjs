const fs=require('fs'),path=require('path'),assert=require('assert');
const {JSDOM}=require('jsdom');const root=path.resolve(__dirname,'../..');
const tick=()=>new Promise(r=>setTimeout(r,20));
async function run(role='admin'){
 const dom=new JSDOM(fs.readFileSync(path.join(root,'source-library.html'),'utf8'),{url:'https://preview.example/source-library.html',runScripts:'outside-only'}),w=dom.window;
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};
 w.localStorage.setItem('savedUserId','admin');w.confirm=()=>true;
 const book={version:1,title:'테스트 교재',subject:'수학',grade:'중3',edition:'2026',sources:[{id:'source',name:'test.pdf',path:'test.pdf',kind:'questions'}],items:[{id:'existing',source_id:'source',number:'1',unit:'단원',statement:'관리자가 수정한 원문',answer:'1',solution:'',status:'ready',regions:[{page:1,box:[0,0,1,1]}],figure_images:[]}],candidates:[{id:'candidate',source_id:'source',kind:'questions',number:'2',unit:'단원',statement:'추출 원문',answer:'2',solution:'',regions:[{page:2,box:[0,0,1,1]}],figure_images:[]}],runs:[],applied_jobs:[]};
 let current={id:'book',title:book.title,source_type:'원본교재',file_path:'revision-original'}, saves=[],conflict=false;
 const bucket={createSignedUrl:async p=>({data:{signedUrl:'https://storage.example/'+p}}),upload:async(p,blob)=>{saves.push({p,blob});return {}}};
 w.db={storage:{from:()=>bucket},from(table){let payload=null,filters=[];const q={select(){return q},eq(k,v){filters.push([k,v]);return q},is(){return q},order(){return q},limit(){return q},update(p){payload=p;return q},single(){if(table==='users')return Promise.resolve({data:{id:'admin',name:'관리자',role,status:'active'}});return Promise.resolve({data:current})},then(resolve,reject){if(payload){assert(filters.some(([k,v])=>k==='file_path'&&v===current.file_path),'conditional revision check required');if(conflict)return Promise.resolve({data:[]}).then(resolve,reject);current={...current,...payload};return Promise.resolve({data:[{id:'book'}]}).then(resolve,reject)}return Promise.resolve({data:[current]}).then(resolve,reject)}};return q}};
 w.fetch=async url=>{assert(url.startsWith('https://storage.example/'));return {ok:true,json:async()=>JSON.parse(JSON.stringify(book))}};
 w.SourceWorker={call:async()=>{throw Error('No AI calls in review test')},supports(){}};
 w.eval(fs.readFileSync(path.join(root,'assets/source-library.js'),'utf8'));await tick();
 if(role!=='admin'){assert(w.document.getElementById('gate').textContent.includes('관리자'));assert(w.document.getElementById('app').hidden);dom.window.close();return}
 w.document.querySelector('[data-id="book"]').click();await tick();
 assert(w.document.getElementById('items').textContent.includes('관리자가 수정한 원문'));
 w.document.querySelector('[data-accept="candidate"]').click();await tick();
 assert(w.document.getElementById('items').textContent.includes('관리자가 수정한 원문'),'existing edit retained');
 assert(w.document.getElementById('items').textContent.includes('추출 원문'),'candidate added separately');
 w.document.querySelector('[data-edit="candidate"]').click();await tick();
 assert.equal(w.document.getElementById('q-status').value,'review');
 w.document.getElementById('q-status').value='ready';
 const submit=w.document.querySelector('#edit-form button[type=submit]')||w.document.querySelector('#edit-form .primary');
 w.document.getElementById('edit-form').dispatchEvent(new w.SubmitEvent('submit',{bubbles:true,cancelable:true,submitter:submit}));await tick();
 assert(w.document.getElementById('edit-status').textContent.includes('원본 대조'));
 w.document.getElementById('q-confirm').checked=true;conflict=true;
 w.document.getElementById('edit-form').dispatchEvent(new w.SubmitEvent('submit',{bubbles:true,cancelable:true,submitter:submit}));await tick();
 assert(w.document.getElementById('edit-status').textContent.includes('다른 화면'));
 assert(w.document.getElementById('editor').open,'unsaved editor preserved on conflict');
 assert(new Set(saves.map(s=>s.p)).size===saves.length,'immutable revisions');
 dom.window.close();
}
(async()=>{await run();await run('teacher');console.log('PASS source UI: admin gate, original edits retained, candidate review, approval gate, immutable revisions, stale-write conflict');})().catch(e=>{console.error(e);process.exit(1)});
