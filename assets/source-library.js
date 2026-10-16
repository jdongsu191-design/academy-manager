/* Original-source library. Immutable Storage revisions + conditional DB pointer update.
   Uses the existing BMAPS users/variant_docs/variants access policies; no new public API. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id), bucket=db.storage.from('variants');
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let user, rows=[], row=null, book=null, busy=false, urls=new Map(), editing=null;
  const clone=x=>JSON.parse(JSON.stringify(x));
  function notice(s){$('notice').textContent=s;}
  function assertAdmin(){if(!user||user.role!=='admin')throw Error('관리자만 원본 교재를 구축할 수 있습니다.');}
  function lock(on){busy=on;document.querySelectorAll('#workspace button,#workspace input,#workspace select,#new-book,#books button').forEach(e=>e.disabled=on);}
  async function action(fn){if(busy)return;lock(true);try{await fn();}catch(e){notice(e.message||String(e));}finally{lock(false);}}
  async function signed(path){if(!urls.has(path)){const r=await bucket.createSignedUrl(path,3600);if(r.error)throw r.error;urls.set(path,r.data.signedUrl);}return urls.get(path);}
  async function upload(path,blob){const r=await bucket.upload(path,blob,{upsert:false});if(r.error)throw Error('저장 실패: '+r.error.message);}
  function download(blob,name){const a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
  async function warmImages(data){
    const paths=[...new Set([...data.items,...(data.candidates||[])].flatMap(q=>[...(q.figure_images||[]),...(q.solution_images||[])])).values()].filter(x=>!x.startsWith('data:'));
    for(let i=0;i<paths.length;i+=20)await Promise.all(paths.slice(i,i+20).map(signed));
  }
  async function storeImages(data,id){
    for(const q of [...data.items,...(data.candidates||[])])for(const field of ['figure_images','solution_images']){
      for(let i=0;i<(q[field]||[]).length;i++){
        const uri=q[field][i];if(!uri.startsWith('data:'))continue;
        if(!uri.startsWith('data:image/png;base64,'))throw Error('PNG 그림만 저장할 수 있습니다.');
        const bytes=Uint8Array.from(atob(uri.split(',')[1]),c=>c.charCodeAt(0));
        if(bytes.length>4*1024*1024)throw Error('그림은 4MB 이하로 등록하세요.');
        const path=`library/${id}/images/${crypto.randomUUID()}.png`;
        await upload(path,new Blob([bytes],{type:'image/png'}));q[field][i]=path;await signed(path);
      }
    }
  }
  function filename(name){return String(name).replace(/[\\/:*?"<>|]/g,'_');}
  async function pdfFile(file){
    if(!file||!file.name.toLowerCase().endsWith('.pdf')||file.size>50*1024*1024)throw Error('50MB 이하 PDF 파일을 선택하세요.');
    if(!new TextDecoder().decode(await file.slice(0,5).arrayBuffer()).startsWith('%PDF-'))throw Error('유효한 PDF 파일이 아닙니다.');
    return file;
  }
  async function list(){
    const r=await db.from('variant_docs').select('*').eq('source_type','원본교재').is('deleted_at',null).order('created_at',{ascending:false}).limit(500);
    if(r.error)throw r.error;rows=r.data||[];renderBooks();
  }
  function renderBooks(){const term=$('search').value.trim().toLowerCase();$('books').innerHTML=rows.filter(r=>[r.title,r.subject,r.grade].join(' ').toLowerCase().includes(term)).map(r=>`<button class="book ${r.id===row?.id?'active':''}" data-id="${esc(r.id)}"><b>${esc(r.title)}</b><br><small>${esc(r.grade)} · ${esc(r.subject)}</small></button>`).join('')||'<p>등록된 원본 교재가 없습니다.</p>';}
  async function open(id){
    const r=await db.from('variant_docs').select('*').eq('id',id).eq('source_type','원본교재').single();if(r.error)throw r.error;
    const response=await fetch(await signed(r.data.file_path));if(!response.ok)throw Error('교재 저장본을 읽지 못했습니다.');
    const next=await response.json();if(next.version!==1||!Array.isArray(next.items)||!Array.isArray(next.sources))throw Error('교재 데이터 버전을 확인하세요.');
    await warmImages(next);row=r.data;book=next;renderBooks();render();notice('저장본을 열었습니다. AI 추출 결과는 반드시 원본과 대조하세요.');
  }
  async function save(next){
    assertAdmin();const owner=row, path=`library/${owner.id}/revisions/${crypto.randomUUID()}.json`;
    next.modified_at=new Date().toISOString();next.modified_by=user.id;
    await storeImages(next,owner.id);
    await upload(path,new Blob([JSON.stringify(next)],{type:'application/json'}));
    // A stale browser must never overwrite a newer administrator revision.
    const r=await db.from('variant_docs').update({file_path:path,updated_at:next.modified_at,status:'구축 중',title:next.title,subject:next.subject,grade:next.grade})
      .eq('id',owner.id).eq('file_path',owner.file_path).select('id');
    if(r.error||!r.data?.length)throw Error(r.error?.message||'다른 화면에서 교재를 수정했습니다. 현재 입력을 복사한 뒤 저장본을 다시 열어주세요. 이전 저장본은 유지됩니다.');
    row={...owner,file_path:path,updated_at:next.modified_at,title:next.title,subject:next.subject,grade:next.grade};book=next;
    rows=rows.map(r=>r.id===row.id?row:r);renderBooks();
  }
  function source(){return book.sources.find(s=>s.id===$('source').value)||book.sources[0];}
  function render(){
    $('workspace').hidden=false;$('book-title').textContent=book.title;$('book-meta').textContent=[book.subject,book.grade,book.edition].filter(Boolean).join(' · ');
    const prior=$('source').value;$('source').innerHTML=book.sources.map(s=>`<option value="${esc(s.id)}">${s.kind==='answers'?'답지':'문제'} · ${esc(s.name)}${s.pages?' ('+s.pages+'쪽)':''}</option>`).join('');if(book.sources.some(s=>s.id===prior))$('source').value=prior;
    $('coverage').textContent='완료한 추출 범위: '+(book.runs||[]).map(r=>`${book.sources.find(s=>s.id===r.source_id)?.name||'원본'} ${r.start}~${r.end}쪽`).join(' / ');
    renderItems();renderCandidates();view().catch(e=>notice(e.message));
  }
  async function view(page){const s=source();if(!s)return;const n=Number(page||$('view-page').value)||1;const url=await signed(s.path);$('view-page').value=n;$('pdf').src=url+'#page='+n;$('open-pdf').href=url+'#page='+n;}
  function itemSummary(q){return `${q.unit||'단원 미지정'} · ${q.number||'번호 없음'} · PDF ${q.regions?.[0]?.page||'?'}쪽`;}
  function renderItems(){const state=$('filter').value;const items=book.items.filter(q=>state==='all'||q.status===state);
    $('items').innerHTML=`<p>전체 ${book.items.length}문항 · 사용 가능 ${book.items.filter(q=>q.status==='ready').length}문항</p>`+items.map(q=>`<article class="card"><div class="row">${q.status==='ready'?`<label class="check"><input type="checkbox" data-export="${q.id}" checked>출력</label>`:''}<b>${esc(itemSummary(q))}</b><span class="badge ${q.status==='ready'?'ready':''}">${q.status==='ready'?'사용 가능':'검수 필요'}</span></div><pre>${esc(q.statement)}</pre>${(q.figure_images||[]).map(src=>`<img src="${esc(urls.get(src)||src)}" alt="원본 도형">`).join('')}<p>정답: ${esc(q.answer||'미등록')}</p>${q.warning?`<p class="muted">${esc(q.warning)}</p>`:''}<div class="row"><button data-edit="${q.id}">검수·수정</button><button data-view="${q.id}">원본 위치</button><button data-remove="${q.id}" class="danger">제외</button></div></article>`).join('');
  }
  function renderCandidates(){
    $('candidate-list').innerHTML=(book.candidates||[]).map(q=>`<article class="card"><b>${esc(itemSummary(q))} · ${q.kind==='answers'?'정답·해설 후보':'문제 후보'}</b><pre>${esc(q.statement||q.solution)}</pre><p>정답: ${esc(q.answer)}</p><p>${esc(q.warning)}</p><div class="row">${q.kind==='answers'?`<select data-target="${q.id}" aria-label="정답 연결 대상"><option value="">연결할 문항을 선택하세요</option>${book.items.map(p=>`<option value="${p.id}">${esc(itemSummary(p))}</option>`).join('')}</select><button data-link="${q.id}">정답·해설 연결</button>`:`<button data-accept="${q.id}">검수 문항으로 추가</button>`}<button data-cview="${q.id}">원본 위치</button><button data-discard="${q.id}">후보 제외</button></div></article>`).join('')||'<p class="muted">대기 중인 후보가 없습니다.</p>';
  }
  const jobKey=()=>`bmaps-source-job:${user.id}:${row.id}`;
  async function poll(job){
    for(let i=0;i<1800;i++){
      const state=await SourceWorker.call('/jobs/'+encodeURIComponent(job.id));notice(state.message||'원본 처리 중');
      if(state.status==='failed'){localStorage.removeItem(jobKey());throw Error(state.message);}
      if(state.status==='complete')return state.result;
      await new Promise(r=>setTimeout(r,2000));
    }throw Error('대기 시간이 길어지고 있습니다. 진행 작업 다시 확인을 눌러 이어서 확인하세요.');
  }
  async function receive(job){
    const result=await poll(job);if(result.kind!=='source'||result.operation!==job.operation)throw Error('작업 결과 종류 오류');
    if(book.applied_jobs.includes(job.id)){localStorage.removeItem(jobKey());notice('이미 저장된 분석 결과입니다.');return;}
    const next=clone(book), s=next.sources.find(s=>s.id===job.source_id);if(!s)throw Error('분석한 원본 파일을 찾을 수 없습니다.');
    s.pages=result.pages;
    next.candidates.push(...result.items.map(q=>({...q,source_id:s.id,kind:job.operation==='answers'?'answers':'questions',job_id:job.id})));
    next.runs.push({source_id:s.id,start:result.start,end:result.end,job_id:job.id,issues:result.issues});next.applied_jobs.push(job.id);
    await save(next);localStorage.removeItem(jobKey());render();notice(`${result.items.length}개 후보를 저장했습니다. 기존 문항은 유지됩니다.\n${result.issues.join('\n')}`);
  }
  async function b64(blob){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=()=>reject(Error('파일 읽기 실패'));r.readAsDataURL(blob);});}
  async function extract(){
    assertAdmin();if(localStorage.getItem(jobKey()))throw Error('미확인 작업이 있습니다. 진행 작업 다시 확인을 먼저 누르세요.');
    const s=source(),start=Number($('start').value),end=Number($('end').value);
    if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end<start||end-start>=5)throw Error('올바른 PDF 페이지 범위(최대 5쪽)를 선택하세요.');
    SourceWorker.supports(await SourceWorker.call('/health'));
    notice('원본 파일을 준비하고 있습니다.');const response=await fetch(await signed(s.path));if(!response.ok)throw Error('원본 다운로드 실패');
    const file=await response.blob();if(file.size>50*1024*1024)throw Error('원본이 50MB를 초과합니다.');
    const operation=s.kind==='answers'?'answers':'extract';
    const request={operation,start,end,pdf:await b64(file)};
    const job=await SourceWorker.call('/jobs?kind=source',{method:'POST',body:JSON.stringify(request)});
    Object.assign(job,{operation,source_id:s.id});localStorage.setItem(jobKey(),JSON.stringify(job));await receive(job);
  }
  function showEditor(q){editing=clone(q);$('q-number').value=q.number||'';$('q-unit').value=q.unit||'';$('q-printed').value=q.printed_page||'';$('q-page').value=q.regions?.[0]?.page||1;['statement','answer','solution','warning'].forEach(k=>$('q-'+k).value=q[k]||'');$('q-status').value='review';$('q-confirm').checked=false;$('q-image').value='';$('edit-status').textContent='';renderEditorFigures();$('editor').showModal();}
  function renderEditorFigures(){$('q-figures').innerHTML=(editing.figure_images||[]).map((src,i)=>`<div><img src="${esc(urls.get(src)||src)}" alt="문항 그림 ${i+1}"><button type="button" data-drop-image="${i}">그림 제외</button></div>`).join('')+(editing.solution_images||[]).map((src,i)=>`<div><p>해설 그림</p><img src="${esc(urls.get(src)||src)}" alt="해설 그림 ${i+1}"><button type="button" data-drop-solution-image="${i}">해설 그림 제외</button></div>`).join('');}
  $('q-figures').onclick=e=>{if(e.target.dataset.dropSolutionImage!==undefined){editing.solution_images.splice(Number(e.target.dataset.dropSolutionImage),1);renderEditorFigures();}if(e.target.dataset.dropImage!==undefined){editing.figure_images.splice(Number(e.target.dataset.dropImage),1);renderEditorFigures();}};
  $('q-image').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>4*1024*1024||f.type!=='image/png')throw Error('4MB 이하 PNG를 선택하세요.');if(editing.figure_images.length>=10)throw Error('문항 그림은 최대 10개입니다.');editing.figure_images.push('data:image/png;base64,'+await b64(f));renderEditorFigures();}catch(err){$('edit-status').textContent=err.message;}};
  $('edit-form').onsubmit=async e=>{
    e.preventDefault();if(busy)return;lock(true);const submit=e.submitter;submit.disabled=true;
    try{assertAdmin();const q=clone(editing);q.number=$('q-number').value.trim();q.unit=$('q-unit').value.trim();q.printed_page=$('q-printed').value.trim();
      ['statement','answer','solution','warning'].forEach(k=>q[k]=$('q-'+k).value.trim());q.status=$('q-status').value;
      if(!q.number||!q.statement)throw Error('문항 번호와 본문이 필요합니다.');
      if(['statement','answer','solution'].some(k=>q[k].split('$').length%2===0))throw Error('수식의 여는 $와 닫는 $를 확인하세요.');
      const page=Number($('q-page').value);if(!Number.isInteger(page)||page<1)throw Error('PDF 페이지를 확인하세요.');
      if(!q.regions?.length)q.regions=[{page,box:[0,0,1,1]}];else q.regions[0].page=page;
      if(q.status==='ready'&&(!$('q-confirm').checked||!q.answer))throw Error('정답 입력과 원본 대조 확인 후 사용 가능으로 전환하세요.');
      const duplicate=book.items.some(x=>x.id!==q.id&&x.source_id===q.source_id&&x.number===q.number&&x.unit===q.unit&&x.regions?.[0]?.page===page);
      if(duplicate)throw Error('같은 원본 페이지·단원·번호의 문항이 있습니다. 기존 문항을 수정하세요.');
      q.reviewed_by=q.status==='ready'?user.id:null;q.reviewed_at=q.status==='ready'?new Date().toISOString():null;
      const next=clone(book),index=next.items.findIndex(x=>x.id===q.id);if(index<0)next.items.push(q);else next.items[index]=q;
      await save(next);$('editor').close();renderItems();notice('문항을 저장했습니다.');
    }catch(err){$('edit-status').textContent=err.message;}finally{submit.disabled=false;lock(false);}
  };
  $('items').onclick=e=>action(async()=>{const t=e.target;if(t.dataset.edit){showEditor(book.items.find(q=>q.id===t.dataset.edit));return;}
    if(t.dataset.view){const q=book.items.find(q=>q.id===t.dataset.view);$('source').value=q.source_id;await view(q.regions?.[0]?.page);}
    if(t.dataset.remove&&confirm('문항을 목록에서 제외할까요? 이전 저장본과 원본 PDF는 남습니다.')){const next=clone(book);next.items=next.items.filter(q=>q.id!==t.dataset.remove);await save(next);renderItems();renderCandidates();}
  });
  $('candidate-list').onclick=e=>action(async()=>{const t=e.target,id=t.dataset.accept||t.dataset.discard||t.dataset.link||t.dataset.cview;if(!id)return;const q=book.candidates.find(q=>q.id===id);
    if(t.dataset.cview){$('source').value=q.source_id;await view(q.regions[0].page);return;}
    const next=clone(book);
    if(t.dataset.accept){if(book.items.some(p=>p.source_id===q.source_id&&p.number===q.number&&p.unit===q.unit&&p.regions?.[0]?.page===q.regions[0].page))throw Error('동일 위치의 문항이 이미 있습니다. 기존 문항을 검수·수정하세요.');next.items.push({...q,status:'review'});}
    if(t.dataset.link){const target=document.querySelector(`[data-target="${id}"]`).value;if(!target)throw Error('답지와 연결할 문항을 직접 선택하세요.');if(!q.answer&&!q.solution)throw Error('후보에 정답·해설이 없습니다. 원본을 확인하세요.');const item=next.items.find(p=>p.id===target);if((item.answer||item.solution)&&!confirm('기존 정답·해설을 선택한 답지 내용으로 바꿀까요?'))return;
      item.answer=q.answer;item.solution=q.solution;item.solution_images=q.figure_images||[];item.answer_source={source_id:q.source_id,regions:q.regions};item.status='review';item.reviewed_at=null;item.reviewed_by=null;}
    next.candidates=next.candidates.filter(p=>p.id!==id);await save(next);renderItems();renderCandidates();notice('후보 처리를 저장했습니다.');
  });
  $('new-book').onclick=()=>{$('create-status').textContent='';$('create').showModal();};
  $('cancel-create').onclick=()=>{if(!busy)$('create').close();};$('cancel-edit').onclick=()=>{if(!busy)$('editor').close();};
  for(const id of ['create','editor'])$(id).addEventListener('cancel',e=>{if(busy)e.preventDefault();});
  $('create-form').onsubmit=async e=>{
    e.preventDefault();if(busy)return;lock(true);e.submitter.disabled=true;
    try{assertAdmin();const main=await pdfFile($('question-file').files[0]),answer=$('answer-file').files[0];if(answer)await pdfFile(answer);
      const id=crypto.randomUUID(),sources=[];$('create-status').textContent='원본 PDF를 저장하고 있습니다…';
      for(const [file,kind] of [[main,'questions'],[answer,'answers']]){if(!file)continue;const sid=crypto.randomUUID(),path=`library/${id}/files/${sid}.pdf`;await upload(path,file);sources.push({id:sid,name:file.name,path,kind});}
      const initial={version:1,title:$('title').value.trim(),subject:$('subject').value.trim(),grade:$('grade').value.trim(),edition:$('edition').value.trim(),sources,items:[],candidates:[],runs:[],applied_jobs:[]};
      const path=`library/${id}/revisions/${crypto.randomUUID()}.json`;await upload(path,new Blob([JSON.stringify(initial)],{type:'application/json'}));
      const r=await db.from('variant_docs').insert({id,title:initial.title,subject:initial.subject,grade:initial.grade,source_type:'원본교재',file_kind:'pdf',file_path:path,status:'구축 중',created_by:user.id,branch_id:user.branch_id});if(r.error)throw r.error;
      $('create').close();$('create-form').reset();await list();await open(id);
    }catch(err){$('create-status').textContent='등록 실패: '+err.message;}finally{e.submitter.disabled=false;lock(false);}
  };
  $('books').onclick=e=>{const b=e.target.closest('[data-id]');if(b)action(()=>open(b.dataset.id));};$('search').oninput=renderBooks;
  $('source').onchange=()=>action(async()=>{await view(1);});$('view').onclick=()=>action(()=>view());$('filter').onchange=renderItems;
  $('extract').onclick=()=>action(extract);$('resume').onclick=()=>action(async()=>{const raw=localStorage.getItem(jobKey());if(!raw)throw Error('미확인 작업이 없습니다.');await receive(JSON.parse(raw));});
  $('reload').onclick=()=>action(async()=>{urls.clear();await open(row.id);});
  $('forget-job').onclick=()=>{if(!busy&&confirm('이 브라우저의 작업 확인 기록만 해제합니다. 실행 중인 Codex 작업은 취소되지 않습니다. 이미 완료한 결과가 있다면 먼저 다시 확인하세요. 계속할까요?')){localStorage.removeItem(jobKey());notice('작업 확인 기록을 해제했습니다.');}};
  $('backup').onclick=()=>download(new Blob([JSON.stringify(book,null,2)],{type:'application/json'}),filename(book.title)+'-원본데이터.json');
  $('clear-export').onclick=()=>document.querySelectorAll('[data-export]').forEach(e=>e.checked=false);
  $('manual').onclick=()=>showEditor({id:crypto.randomUUID(),source_id:source().id,regions:[{page:Number($('view-page').value)||1,box:[0,0,1,1]}],figure_images:[],status:'review'});
  $('edit-meta').onclick=()=>action(async()=>{const title=prompt('교재명',book.title);if(title===null)return;if(!title.trim())throw Error('교재명이 필요합니다.');const edition=prompt('개정판·연도',book.edition);if(edition===null)return;const next=clone(book);next.title=title.trim();next.edition=edition.trim();await save(next);render();});
  $('add-file').onchange=e=>action(async()=>{const file=await pdfFile(e.target.files[0]),id=crypto.randomUUID(),path=`library/${row.id}/files/${id}.pdf`;await upload(path,file);const next=clone(book);next.sources.push({id,path,name:file.name,kind:$('add-kind').value});await save(next);render();e.target.value='';notice('PDF를 추가했습니다. 원본 목록에서 선택해 추출하세요.');});
  $('export').onclick=()=>action(async()=>{const selected=new Set(Array.from(document.querySelectorAll('[data-export]:checked'),e=>e.dataset.export));const items=clone(book.items.filter(q=>q.status==='ready'&&selected.has(q.id)));if(!items.length)throw Error('사용 가능 문항이 없습니다. 문항을 검수·확정하세요.');if(items.length>100)throw Error('첫 단계 출력은 100문항까지 지원합니다.');SourceWorker.supports(await SourceWorker.call('/health'));notice('출력할 문항과 그림을 준비하고 있습니다.');
    for(const q of items)for(const field of ['figure_images','solution_images'])for(let i=0;i<(q[field]||[]).length;i++){
      if(q[field][i].startsWith('data:'))continue;
      const response=await fetch(await signed(q[field][i]));if(!response.ok)throw Error('출력 그림을 읽지 못했습니다.');
      q[field][i]='data:image/png;base64,'+await b64(await response.blob());
    }
    const job=await SourceWorker.call('/jobs?kind=source',{method:'POST',body:JSON.stringify({operation:'export',title:book.title,items})});const result=await poll(job);if(!result.hwpx)throw Error('한글 출력 결과 오류');const bytes=Uint8Array.from(atob(result.hwpx),c=>c.charCodeAt(0));download(new Blob([bytes],{type:'application/hwp+zip'}),filename(book.title)+'-검수원문.hwpx');notice('본문·수식 편집 가능한 HWPX를 내려받았습니다. 한글에서 배치와 수식을 최종 확인하세요.');});
  window.addEventListener('beforeunload',e=>{if(busy){e.preventDefault();e.returnValue='';}});
  (async()=>{try{const id=localStorage.getItem('savedUserId');if(!id)throw Error('BMAPS에서 관리자 로그인 후 다시 열어주세요.');const r=await db.from('users').select('id,name,role,branch_id,status').eq('id',id).single();if(r.error)throw r.error;user=r.data;assertAdmin();if(user.status!=='active')throw Error('활성 관리자 계정이 필요합니다.');$('who').textContent=user.name+' · 관리자';await list();$('gate').hidden=true;$('app').hidden=false;}catch(e){$('gate').textContent=e.message;}})();
})();
