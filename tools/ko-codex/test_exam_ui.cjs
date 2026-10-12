const {JSDOM}=require('jsdom'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.join(__dirname,'../..'),read=f=>fs.readFileSync(path.join(root,f),'utf8'),pause=()=>new Promise(r=>setTimeout(r,10));
(async()=>{
 const core=require('../../assets/ko-exam-core.js');
 assert.throws(()=>core.validate([{no:1,answer:'',points:2}]));
 assert.throws(()=>core.selectSets({codexReview:[],sets:[{area:'독서',qs:[{no:1},{no:1}]}]},'공통'));
 const eid='00000000-0000-4000-8000-000000000010',image='ko-published/'+eid+'/0.png';
 let calls=[],saved={};const now=new Date(),deadline=new Date(+now+4800000);
 const dom=new JSDOM(read('korean-exam.html'),{url:'https://bmaps.example/korean-exam.html',runScripts:'outside-only'}),w=dom.window;
 w.confirm=()=>true;w.sessionStorage.setItem('ko-student-token','test-session');
 w.supabase={createClient:()=>({rpc:async(name,p)=>{calls.push(p);let data;
  if(p.p_action==='list')data=[{id:eid,title:'테스트 국어',elective:'공통',duration:80}];
  if(p.p_action==='start')data={id:eid,title:'테스트 국어',server_now:now.toISOString(),deadline:deadline.toISOString(),answers:saved,sets:[{passage:[image],questions:[{no:1,points:2,images:[image]},{no:2,points:3,images:[image]}]}]};
  if(p.p_action==='save'){saved=p.p_data.answers;data={ok:true};}
  if(p.p_action==='submit')data={submitted:true,result:{score:5,total:5,correct_count:2,items:[{no:1,answer:'4',response:'4',correct:true,points:2},{no:2,answer:'2',response:'2',correct:true,points:3}]}};
  return {data};}})};
 w.eval(read('assets/ko-student.js'));await pause();await w.document.querySelector('#exams button').onclick();
 assert.equal(w.document.getElementById('exam').hidden,false);
 assert.equal(w.document.querySelectorAll('#passage img').length,1);
 assert.ok(!w.document.getElementById('question').textContent.includes('정답'));
 w.document.querySelectorAll('#choices button')[3].click();await pause();
 w.document.getElementById('next').click();w.document.querySelectorAll('#choices button')[1].click();await pause();
 assert.equal(saved['1'],'4');assert.equal(saved['2'],'2');
 await w.document.getElementById('submit').onclick();assert.match(w.document.getElementById('result').textContent,/5 \/ 5점/);
 assert.equal(calls.filter(c=>c.p_action==='submit').length,1);dom.window.close();
 // Administrator uses the current Codex draft and keeps the two elective answer keys separate.
 const admin=new JSDOM('<div id="ko-result"></div>',{url:'https://bmaps.example/bety-admin.html',runScripts:'outside-only'}),a=admin.window;
 a._ko={file:{name:'test.pdf'}};a.db={rpc:async()=>({data:[]})};a.KoExamCore=core;
 a.koGetDraft=()=>({codexReview:[],sets:[{range:'1',area:'독서',sourceRegions:[],qs:[{no:1,pts:2}]},{range:'35',area:'화법과 작문',sourceRegions:[],qs:[{no:35,pts:2}]},{range:'35',area:'언어와 매체',sourceRegions:[],qs:[{no:35,pts:3}]}]});
 a.eval(read('assets/ko-publish.js'));await a.document.getElementById('kp-prepare').onclick();
 assert.equal(a.document.querySelectorAll('#kp-grid tbody tr').length,2);
 a.document.getElementById('kp-elective').value='언어와 매체';await a.document.getElementById('kp-prepare').onclick();
 assert.equal(a.document.querySelectorAll('#kp-grid input[data-field="points"]')[1].value,'3');
 admin.window.close();console.log('PASS UI: answer validation, elective separation, passage display, navigation, save, submit, result');
})().catch(e=>{console.error(e);process.exitCode=1});
