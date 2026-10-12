/* Optional, paired local Codex workflow. Existing server analysis remains available. */
(function () {
  'use strict';
  var base = 'http://127.0.0.1:8765', draft = null, running = false;
  var $ = function (id) { return document.getElementById(id); };
  var originalRender = koRender, originalReset = koReset, originalSetFile = koSetFile;
  function token() { return $('ko-codex-token').value.trim(); }
  async function call(path, options) {
    var controller = new AbortController(), timer = setTimeout(function () { controller.abort(); }, 20000);
    try {
      var opts = Object.assign({}, options || {});
      opts.headers = Object.assign({}, opts.headers || {}, { Authorization: 'Bearer ' + token() });
      opts.signal = controller.signal;
      var response = await fetch(base + path, opts), body = await response.json();
      if (!response.ok) throw new Error(body.error || ('HTTP ' + response.status));
      return body;
    } finally { clearTimeout(timer); }
  }
  function message(error) {
    return error instanceof TypeError || error.name === 'AbortError'
      ? '로컬 Codex 연결 실패. 처리 프로그램·연결 코드·브라우저 로컬 네트워크 허용을 확인하세요.' : error.message;
  }
  function busy(on) {
    running = on; _ko.busy = on;
    ['ko-run', 'ko-codex-run', 'ko-codex-resume', 'ko-scope', 'ko-from', 'ko-to'].forEach(function (id) { $(id).disabled = on; });
    if (!on) koScope();
  }
  function regionHtml(regions) {
    return (regions || []).map(function (r) {
      if (!/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(r.image || '')) throw new Error('원본 이미지 형식 오류');
      return '<div class="ko-fig"><img style="width:100%" src="' + r.image + '" alt="원본 영역"><div class="cap">원본 ' + Number(r.page) + '쪽</div></div>';
    }).join('');
  }
  koRender = function () {
    if (!draft || _ko.sets !== draft.sets) return originalRender();
    var reviews = draft.codexReview || [], issues = [].concat.apply([], reviews.map(function (r) { return r.issues || []; }));
    $('ko-result').innerHTML = '<div class="ko-warn"><b>Codex 검토가 포함된 등록 초안 · 학생에게 배포되지 않았습니다.</b><br>'
      + reviews.map(function (r) { return koEsc(r.pages.join(', ') + '쪽: ' + r.summary); }).join('<br>')
      + (issues.length ? '<br><b>확인 필요</b><br>' + issues.map(koEsc).join('<br>') : '<br>자동 검토에서 보고된 문제 없음 · 등록 전 원본을 확인하세요.')
      + '<br><button class="btn" onclick="koCodexDownload()">등록 초안 내려받기</button></div>'
      + draft.sets.map(function (s) {
        return '<div class="ko-set' + (!s.sourceRegions.length ? ' solo' : '') + '"><div class="ko-set-h"><span class="tag">' + koEsc(s.range) + '번</span><span>' + koEsc(s.area) + '</span></div><div class="ko-cols"><div class="ko-body">' + regionHtml(s.sourceRegions) + '</div><div class="ko-qs">'
          + s.qs.map(function (q) { return '<div class="ko-q">' + regionHtml(q.sourceRegions) + '</div>'; }).join('') + '</div></div></div>';
      }).join('');
  };
  koReset = function () { if (running || _ko.busy) return; draft = null; originalReset(); };
  koSetFile = function (file) { if (running || _ko.busy) return; draft = null; _ko.sets = []; $('ko-result').replaceChildren(); originalSetFile(file); };
  window.koCodexCheck = async function () {
    try { await call('/health'); koMsg('로컬 Codex 처리 프로그램 연결됨'); }
    catch (e) { koMsg(message(e), true); }
  };
  async function poll(id) {
    for (var count = 0; count < 1800; count++) {
      var job = await call('/jobs/' + encodeURIComponent(id));
      koMsg(job.message);
      if (job.status === 'failed') throw new Error(job.message);
      if (job.status === 'complete') {
        if (!job.result || !Array.isArray(job.result.sets) || !Array.isArray(job.result.codexReview)) throw new Error('결과 형식 오류');
        draft = job.result; _ko.sets = draft.sets; _ko.imgs = []; koRender();
        sessionStorage.removeItem('ko-codex-job'); return;
      }
      await new Promise(function (resolve) { setTimeout(resolve, 2000); });
    }
    throw new Error('대기 시간이 길어졌습니다. 결과 다시 받기로 이어서 확인하세요.');
  }
  window.koCodexRun = async function (resume) {
    if (running || _ko.busy) return;
    if (!token()) { koMsg('Codex 연결 설정에 연결 코드를 입력하세요.', true); return; }
    if (!resume && !_ko.file) { koMsg('국어 문제지 PDF를 선택하세요.', true); return; }
    busy(true);
    try {
      await call('/health');
      var id = resume ? sessionStorage.getItem('ko-codex-job') : null;
      if (resume && !id) throw new Error('이어받을 작업이 없습니다.');
      if (!resume) {
        if (_ko.file.size > 30 * 1024 * 1024) throw new Error('30MB 이하 PDF를 사용하세요.');
        var job = await call('/jobs?from=' + encodeURIComponent($('ko-from').value) + '&to=' + encodeURIComponent($('ko-to').value), { method:'POST', headers:{'Content-Type':'application/pdf'}, body:_ko.file });
        id = job.id; sessionStorage.setItem('ko-codex-job', id);
      }
      await poll(id);
    } catch (e) { koMsg(message(e), true); }
    finally { busy(false); }
  };
  window.koCodexDownload = function () {
    if (!draft) return;
    var url = URL.createObjectURL(new Blob([JSON.stringify(draft)], {type:'application/json'})), a = document.createElement('a');
    a.href = url; a.download = 'BMAPS-korean-draft.json'; a.click(); setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  };
  $('ko-codex-origin').textContent = location.origin;
})();
