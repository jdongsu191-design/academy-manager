(function(){
 'use strict';
 var rows=[],answerRows=[],prepared=null,sets=[],students=[],pending=null,working=false;
 var selected=new Set(),studentsLoaded=false,appliedCondition=null;
 var token=sessionStorage.getItem('ko-admin-token')||'';
 var card=document.createElement('section');card.className='card';card.style.marginTop='18px';
 card.innerHTML='<h3>국어 시험지 등록</h3><p class="hint">정답 확인 → 시험 설정 → 응시 대상 지정 → 발행 순서로 등록합니다.</p><h4>1️⃣ 정답·배점 확인</h4>'
 +'<p><label>정답 PDF <input id="kp-answer" type="file" accept="application/pdf"></label> <button class="btn" id="kp-read">정답 읽기</button></p>'
 +'<p><label>선택과목 <select class="inp" id="kp-elective"><option>화법과 작문</option><option>언어와 매체</option><option>공통</option></select></label> <button class="btn" id="kp-prepare">정답·배점 확인</button></p>'
 +'<div id="kp-grid" style="max-height:320px;overflow:auto"></div><h4>2️⃣ 시험 설정</h4><div class="frow"><label for="kp-title">시험명</label><input class="inp" id="kp-title" maxlength="150" placeholder="예: 6월 평가원 국어"></div><div class="frow"><label for="kp-duration">제한시간(분)</label><input class="inp" id="kp-duration" type="number" min="1" max="240" value="80" style="max-width:140px"></div>'
 +'<h4>3️⃣ 응시 대상</h4><details open id="kp-auth"><summary id="kp-auth-status">관리자 인증</summary><p class="hint">BMAPS 관리자/데스크 계정으로 인증하면 학생 목록을 자동으로 불러옵니다.</p><input class="inp" id="kp-user" autocomplete="username" placeholder="아이디"><input class="inp" id="kp-password" type="password" autocomplete="current-password" placeholder="비밀번호"><button class="btn" id="kp-login">인증</button></details>'
 +'<div class="frow"><label for="kp-school">학교</label><select class="inp" id="kp-school" disabled><option value="">무관 (전체 학교)</option></select></div><div class="frow"><label for="kp-grade">학년</label><select class="inp" id="kp-grade" disabled><option value="">무관 (전 학년)</option></select></div>'
 +'<p><button class="btn btn-primary" id="kp-apply-targets" disabled>조건에 맞는 학생 지정</button> <button class="btn" id="kp-students-load">학생 목록 새로고침</button></p><p class="hint" id="kp-target-summary" role="status">인증 후 학교·학년을 선택하세요.</p>'
 +'<details id="kp-individual"><summary>대상 학생 확인 · 개별 제외/추가</summary><p><input class="inp" id="kp-filter" placeholder="학생 이름 검색" aria-label="학생 이름 검색"> <label><input type="checkbox" id="kp-selected-only">선택한 학생만</label> <button class="btn" id="kp-clear-targets">전체 선택 해제</button></p><div id="kp-students" style="max-height:260px;overflow:auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))"></div></details>'
 +'<h4>4️⃣ 등록·발행</h4><p id="kp-summary" class="hint" role="status"></p><p class="hint">발행하면 지정한 학생이 바로 응시할 수 있습니다. 대상은 등록 시점의 명단으로 저장됩니다.</p><p><label><input type="checkbox" id="kp-confirm"> 원본과 정답·배점을 확인했습니다.</label></p><button class="btn btn-primary" id="kp-publish">시험지 등록 · 발행</button> <a class="btn" href="korean-exam.html" target="_blank" rel="noopener">학생 응시 화면</a>'
 +'<p id="kp-msg" role="status" style="white-space:pre-wrap"></p><hr><h4>등록된 시험지 · 응시 현황</h4><button class="btn" id="kp-list">새로고침</button><div id="kp-exams" class="ex-grid"></div><div id="kp-results"></div>';
 document.getElementById('ko-result').before(card);
 var $=id=>document.getElementById(id),msg=(s,bad)=>{$('kp-msg').textContent=s;$('kp-msg').style.color=bad?'#b91c1c':'#166534';};
 var esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 async function api(action,data){if(!token)throw Error('먼저 배포·응시 현황 인증을 해 주세요.');var r=await db.rpc('bmaps_ko_api',{p_token:token,p_action:action,p_data:data||{}});if(r.error)throw Error(r.error.message);return r.data;}
 function action(id,fn){$(id).onclick=async()=>{if(working)return;working=true;$(id).disabled=true;try{await fn();}catch(e){msg(e.message+'\n함수를 찾을 수 없다는 오류라면 국어 시험 SQL 설치가 필요합니다.',true);}finally{working=false;$(id).disabled=false;if(id==='kp-publish')$(id).textContent=pending?'이전 시험 등록 재시도':'시험지 등록 · 발행';}};}
 action('kp-login',async()=>{var password=$('kp-password').value;$('kp-password').value='';var r=await db.rpc('bmaps_ko_login',{p_username:$('kp-user').value.trim(),p_password:password});if(r.error)throw Error(r.error.message);if(!['admin','desk'].includes(r.data.role))throw Error('관리자·데스크 계정만 배포할 수 있습니다.');token=r.data.token;sessionStorage.setItem('ko-admin-token',token);await loadStudents();$('kp-auth-status').textContent=r.data.name+' · 인증 완료';$('kp-auth').open=false;msg('인증 완료. 학교·학년을 고르고 대상 학생을 지정하세요.');await list();});
 action('kp-read',async()=>{var file=$('kp-answer').files[0];if(!file)throw Error('정답 PDF를 선택하세요.');if(file.size>10*1024*1024)throw Error('정답 파일은 10MB 이하여야 합니다.');var result=await koLocalCall('/answers',{method:'POST',headers:{'Content-Type':'application/pdf'},body:file});answerRows=result.rows;prepared=null;rows=[];$('kp-grid').replaceChildren();summary();msg('정답 '+answerRows.length+'개를 읽었습니다. 선택과목을 고르고 정답·배점 확인을 누르세요.');});
 action('kp-prepare',async()=>{if(pending)throw Error('먼저 이전 배포 요청을 재시도해 결과를 확인하세요.');prepared=koGetDraft();sets=KoExamCore.selectSets(prepared,$('kp-elective').value);var map={};answerRows.filter(r=>r.elective==='공통'||r.elective===$('kp-elective').value).forEach(r=>{map[r.no]=r;});rows=sets.flatMap(s=>s.qs.map(q=>({no:q.no,answer:map[q.no]?map[q.no].answer:'',points:map[q.no]?map[q.no].points:q.pts||2}))).sort((a,b)=>a.no-b.no);
 $('kp-grid').innerHTML='<table style="width:100%"><thead><tr><th>번호</th><th>정답(1~5)</th><th>배점</th></tr></thead><tbody>'+rows.map((r,i)=>'<tr><td>'+r.no+'</td><td><input aria-label="'+r.no+'번 정답" data-i="'+i+'" data-field="answer" type="number" min="1" max="5" value="'+esc(r.answer)+'"></td><td><input aria-label="'+r.no+'번 배점" data-i="'+i+'" data-field="points" type="number" min="1" max="10" value="'+r.points+'"></td></tr>').join('')+'</tbody></table>';
 if(!$('kp-title').value)$('kp-title').value=(_ko.file?_ko.file.name.replace(/\.pdf$/i,''):'국어 시험')+' · '+$('kp-elective').value;
 $('kp-confirm').checked=false;summary();msg(rows.length+'문항 준비 · 정답을 직접 수정할 수 있습니다.');});
 $('kp-grid').oninput=e=>{if(e.target.dataset.field){rows[+e.target.dataset.i][e.target.dataset.field]=e.target.value;$('kp-confirm').checked=false;summary();}};
 $('kp-elective').onchange=()=>{prepared=null;$('kp-confirm').checked=false;summary();};
 function condition(){return JSON.stringify([$('kp-school').value,$('kp-grade').value]);}
 function matches(s){return (!$('kp-school').value||String(s.school||'')===$('kp-school').value)&&(!$('kp-grade').value||String(s.grade||'')===$('kp-grade').value);}
 function summary(){
  var total=rows.reduce((n,r)=>n+(+r.points||0),0),missing=rows.filter(r=>!r.answer).length;
  $('kp-summary').textContent=rows.length+'문항 · '+total+'점'+(missing?' · 정답 미입력 '+missing+'개':'')+' · '+$('kp-elective').value+' · 응시 대상 '+selected.size+'명';
  if(!studentsLoaded)return;
  var matched=students.filter(matches).length,outside=students.filter(s=>selected.has(s.id)&&!matches(s)).length;
  $('kp-target-summary').textContent='조건 일치 '+matched+'명 · 최종 대상 '+selected.size+'명'+(outside?' (조건 외 개별 추가 '+outside+'명)':'')+(appliedCondition!==condition()?' · 조건에 맞는 학생 지정을 눌러 반영하세요.':' · 아래에서 개별 조정할 수 있습니다.');
 }
 function renderStudents(){
  $('kp-students').replaceChildren();
  var visible=students.filter(s=>(!$('kp-selected-only').checked||selected.has(s.id))&&s.name.includes($('kp-filter').value));
  visible.forEach(s=>{var label=document.createElement('label');label.style.padding='7px';var cb=document.createElement('input');cb.type='checkbox';cb.value=s.id;cb.checked=selected.has(s.id);cb.onchange=()=>{if(cb.checked)selected.add(s.id);else selected.delete(s.id);summary();if($('kp-selected-only').checked)renderStudents();};label.append(cb,document.createTextNode(' '+s.name+' · '+(s.school||'학교 미등록')+' '+(s.grade||'학년 미등록')));$('kp-students').append(label);});
  if(!visible.length)$('kp-students').textContent='표시할 학생이 없습니다.';
  summary();
 }
 async function loadStudents(){
  var fresh=await api('students');students=fresh;studentsLoaded=true;
  selected=new Set(Array.from(selected).filter(id=>students.some(s=>s.id===id)));
  [['kp-school','school','무관 (전체 학교)'],['kp-grade','grade','무관 (전 학년)']].forEach(([id,key,label])=>{var previous=$(id).value;$(id).replaceChildren(new Option(label,''));Array.from(new Set(students.map(s=>String(s[key]||'')).filter(Boolean))).sort((a,b)=>a.localeCompare(b,'ko',{numeric:true})).forEach(v=>$(id).add(new Option(v,v)));$(id).value=previous;if($(id).selectedIndex<0)$(id).value='';$(id).disabled=false;});
  // Refresh never silently adds newly enrolled students to an already reviewed target list.
  appliedCondition=null;$('kp-apply-targets').disabled=false;renderStudents();
 }
 action('kp-students-load',async()=>{await loadStudents();msg('학생 목록을 새로 불러왔습니다. 조건으로 대상을 지정해 주세요.');});
 action('kp-apply-targets',async()=>{selected=new Set(students.filter(matches).map(s=>s.id));appliedCondition=condition();renderStudents();msg('응시 대상 '+selected.size+'명을 지정했습니다. 필요하면 개별 조정하세요.');});
 $('kp-school').onchange=$('kp-grade').onchange=summary;
 $('kp-filter').oninput=$('kp-selected-only').onchange=renderStudents;
 $('kp-clear-targets').onclick=()=>{selected.clear();renderStudents();};
 async function uploadImages(owner,id,counter){var out=[];for(var region of owner.sourceRegions||[]){if(!/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(region.image||''))throw Error('원본 이미지 오류');var key='ko-published/'+id+'/'+(counter.n++)+'.png';var raw=atob(region.image.split(',')[1]),bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));var r=await db.storage.from('bety-exam').upload(key,new Blob([bytes],{type:'image/png'}),{contentType:'image/png',upsert:false});if(r.error)throw Error('이미지 업로드 실패: '+r.error.message);out.push(key);}return out;}
 action('kp-publish',async()=>{
  if(!pending){if(!prepared||prepared!==koGetDraft())throw Error('현재 분석 결과의 정답·배점을 먼저 확인하세요.');var total=KoExamCore.validate(rows);if(!$('kp-confirm').checked)throw Error('원본 확인 항목을 체크하세요.');if(appliedCondition!==condition())throw Error('학교·학년 조건을 적용한 뒤 최종 대상 인원을 확인하세요.');var targets=Array.from(selected);if(!targets.length)throw Error('응시 대상 학생을 지정하세요.');var title=$('kp-title').value.trim(),duration=+$('kp-duration').value,elective=$('kp-elective').value;if(!title||!Number.isInteger(duration)||duration<1||duration>240)throw Error('시험명과 제한시간을 확인하세요.');await api('list');if(!confirm(title+' · '+rows.length+'문항 / '+total+'점\n선택한 '+targets.length+'명에게 발행할까요? 학생이 바로 응시할 수 있습니다.'))return;
   var id=crypto.randomUUID(),counter={n:0},body=[],keys={};rows.forEach(r=>keys[r.no]={answer:String(r.answer),points:+r.points});msg('원본 이미지 업로드 중…');
   for(var s of sets){var item={range:s.range,area:s.area,passage:await uploadImages(s,id,counter),questions:[]};for(var q of s.qs)item.questions.push({no:q.no,points:keys[q.no].points,images:await uploadImages(q,id,counter)});body.push(item);}
   pending={id:id,title:title,elective:elective,duration:duration,students:targets,sets:body,keys:keys};
  }
  msg('시험 저장 중…');await api('publish',pending);pending=null;msg('배포 완료. 학생에게 이 주소를 안내하세요: '+new URL('korean-exam.html',location.href).href);await list();
 });
 async function list(){var exams=await api('list');$('kp-exams').replaceChildren();if(!exams.length)$('kp-exams').textContent='등록된 국어 시험지가 없습니다.';exams.forEach(ex=>{var p=document.createElement('div');p.className='ex-card';p.style.cursor='default';var name=document.createElement('div');name.className='ex-name';name.textContent=ex.title;var meta=document.createElement('div');meta.className='ex-meta';meta.textContent=ex.elective+' · '+ex.duration+'분';var badge=document.createElement('span');badge.className='ex-badge '+(ex.published?'bg-pub':'bg-draft');badge.textContent=ex.published?'발행 · 학생 응시 가능':'미발행 · 학생 응시 불가';p.append(name,meta,badge,document.createElement('br'));var b=document.createElement('button');b.className='btn';b.textContent='응시 현황';b.onclick=async()=>{try{var data=await api('results',{id:ex.id});$('kp-results').innerHTML='<h4>'+esc(ex.title)+'</h4>'+data.map(r=>'<p>'+esc(r.name)+' · '+(r.result?esc(r.result.score)+' / '+esc(r.result.total)+'점':r.started_at?'응시 중':'미응시')+'</p>').join('');}catch(e){msg(e.message,true);}};p.append(b);var v=document.createElement('button');v.className='btn';v.textContent=ex.published?'미발행으로 전환':'발행하기';v.onclick=async()=>{if(!confirm('배포 상태를 변경할까요? 비공개이면 진행 중 응시도 접근할 수 없습니다.'))return;try{await api('visibility',{id:ex.id,published:!ex.published});await list();}catch(e){msg(e.message,true);}};p.append(v);$('kp-exams').append(p);});}
 action('kp-list',list);
 summary();
 if(token){loadStudents().then(()=>{$('kp-auth-status').textContent='관리자 인증 유지 중';$('kp-auth').open=false;return list();}).catch(e=>{msg(e.message,true);$('kp-auth').open=true;});}
})();
