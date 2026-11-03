/* N제 extraction adapter. Keep the existing editor, preview and explicit save. */
(function () {
  'use strict';
  const base = 'http://127.0.0.1:8765', $ = id => document.getElementById(id);
  let popup = null, token = '', direct = false, relay = false, hello = null;
  let running = false, file = null, reviewed = false, answerPages = [], issues = [];
  const pending = new Map();
  const legacyLoad = startNajePdfLoad, legacyAnswers = openAssignAnswerModal, legacyReset = resetNajeUpload;
  const toolbar = document.createElement('div'); toolbar.className = 'row'; toolbar.style.marginBottom = '10px';
  toolbar.innerHTML = '<select class="inp" id="njc-engine" aria-label="PDF 분석 도구"><option value="codex">Codex 분석</option><option value="legacy">기존 분석</option></select>'
    + '<button class="btn btn-sm" id="njc-connect">Codex 연결</button><span class="hint" id="njc-status">연결 안 됨</span>'
    + '<button class="btn btn-sm" id="njc-retry">분석 다시 실행</button><button class="btn btn-sm" id="njc-resume">결과 다시 받기</button>'
    + '<span class="hint" id="njc-message" role="status"></span>';
  $('admin-naje-panel-upload').before(toolbar);
  function message(text) { $('njc-message').textContent = text; }
  function disconnected() { token = ''; direct = relay = false; $('njc-status').textContent = '연결 안 됨'; }
  async function directCall(path, options) {
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 30000);
    try {
      const response = await fetch(base + path, Object.assign({}, options, {
        headers: {Authorization:'Bearer ' + token, 'Content-Type':'application/pdf'}, signal:ctl.signal
      }));
      const data = await response.json(); if (!response.ok) throw Error(data.error || '로컬 처리기 오류'); return data;
    } finally { clearTimeout(timer); }
  }
  async function call(path, options = {}) {
    if (direct) return directCall(path, options);
    if (!relay || !popup || popup.closed) throw Error('Codex 연결을 먼저 허용하세요.');
    return new Promise((resolve, reject) => {
      const id = crypto.randomUUID(), timer = setTimeout(() => {pending.delete(id);reject(Error('연결 창 응답이 없습니다.'));}, 40000);
      pending.set(id, {resolve, reject, timer});
      popup.postMessage({type:'bmaps-request', id, path, method:options.method || 'GET', body:options.body}, base);
    });
  }
  function supports(health) {
    if (!health.capabilities || !health.capabilities.includes('naje')) throw Error('N제 지원 처리기로 업데이트한 뒤 다시 연결하세요.');
  }
  $('njc-connect').onclick = function () {
    if (direct) {call('/health').then(h => {supports(h);message('백그라운드 연결 정상');}).catch(e => {disconnected();message(e.message);});return;}
    if (popup && !popup.closed) {popup.focus();popup.postMessage({type:'bmaps-connect'}, base);return;}
    popup = window.open(base + '/connect', '_blank', 'popup,width=650,height=650');
    if (!popup) {message('팝업을 허용하고 다시 연결하세요.');return;}
    clearInterval(hello); let tries = 0;
    $('njc-status').textContent = '승인 대기 중';
    hello = setInterval(() => {
      if (!popup || popup.closed || ++tries > 120) {clearInterval(hello);if(!direct){disconnected();message('연결 창과 처리 프로그램을 확인하세요.');}return;}
      popup.postMessage({type:'bmaps-connect'}, base);
    }, 500);
  };
  addEventListener('message', async e => {
    if (e.origin !== base || e.source !== popup || !e.data) return;
    const m = e.data;
    if (m.type === 'bmaps-response' && pending.has(m.id)) {
      const p = pending.get(m.id); pending.delete(m.id); clearTimeout(p.timer);
      if (m.error) p.reject(Error(m.error)); else p.resolve(m.value); return;
    }
    if (m.type === 'bmaps-disconnected') {disconnected();message('연결이 해제됐습니다.');return;}
    if (m.type !== 'bmaps-ready' || typeof m.token !== 'string' || !/^[\w-]{40,100}$/.test(m.token)) return;
    clearInterval(hello);token = m.token;relay = true;
    try {
      let health;
      try {health = await directCall('/health'); direct = true;}
      catch (_) {direct = false; health = await call('/health');}
      supports(health);
      popup.postMessage({type:'bmaps-ack', direct}, base);
      $('njc-status').textContent = direct ? 'Codex 연결됨 · 창 닫기 가능' : 'Codex 연결됨 · 연결 창 유지';
      message(file ? '분석 다시 실행을 누르세요.' : 'PDF를 올리면 Codex로 분석합니다.');
    } catch (err) {disconnected();message(err.message);}
  });
  // Prevent switching the target while a document is being analyzed or applied.
  ['njeOpenSet','njeOnGradeChange','njeOpenSetModal','njeDeleteSet','njeNewFolder'].forEach(name => {
    const fn = window[name]; window[name] = function () {if(running || _nj.busy){message('현재 작업이 끝난 뒤 변경하세요.');return;}return fn.apply(this, arguments);};
  });
  function busy(on) {
    running = on;_nj.busy = on;
    ['njc-engine','njc-retry','njc-resume','nje-grade','nje-folder','admin-naje-pdf-input','admin-naje-save-btn'].forEach(id => {if($(id))$(id).disabled = on;});
  }
  function clearDraft() {reviewed = false;answerPages = [];issues = [];najeExtractedProblems = [];najeAnswerMap = {};najeQuickAnswerDataUrl = null;window._pendingAnswerMap = null;sessionStorage.removeItem('najeQuickAnswerDataUrl');if($('modal-assign-answer'))$('modal-assign-answer').remove();}
  resetNajeUpload = function (mode) {if(running)return;clearDraft();file = null;return legacyReset(mode);};
  function accept(result) {
    if (!result || result.kind !== 'naje' || !Array.isArray(result.problems) || !result.problems.length || !result.answers || !Array.isArray(result.issues)) throw Error('N제 결과 형식 오류');
    const seen = new Set();
    const problems = result.problems.map(p => {
      if(!Number.isInteger(p.number) || p.number<1 || p.number>9999 || seen.has(p.number) || !/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(p.dataUrl)) throw Error('문항 번호/이미지 오류');
      if(p.qrUrl && !/^https?:\/\//.test(p.qrUrl)) throw Error('QR 주소 오류');
      seen.add(p.number);const level=getLevelInfoByNum(p.number);
      return Object.assign({}, p, {level_name:level.name,level_type:level.type,step:level.step});
    });
    const answers = {};
    Object.entries(result.answers).forEach(([n,a]) => {if(!/^\d+$/.test(n) || typeof a !== 'string' || a.length>300) throw Error('정답 형식 오류');if(seen.has(+n))answers[n]=a;});
    problems.forEach(p=>{if(!(p.number in answers))answers[p.number]='';});
    answerPages = result.answerPages || [];
    if(!answerPages.every(s => /^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(s))) throw Error('정답 원본 이미지 오류');
    najeExtractedProblems = problems;najeAnswerMap = answers;najeQuickAnswerDataUrl = answerPages[0] || null;
    issues = result.issues;reviewed = true;
    $('admin-naje-step1').style.display = 'none';$('admin-naje-step2').style.display = 'none';$('admin-naje-step3').style.display = 'block';
    showNajePreview(problems, 0);
    message('Codex 분석 완료 · '+problems.length+'문항 · 확인 필요 '+issues.length+'건. 원본 대조 후 N제에 적용하세요.');
  }
  const preview = showNajePreview;
  showNajePreview = function () {
    preview.apply(this, arguments);
    if(reviewed && issues.length){const box=document.createElement('div');box.className='chk-li warn';box.style.whiteSpace='pre-wrap';box.textContent=issues.join('\n');$('nje-check').append(box);}
  };
  async function analyze(resume) {
    if(running || _nj.busy)return;
    if(!_nj.set){message('N제를 먼저 선택하세요.');return;}
    const target = _nj.set.id;
    let saved;
    try {saved=JSON.parse(sessionStorage.getItem('naje-codex-job') || 'null');} catch (_) {}
    if(resume && (!saved || saved.setId!==target)){message('이 N제에 이어받을 작업이 없습니다.');return;}
    if(!resume && !file){message('PDF를 먼저 선택하세요.');return;}
    busy(true);
    try {
      supports(await call('/health'));
      clearDraft();$('admin-naje-step1').style.display='none';$('admin-naje-step3').style.display='none';$('admin-naje-step2').style.display='block';
      let id = resume ? saved.id : null;
      if(!resume){const job=await call('/jobs?kind=naje',{method:'POST',body:file});id=job.id;sessionStorage.setItem('naje-codex-job',JSON.stringify({id,setId:target}));}
      for(let n=0;n<3600;n++){
        const job=await call('/jobs/'+encodeURIComponent(id));
        $('admin-naje-progress-text').textContent=job.message || '분석 중…';message(job.message || '분석 중…');
        const progress=String(job.message||'').match(/(\d+)~(\d+) \/ (\d+)쪽/);
        if(progress)$('admin-naje-progress-bar').style.width=Math.round(90*Number(progress[2])/Number(progress[3]))+'%';
        if(job.status==='failed')throw Error(job.message);
        if(job.status==='complete'){
          if(!_nj.set || _nj.set.id!==target)throw Error('선택한 N제가 달라졌습니다. 원래 N제를 선택하고 결과 다시 받기를 누르세요.');
          accept(job.result);sessionStorage.removeItem('naje-codex-job');return;
        }
        await new Promise(r => setTimeout(r,2000));
      }
      throw Error('분석 대기 시간이 길어졌습니다. 결과 다시 받기로 이어서 확인하세요.');
    } catch(e){
      message(e.name==='AbortError'||e instanceof TypeError ? '로컬 연결 실패. 처리 프로그램과 브라우저 로컬 네트워크 권한을 확인하세요.' : e.message);
      $('admin-naje-step2').style.display='none';$('admin-naje-step1').style.display='block';
    } finally {busy(false);}
  }
  startNajePdfLoad = async function (selected, mode) {
    if(running || _nj.busy)return;
    if($('njc-engine').value==='legacy'){clearDraft();return legacyLoad(selected,mode);}
    if(!selected || !/\.pdf$/i.test(selected.name) || selected.size>30*1024*1024){message('30MB 이하 PDF를 선택하세요.');return;}
    _najeMode='admin';clearDraft();file=selected;await analyze(false);
  };
  $('njc-retry').onclick = () => analyze(false);
  $('njc-resume').onclick = () => analyze(true);
  const apply = njeApply;
  njeApply = function () {
    if(reviewed && $('nje-o-ans').checked){
      const missing=najeExtractedProblems.filter(p=>!najeAnswerMap[p.number]);
      if(missing.length){message('정답 확인에서 '+missing.map(p=>p.number).join(', ')+'번 답을 입력하거나 정답 적용을 해제하세요. 이전 정답을 자동으로 재사용하지 않습니다.');return;}
    }
    return apply.apply(this,arguments);
  };
  openAssignAnswerModal = function (mode) {
    if(!reviewed){if($('njc-engine').value==='legacy')return legacyAnswers(mode);message('PDF를 Codex로 분석한 뒤 정답을 확인하세요.');return;}
    // Keep the existing answer review/edit modal, without a second Gemini call.
    const old=$('modal-assign-answer');if(old)old.remove();
    const modal=document.createElement('div');modal.id='modal-assign-answer';modal.className='modal-backdrop open';
    modal.innerHTML='<div class="modal" style="max-width:920px;width:96vw;max-height:92vh;overflow:auto"><h3>문항별 정답 확인 · Codex</h3><div id="assign-answer-body"></div><div class="row"><button class="btn" id="njc-answer-close">닫기</button><button class="btn btn-primary" onclick="applyAnswerMap()">정답 부여</button></div></div>';
    document.body.append(modal);window._pendingAnswerMap=Object.assign({},najeAnswerMap);renderAssignAnswerSections(window._pendingAnswerMap);
    $('njc-answer-close').onclick=()=>modal.remove();
    answerPages.forEach((src,i)=>{const b=document.createElement('button');b.className='btn btn-sm';b.textContent='정답 원본 '+(i+1);b.onclick=()=>openImgViewer(src);$('assign-answer-body').prepend(b);});
  };
})();
