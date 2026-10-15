/* Exam analysis: paired local Codex jobs, existing review/save remains explicit. */
(function () {
  'use strict';
  const base = 'http://127.0.0.1:8765', $ = id => document.getElementById(id);
  let popup = null, token = '', direct = false, relay = false, hello = null;
  const pending = new Map();
  let unfinished = null;
  const toolbar = document.createElement('div'); toolbar.style.cssText='font-size:12px;margin-bottom:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap';
  toolbar.innerHTML='<button type="button" id="eac-connect">Codex 연결</button><span id="eac-status">연결 안 됨</span><span id="eac-message" role="status"></span>';
  $('eam-body').before(toolbar);
  function message(text) { $('eac-message').textContent = text; }
  function disconnected() { token = ''; direct = relay = false; $('eac-status').textContent = '연결 안 됨'; }
  async function directCall(path, options) {
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 30000);
    try {
      const response = await fetch(base + path, Object.assign({}, options, {
        headers: {Authorization:'Bearer ' + token, 'Content-Type':'application/json'}, signal:ctl.signal
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
    if (!health.capabilities || !health.capabilities.includes('exam')) throw Error('내신분석 지원 처리기(v5)로 업데이트한 뒤 다시 연결하세요.');
  }
  $('eac-connect').onclick = function () {
    if (direct) {call('/health').then(h => {supports(h);message('백그라운드 연결 정상');}).catch(e => {disconnected();message(e.message);});return;}
    if (popup && !popup.closed) {popup.focus();popup.postMessage({type:'bmaps-connect'}, base);return;}
    popup = window.open(base + '/connect', '_blank', 'popup,width=650,height=650');
    if (!popup) {message('팝업을 허용하고 다시 연결하세요.');return;}
    clearInterval(hello); let tries = 0;
    $('eac-status').textContent = '승인 대기 중';
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
      $('eac-status').textContent = direct ? 'Codex 연결됨 · 창 닫기 가능' : 'Codex 연결됨 · 연결 창 유지';
      message('분석 시작 또는 총평 생성을 누르세요.');
    } catch (err) {disconnected();message(err.message);}
  });
  // The existing three stages supply their prompt and allowed units; never call Gemini.
  window.eaCallCodex = async function(body) {
    const properties=body.generationConfig.responseSchema.properties;
    const operation=properties.items?'analysis':properties.units?'range':'summary';
    const parts=body.contents[0].parts;
    const request={operation,prompt:parts.filter(p=>typeof p.text==='string').map(p=>p.text).join('\n'),
      units:operation==='analysis'?properties.items.items.properties.unit.enum:operation==='range'?properties.units.items.properties.name.enum:[],
      pdf:(parts.find(p=>p.inlineData)||{}).inlineData?.data||''};
    supports(await call('/health'));
    const owner=_eaMake;
    const encoded=JSON.stringify(request);
    const signature=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(encoded)))).join('-');
    const job=unfinished?.owner===owner && unfinished.signature===signature ? unfinished : await call('/jobs?kind=exam',{method:'POST',body:encoded});
    unfinished={id:job.id,owner,signature};
    for(let n=0;n<1800;n++){
      const state=await call('/jobs/'+encodeURIComponent(job.id));
      message(state.message||'Codex 분석 중…');
      if(state.status==='failed'){unfinished=null;throw Error(state.message);}
      if(state.status==='complete'){
        if(_eaMake!==owner)throw Error('분석 화면이 변경되었습니다. 다시 분석하세요.');
        const result=state.result;
        if(result?.kind!=='exam'||result.operation!==operation||!result.output)throw Error('내신 분석 결과 형식 오류');
        if(operation==='analysis')owner.audit=result.output.audit;
        unfinished=null;
        return result.output;
      }
      await new Promise(r=>setTimeout(r,2000));
    }
    throw Error('분석 대기 시간이 초과됐습니다. 로컬 작업 로그를 확인하세요.');
  };
  window.eaAuditValidate = function(items, hard, soft) {
    const labels=new Set(), orders=new Set();
    items.forEach(item=>{
      if(!String(item.number_label||'').trim() || labels.has(item.number_label))hard.push('문항 번호 누락/중복: '+(item.number_label||'(빈 번호)'));
      if(!Number.isInteger(Number(item.order)) || Number(item.order)<1 || orders.has(Number(item.order)))hard.push('문항 순번 오류: '+item.order);
      if(!Number.isFinite(Number(item.score)) || Number(item.score)<0)hard.push('배점 오류: '+item.number_label);
      if(![1,2,3].includes(Number(item.difficulty)))hard.push('난이도 오류: '+item.number_label);
      labels.add(item.number_label);orders.add(Number(item.order));
    });
    const audit=_eaMake?.audit;
    if(!audit)return;
    if(!Array.isArray(audit.questions) || !Array.isArray(audit.issues)){hard.push('원본 대조표 형식 오류');return;}
    if(audit.questions.length!==items.length)hard.push('원본 대조 '+audit.questions.length+'문항 / 현재 표 '+items.length+'문항');
    const original=new Set();
    audit.questions.forEach(q=>{
      if(original.has(q.number_label))hard.push('원본 대조표 번호 중복: '+q.number_label);
      original.add(q.number_label);
      const item=items.find(x=>x.number_label===q.number_label);
      if(!item)hard.push('원본 대조 문항 누락: '+q.number_label+' ('+q.page+'쪽)');
      else if(q.score==null)soft.push(q.number_label+' 원본 배점 판독 불확실 — 원본 확인 필요');
      else if(Math.abs(Number(item.score)-q.score)>0.01)hard.push(q.number_label+' 배점 불일치: 원본 대조 '+q.score+' / 표 '+item.score);
    });
    items.filter(x=>!original.has(x.number_label)).forEach(x=>hard.push('원본 대조표에 없는 문항: '+x.number_label));
    audit.issues.forEach(issue=>soft.push('원본 확인: '+String(issue)));
  };
  const renderReview=eaRenderReview;
  eaRenderReview=function(){
    renderReview.apply(this,arguments);
    if(!_eaMake?.audit)return;
    const details=document.createElement('details');details.style.cssText='font-size:12px;padding:10px;border:1px solid #ddd6fe;margin-bottom:10px';
    const title=document.createElement('summary');title.textContent='Codex 원본 대조표 · 문항 번호·배점·페이지 확인';details.append(title);
    const content=document.createElement('div');content.style.whiteSpace='pre-wrap';
    content.textContent=_eaMake.audit.questions.map(q=>q.number_label+' · '+q.page+'쪽 · '+(q.score==null?'배점 확인 필요':q.score+'점')).join('\n');
    details.append(content);$('eam-warn').after(details);
  };
  // A summary must describe the reviewed table, not a table edited during generation.
  const analyze=eaAnalyze;
  eaAnalyze=async function(){
    if(_eaMake?.busy)return;
    const controls=Array.from($('eam-body').querySelectorAll('button,input,select,textarea'));
    const disabled=controls.map(el=>el.disabled);
    try{controls.forEach(el=>el.disabled=true);await analyze();}
    finally{controls.forEach((el,i)=>el.disabled=disabled[i]);}
  };
  const close=closeModal;
  closeModal=function(id){if(id==='eaMake' && _eaMake?.busy)return;return close.apply(this,arguments);};
  const summary=eaGenSummary;
  eaGenSummary=async function(){
    const controls=Array.from($('eam-body').querySelectorAll('button,input,select,textarea'));
    const disabled=controls.map(el=>el.disabled);
    if(_eaMake?.busy)return;
    try{controls.forEach(el=>el.disabled=true);await summary();}
    finally{controls.forEach((el,i)=>el.disabled=disabled[i]);}
  };
})();
