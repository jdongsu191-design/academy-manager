/* Exam analysis: paired local Codex jobs, existing review/save remains explicit. */
(function () {
  'use strict';
  const base = 'http://127.0.0.1:8765', $ = id => document.getElementById(id);
  let popup = null, token = '', direct = false, relay = false, hello = null;
  const pending = new Map();
  let unfinished = null;
  const toolbar = document.createElement('div'); toolbar.style.cssText='font-size:12px;margin-bottom:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap';
  toolbar.innerHTML='<button type="button" id="eac-connect">Codex 연결</button><span id="eac-status">연결 안 됨</span><span id="eac-message" role="status"></span>';
  $('connection').append(toolbar);
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
    if (!health.capabilities || !health.capabilities.includes('source')) throw Error('원본 교재 지원 처리기(v7)로 업데이트한 뒤 다시 연결하세요.');
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
      message('페이지 범위를 선택하고 원본 추출을 시작하세요.');
    } catch (err) {disconnected();message(err.message);}
  });
  window.SourceWorker = {call, supports};
})();
