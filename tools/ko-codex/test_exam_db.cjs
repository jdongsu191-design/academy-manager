// Run with NODE_PATH pointing to a local @electric-sql/pglite install. No network/database writes.
const {PGlite}=require('@electric-sql/pglite'),fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const db=new PGlite();
 await db.exec("create role anon;create role authenticated;create table users(id uuid primary key,username text,password text,name text,role text,status text,school text,grade text);");
 const admin='00000000-0000-4000-8000-000000000001',student='00000000-0000-4000-8000-000000000002',other='00000000-0000-4000-8000-000000000003',eid='00000000-0000-4000-8000-000000000010';
 for(const [id,username,role] of [[admin,'admin','admin'],[student,'student','student'],[other,'other','student']])await db.query("insert into users values($1,$2,'test-password',$2,$3,'active','test','3')",[id,username,role]);
 await db.exec(fs.readFileSync(path.join(__dirname,'../../migrations/20261012_korean_exams.sql'),'utf8'));
 await db.exec('set role anon');
 const login=async name=>(await db.query("select bmaps_ko_login($1,'test-password') v",[name])).rows[0].v.token;
 const at=await login('admin'),st=await login('student'),ot=await login('other');
 const api=async(t,a,d={})=>(await db.query('select bmaps_ko_api($1,$2,$3::jsonb) v',[t,a,JSON.stringify(d)])).rows[0].v;
 await assert.rejects(()=>db.query('select * from bmaps_ko_exams'));
 await assert.rejects(()=>db.query("select bmaps_ko_login('admin','wrong')"));
 const payload={id:eid,title:'테스트 국어',elective:'공통',duration:80,students:[student],sets:[{range:'1~2',area:'독서',passage:['ko-published/'+eid+'/0.png'],questions:[{no:1,points:2,images:['ko-published/'+eid+'/1.png'],answer:'LEAK'},{no:2,points:3,images:['ko-published/'+eid+'/2.png']}],answer:'LEAK'}],keys:{1:{answer:'4',points:2},2:{answer:'2',points:3}}};
 await assert.rejects(()=>api(st,'publish',payload));
 await api(at,'publish',payload);await api(at,'publish',payload);
 assert.equal((await api(at,'list')).length,1,'publish must be idempotent');
 assert.equal((await api(ot,'list')).length,0);
 await assert.rejects(()=>api(ot,'start',{id:eid}));
 let exam=await api(st,'start',{id:eid});assert.equal(exam.sets.length,1);assert.ok(!JSON.stringify(exam).includes('LEAK'));assert.ok(!JSON.stringify(exam.sets).includes('answer'));
 await api(st,'save',{id:eid,answers:{1:'4'}});
 assert.equal((await api(st,'start',{id:eid})).answers['1'],'4');
 let r=await api(st,'submit',{id:eid,answers:{1:'4',2:'1'}});assert.equal(r.result.score,2);assert.equal(r.result.total,5);
 assert.deepEqual(await api(st,'submit',{id:eid,answers:{1:'1',2:'2'}}),r,'repeat submit cannot change grade');
 assert.equal((await api(at,'results',{id:eid}))[0].result.score,2);
 await api(at,'visibility',{id:eid,published:false});await assert.rejects(()=>api(st,'start',{id:eid}));
 // Expiry grades only saved answers and ignores answers supplied after the deadline.
 await api(at,'visibility',{id:eid,published:true});await db.exec('reset role');await db.query("update bmaps_ko_attempts set submitted_at=null,result=null,answers='{\"1\":\"4\"}',deadline=now()-interval '1 second' where exam_id=$1",[eid]);await db.exec('set role anon');
 r=await api(st,'submit',{id:eid,answers:{1:'1',2:'2'}});assert.equal(r.result.score,2);
 await api(st,'logout');await assert.rejects(()=>api(st,'list'));
 await db.close();console.log('PASS SQL: permissions, identity, assignments, no answer leak, save/resume, scoring, idempotence, expiry, logout');
})().catch(e=>{console.error(e);process.exitCode=1});
