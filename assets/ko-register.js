/* ═══════════════════════════════════════════════════════════════════════
   국어 모의고사 — 시험지 등록 (베티모의고사와 같은 흐름)
     1️⃣ 회차(weekend_sessions program='korean') → 2️⃣ 시험지(학교급·학년·선택과목·제한시간·발행)
     → 3️⃣ 세팅: [PDF 가져오기(Codex)] [정답·배점] [응시 현황]
   읽기는 ko-codex.js(로컬 Codex 워커)가 하고, 여기서는 그 결과(원본 영역 이미지)를
   시험지에 '적용' 한다: 지문·문항 이미지를 합쳐 Storage 에 올리고 정답·배점과 함께 RPC 로 저장.
   ⚠ 학생을 고르지 않는다 — 베티처럼 bety_yn 학생 중 학교급·학년이 맞으면 자동 대상(서버 ko_eligible).
   의존: bety-admin.html 의 db·_ba(관리자)·_ko·koMsg·koRender / ko-codex.js 의 koGetDraft / ko-exam-core.js
   ═══════════════════════════════════════════════════════════════════ */
(function(){
'use strict';
var KA = { BUCKET:'bety-exam', DIR:'ko-published', GAP:10 };
var _ka = { date:'', sessions:[], exams:[], exam:null, sets:[], keys:{}, tab:'p',
            answerRows:[], rows:[], draftSets:null, busy:false };
window._ka = _ka;

var $ = function(id){ return document.getElementById(id); };
var esc = function(v){ return String(v==null?'':v).replace(/[&<>"']/g, function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
function msg(id, t, bad){ var el=$(id); if(!el) return; el.textContent=t||''; el.classList.toggle('err', !!bad); }
function actor(){ return window._ba && _ba.user ? _ba.user.id : null; }
async function rpc(name, args){
  var r = await db.rpc(name, args);
  if(r.error) throw new Error(r.error.message || String(r.error));
  if(r.data && r.data.error) throw new Error(r.data.error);
  return r.data;
}
function imgUrl(path){ return SUPABASE_URL + '/storage/v1/object/public/' + KA.BUCKET + '/' + path; }
function examName(e){
  var sl = e.school_level==='high' ? '고등 ' : e.school_level==='middle' ? '중등 ' : '';
  return sl + (e.grade==null ? '전학년' : e.grade + '학년') + ' · ' + e.elective;
}

/* ── 1️⃣ 회차 ───────────────────────────────────────────── */
window.kaLoadSessions = async function(){
  try {
    var r = await db.from('weekend_sessions').select('*').eq('program','korean');
    if(r.error) throw r.error;
    _ka.sessions = (r.data||[]).slice().sort(function(a,b){ return String(b.session_date).localeCompare(String(a.session_date)); });
    var sel = $('ka-session');
    sel.innerHTML = '<option value="">회차를 선택하세요</option>' + _ka.sessions.map(function(s){
      return '<option value="'+esc(s.session_date)+'">'+esc(s.session_date + (s.round_no ? ('  ·  '+s.round_no+'회차') : '') + (s.is_closed ? '  (휴강)' : ''))+'</option>';
    }).join('');
    if(_ka.date) sel.value = _ka.date;
  } catch(e){ console.error('[국어 회차]', e); }
};
window.kaOnSessionPick = function(){
  var v = $('ka-session').value;
  if(v){ $('ka-date').value = v; kaLoadExams(); }
};
window.kaOpenSession = function(){
  msg('ka-ss-msg',''); $('ka-ss-date').value = ''; $('ka-ss-round').value = '';
  var last = _ka.sessions.find(function(s){ return s.round_no != null; });
  if(last) $('ka-ss-round').value = String(last.round_no + 1);
  $('ka-ss-ov').classList.add('open');
};
window.kaCloseSession = function(){ $('ka-ss-ov').classList.remove('open'); };
window.kaSaveSession = async function(){
  var date = $('ka-ss-date').value, round = parseInt($('ka-ss-round').value, 10);
  if(!date){ msg('ka-ss-msg','날짜를 입력하세요', true); return; }
  try {
    /* UNIQUE 가 (program, session_date, …) 이라 index.html 회차 관리와 같이 먼저 찾아본다 */
    var ex = await db.from('weekend_sessions').select('id').eq('program','korean').eq('session_date', date);
    if(ex.error) throw ex.error;
    var payload = { program:'korean', session_date:date, round_no:isNaN(round) ? null : round, is_closed:false };
    var w = (ex.data && ex.data.length)
      ? await db.from('weekend_sessions').update(payload).eq('id', ex.data[0].id)
      : await db.from('weekend_sessions').insert(payload);
    if(w.error) throw w.error;
    kaCloseSession();
    _ka.date = date;
    await kaLoadSessions();
    $('ka-date').value = date;
    await kaLoadExams();
  } catch(e){ msg('ka-ss-msg','저장 실패: ' + (e.message||e), true); }
};

/* ── 2️⃣ 시험지 목록 ───────────────────────────────────── */
window.kaLoadExams = async function(){
  var date = $('ka-date').value, box = $('ka-exams');
  if(!date){ box.innerHTML = '<div class="empty">회차를 먼저 선택해주세요</div>'; return; }
  _ka.date = date;
  box.innerHTML = '<div class="empty">불러오는 중...</div>';
  try {
    _ka.exams = await rpc('ko_exam_list', { p_actor_id:actor(), p_session_date:date }) || [];
    kaRenderExams();
    if(_ka.exam){
      var cur = _ka.exams.find(function(x){ return x.id === _ka.exam.id; });
      if(cur){ _ka.exam = cur; kaRenderBadge(); } else { _ka.exam = null; $('ka-editor').style.display = 'none'; }
    }
  } catch(e){ box.innerHTML = '<div class="empty" style="color:#dc2626">불러오기 실패: '+esc(e.message||e)+'</div>'; }
};
function kaRenderExams(){
  var box = $('ka-exams');
  if(!_ka.exams.length){
    box.innerHTML = '<div class="empty">이 회차에 등록된 국어 시험지가 없습니다. [+ 시험지 추가]를 눌러주세요</div>';
    $('ka-editor').style.display = 'none'; return;
  }
  box.innerHTML = '<div class="ex-grid">' + _ka.exams.map(function(e){
    var badge = e.published ? '<span class="ex-badge bg-pub">발행</span>' : '<span class="ex-badge bg-draft">미발행</span>';
    var warn = e.question_count ? '' : ' <span class="ex-badge bg-warn">문항 없음</span>';
    return '<div class="ex-card '+(_ka.exam && _ka.exam.id===e.id ? 'on' : '')+'" onclick="kaOpenExam(\''+e.id+'\')">'
      + '<div class="ex-name">📖 '+esc(examName(e))+'</div>'
      + '<div class="ex-meta">'+badge+warn+'</div>'
      + '<div class="ex-meta">문항 '+e.question_count+' · 만점 '+e.total_score+' · '+e.duration_min+'분</div>'
      + '<div class="ex-meta">응시 '+e.submit_cnt+'명'+(e.in_progress_cnt ? ' · 진행 중 '+e.in_progress_cnt : '')+'</div>'
      + '</div>';
  }).join('') + '</div>';
}
window.kaOpenExamModal = function(exam){
  if(!_ka.date){ alert('회차를 먼저 선택해주세요'); return; }
  msg('ka-ex-msg','');
  $('ka-ex-title').textContent = exam ? '시험지 정보 수정' : '국어 시험지 추가';
  $('ka-ex-slevel').value   = exam ? (exam.school_level || '') : 'high';
  $('ka-ex-grade').value    = exam ? (exam.grade==null ? '' : String(exam.grade)) : '';
  $('ka-ex-elective').value = exam ? exam.elective : '화법과 작문';
  $('ka-ex-tmin').value     = exam ? exam.duration_min : 80;
  $('ka-ex-name').value     = exam ? (exam.title || '') : '';
  $('ka-ex-pub').value      = exam && exam.published ? 'true' : 'false';
  _ka.editing = exam ? exam.id : null;
  $('ka-ex-ov').classList.add('open');
};
window.kaCloseExamModal = function(){ $('ka-ex-ov').classList.remove('open'); };
window.kaSaveExam = async function(){
  var sl = $('ka-ex-slevel').value, g = $('ka-ex-grade').value, el = $('ka-ex-elective').value;
  var tmin = parseInt($('ka-ex-tmin').value, 10), title = $('ka-ex-name').value.trim(), pub = $('ka-ex-pub').value === 'true';
  if(!tmin || tmin < 1 || tmin > 240){ msg('ka-ex-msg','제한시간은 1~240분', true); return; }
  var btn = $('ka-ex-save'); btn.disabled = true; btn.textContent = '저장중...';
  try {
    var id = await rpc('ko_exam_upsert', { p_actor_id:actor(), p_exam_id:_ka.editing || null,
      p_session_date:_ka.date, p_school_level:sl || null, p_grade:g === '' ? null : parseInt(g,10),
      p_elective:el, p_duration_min:tmin, p_title:title || null, p_published:pub, p_opens_at:null });
    kaCloseExamModal();
    await kaLoadExams();
    await kaOpenExam(id);
  } catch(e){ msg('ka-ex-msg','저장 실패: ' + (e.message||e), true); }
  finally { btn.disabled = false; btn.textContent = '저장'; }
};
window.kaDeleteExam = async function(){
  if(!_ka.exam) return;
  var e = _ka.exam;
  if(!confirm(examName(e) + ' 시험지를 삭제합니다.\n응시 기록 ' + e.submit_cnt + '건도 함께 지워집니다. 계속할까요?')) return;
  try { await rpc('ko_exam_delete', { p_actor_id:actor(), p_exam_id:e.id }); _ka.exam = null; $('ka-editor').style.display = 'none'; await kaLoadExams(); }
  catch(err){ alert('삭제 실패: ' + (err.message||err)); }
};

/* ── 3️⃣ 세팅 ───────────────────────────────────────────── */
window.kaOpenExam = async function(examId){
  var e = _ka.exams.find(function(x){ return x.id === examId; }); if(!e) return;
  _ka.exam = e; kaRenderExams();
  $('ka-editor').style.display = '';
  $('ka-editor-title').textContent = '📖 ' + examName(e) + ' 세팅';
  kaRenderBadge();
  try {
    var d = await rpc('ko_exam_get', { p_actor_id:actor(), p_exam_id:examId });
    _ka.sets = (d && d.sets) || []; _ka.keys = (d && d.keys) || {};
  } catch(err){ _ka.sets = []; _ka.keys = {}; alert('시험지 조회 실패: ' + (err.message||err)); }
  kaRenderKeys(); kaRenderApply(); kaHideSaved();
  kaTab(_ka.tab || 'p');
};
function kaRenderBadge(){
  var e = _ka.exam; if(!e) return;
  $('ka-editor-badge').innerHTML = (e.published ? '<span class="ex-badge bg-pub">발행</span>' : '<span class="ex-badge bg-draft">미발행</span>')
    + ' <span class="hint">문항 ' + e.question_count + ' · 만점 ' + e.total_score + ' · ' + e.duration_min + '분 · 응시 ' + e.submit_cnt + '명</span>';
}
window.kaTab = function(t){
  _ka.tab = t;
  ['p','q','s'].forEach(function(k){
    $('ka-tab-'+k).classList.toggle('on', k===t);
    $('ka-pane-'+k).style.display = (k===t) ? '' : 'none';
  });
  if(t === 's') kaLoadSubs();
};

/* ── PDF 가져오기 — Codex 결과 적용 ───────────────────────
   ko-codex.js 가 분석을 마치면 koAcceptAnswers(정답 PDF 결과) → koPrepareExam() 을 부른다. */
window.koInvalidateAnswers = function(){ _ka.rows = []; _ka.draftSets = null; kaRenderApply(); };
window.koAcceptAnswers = function(result){ _ka.answerRows = result && result.rows ? result.rows : []; };
window.koPrepareExam = function(){
  if(!_ka.exam){ koMsg('적용할 시험지를 먼저 고르세요 (2️⃣ 시험지 목록)', true); return; }
  try {
    var draft = window.koGetDraft ? koGetDraft() : null;
    if(!draft) throw new Error('Codex 분석 결과가 없습니다');
    var sets = KoExamCore.selectSets(draft, _ka.exam.elective);
    var map = {};
    _ka.answerRows.filter(function(r){ return r.elective === '공통' || r.elective === _ka.exam.elective; })
                  .forEach(function(r){ map[r.no] = r; });
    _ka.draftSets = sets;
    _ka.rows = [];
    sets.forEach(function(s){ s.qs.forEach(function(q){
      var k = map[q.no] || _ka.keys[q.no] || {};
      _ka.rows.push({ no:q.no, answer:k.answer != null ? String(k.answer) : '', points:k.points || q.pts || 2 });
    }); });
    _ka.rows.sort(function(a,b){ return a.no - b.no; });
    kaRenderApply();
    var missing = _ka.rows.filter(function(r){ return !r.answer; }).length;
    koMsg('✓ 분석 완료 — ' + _ka.rows.length + '문항' + (missing ? ' · 정답 미입력 ' + missing + '개 (아래 표에서 입력)' : '') + ' · [시험지에 적용]을 누르면 저장됩니다');
    $('ka-apply').scrollIntoView({ behavior:'smooth', block:'nearest' });
  } catch(e){ _ka.rows = []; _ka.draftSets = null; kaRenderApply(); koMsg(e.message || String(e), true); }
};
function kaRenderApply(){
  var box = $('ka-apply'); if(!box) return;
  if(!_ka.rows.length){ box.style.display = 'none'; return; }
  box.style.display = '';
  var total = _ka.rows.reduce(function(n,r){ return n + (+r.points||0); }, 0);
  $('ka-apply-sum').textContent = _ka.draftSets.length + '세트 · ' + _ka.rows.length + '문항 · 배점합 ' + total + '점 · ' + _ka.exam.elective;
  $('ka-apply-grid').innerHTML = '<table class="qt"><thead><tr><th>번호</th><th>정답</th><th>배점</th></tr></thead><tbody>'
    + _ka.rows.map(function(r,i){
      return '<tr><td style="text-align:center;font-weight:800">'+r.no+'</td>'
        + '<td><select data-i="'+i+'" data-f="answer" class="inp" style="width:70px">' + ['','1','2','3','4','5'].map(function(v){
            return '<option value="'+v+'"'+(r.answer===v?' selected':'')+'>'+(v ? '①②③④⑤'[v-1] : '—')+'</option>'; }).join('') + '</select></td>'
        + '<td><input data-i="'+i+'" data-f="points" class="inp" type="number" min="1" max="10" value="'+esc(r.points)+'" style="width:64px"></td></tr>';
    }).join('') + '</tbody></table>';
}
document.addEventListener('input', function(e){
  var t = e.target; if(!t || !t.dataset || !t.dataset.f || !t.closest('#ka-apply-grid')) return;
  _ka.rows[+t.dataset.i][t.dataset.f] = t.value;
  var total = _ka.rows.reduce(function(n,r){ return n + (+r.points||0); }, 0);
  $('ka-apply-sum').textContent = _ka.draftSets.length + '세트 · ' + _ka.rows.length + '문항 · 배점합 ' + total + '점 · ' + _ka.exam.elective;
});

/* 원본 영역들을 세로로 한 장에 합친다 (학생 화면은 문항당 이미지 한 장) */
function loadImg(src){ return new Promise(function(res, rej){ var im = new Image(); im.onload = function(){ res(im); }; im.onerror = function(){ rej(new Error('이미지 디코드 실패')); }; im.src = src; }); }
async function compose(regions){
  if(!regions || !regions.length) return null;
  var ims = [];
  for(var i=0;i<regions.length;i++){
    if(!/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(regions[i].image||'')) throw new Error('원본 이미지 형식 오류');
    ims.push(await loadImg(regions[i].image));
  }
  var w = Math.max.apply(null, ims.map(function(i){ return i.naturalWidth; }));
  var h = ims.reduce(function(n,i){ return n + i.naturalHeight; }, 0) + KA.GAP * (ims.length - 1);
  var cv = document.createElement('canvas'); cv.width = w; cv.height = h;
  var cx = cv.getContext('2d'); cx.fillStyle = '#fff'; cx.fillRect(0,0,w,h);
  var y = 0;
  ims.forEach(function(im){ cx.drawImage(im, 0, y); y += im.naturalHeight + KA.GAP; });
  return await new Promise(function(res){ cv.toBlob(res, 'image/png'); });
}
async function upload(path, blob){
  var up = await db.storage.from(KA.BUCKET).upload(path, blob, { contentType:'image/png', upsert:true });
  if(up.error) throw new Error('이미지 업로드 실패: ' + (up.error.message || up.error));
  return path;
}
window.kaApply = async function(){
  if(_ka.busy || !_ka.exam || !_ka.draftSets) return;
  var ex = _ka.exam;
  var keys = {};
  try {
    var total = KoExamCore.validate(_ka.rows.map(function(r){ return { no:r.no, answer:r.answer, points:r.points }; }));
    _ka.rows.forEach(function(r){ keys[r.no] = { answer:String(r.answer), points:+r.points }; });
  } catch(e){ msg('ka-apply-msg', e.message, true); return; }
  if(!confirm(examName(ex) + ' 시험지에 적용합니다.\n\n' + _ka.rows.length + '문항 · ' + total + '점\n'
      + '지문·문항 이미지를 올리고 정답·배점을 저장합니다. 기존 문항은 덮어씁니다.\n계속할까요?')) return;
  _ka.busy = true;
  var btn = $('ka-apply-btn'); btn.disabled = true; btn.textContent = '적용 중...';
  try {
    var n = 0, body = [], steps = _ka.draftSets.reduce(function(c,s){ return c + 1 + s.qs.length; }, 0), done = 0;
    for(var i=0;i<_ka.draftSets.length;i++){
      var s = _ka.draftSets[i], item = { range:s.range, area:s.area, passage:null, questions:[] };
      var pb = await compose(s.sourceRegions);
      if(pb) item.passage = await upload(KA.DIR + '/' + ex.id + '/' + (n++) + '.png', pb);
      done++; koProg(done/steps);
      for(var j=0;j<s.qs.length;j++){
        var q = s.qs[j], qb = await compose(q.sourceRegions);
        if(!qb) throw new Error(q.no + '번 문항 이미지가 없습니다');
        item.questions.push({ no:q.no, points:keys[q.no].points, image:await upload(KA.DIR + '/' + ex.id + '/' + (n++) + '.png', qb) });
        done++; koProg(done/steps);
      }
      body.push(item);
    }
    var r = await rpc('ko_exam_save_body', { p_actor_id:actor(), p_exam_id:ex.id, p_sets:body, p_keys:keys,
                                             p_pdf_name:(window._ko && _ko.file) ? _ko.file.name : null });
    msg('ka-apply-msg', '✓ 적용 완료 — 문항 ' + r.question_count + '개 · 만점 ' + r.total_score + '점 · 이미지 ' + n + '장');
    await kaLoadExams();
    await kaOpenExam(ex.id);
    kaShowSaved();
  } catch(e){ console.error(e); msg('ka-apply-msg', '적용 실패: ' + (e.message||e), true); }
  finally { _ka.busy = false; btn.disabled = false; btn.textContent = '💾 시험지에 적용'; setTimeout(function(){ koProg(null); }, 800); }
};

/* 저장된 지문·문항 이미지 보기 */
window.kaShowSaved = function(){
  var box = $('ka-saved'); box.style.display = '';
  $('ka-saved-hide').style.display = '';
  if(!_ka.sets.length){ box.innerHTML = '<div class="empty">저장된 문항이 없습니다. PDF 를 분석해 적용하세요.</div>'; return; }
  var bust = '?v=' + Date.now();
  box.innerHTML = _ka.sets.map(function(s){
    return '<div class="ko-set"><div class="ko-set-h"><span class="tag">' + esc(s.range) + '번</span><span class="area">' + esc(s.area) + '</span></div>'
      + '<div class="ko-cols' + (s.passage ? '' : ' solo') + '">'
      + '<div class="ko-body">' + (s.passage ? '<img src="' + imgUrl(s.passage) + bust + '" style="width:100%;border:1px solid #e2e8f0">' : '') + '</div>'
      + '<div class="ko-qs">' + s.questions.map(function(q){
          var k = _ka.keys[q.no] || {};
          return '<div class="ko-q"><div class="ko-stem"><span class="no">' + q.no + '번</span><span class="pts">' + q.points + '점</span>'
            + (k.answer ? ' <span class="hint">정답 ' + '①②③④⑤'[k.answer-1] + '</span>' : '') + '</div>'
            + '<img src="' + imgUrl(q.image) + bust + '" style="width:100%;border:1px solid #e2e8f0;margin-top:6px"></div>'; }).join('')
      + '</div></div></div>';
  }).join('');
};
window.kaHideSaved = function(){ $('ka-saved').style.display = 'none'; $('ka-saved').innerHTML = ''; $('ka-saved-hide').style.display = 'none'; };

/* ── 정답 · 배점 탭 ─────────────────────────────────────── */
function kaRenderKeys(){
  var t = $('ka-qt');
  var qs = []; _ka.sets.forEach(function(s){ s.questions.forEach(function(q){ qs.push(q); }); });
  qs.sort(function(a,b){ return a.no - b.no; });
  if(!qs.length){ t.innerHTML = '<tbody><tr><td class="empty">문항이 없습니다. [PDF 가져오기] 에서 분석해 적용하세요.</td></tr></tbody>'; $('ka-sum').textContent = ''; return; }
  t.innerHTML = '<thead><tr><th>번호</th><th>정답</th><th>배점</th></tr></thead><tbody>' + qs.map(function(q){
    var k = _ka.keys[q.no] || {};
    return '<tr><td style="text-align:center;font-weight:800">' + q.no + '</td>'
      + '<td><select class="inp ka-k" data-no="' + q.no + '" data-f="answer" style="width:70px">' + ['','1','2','3','4','5'].map(function(v){
          return '<option value="'+v+'"'+(String(k.answer||'')===v?' selected':'')+'>'+(v ? '①②③④⑤'[v-1] : '—')+'</option>'; }).join('') + '</select></td>'
      + '<td><input class="inp ka-k" data-no="' + q.no + '" data-f="points" type="number" min="1" max="10" value="' + esc(k.points != null ? k.points : q.points) + '" style="width:64px"></td></tr>';
  }).join('') + '</tbody>';
  var total = qs.reduce(function(n,q){ var k=_ka.keys[q.no]||{}; return n + (+(k.points != null ? k.points : q.points)||0); }, 0);
  $('ka-sum').textContent = qs.length + '문항 · 배점합 ' + total + '점';
}
window.kaSaveKeys = async function(){
  if(!_ka.exam) return;
  var keys = {}, rows = [];
  document.querySelectorAll('#ka-qt .ka-k').forEach(function(el){
    var no = +el.dataset.no; keys[no] = keys[no] || {}; keys[no][el.dataset.f] = el.value;
  });
  Object.keys(keys).forEach(function(no){ rows.push({ no:+no, answer:keys[no].answer, points:keys[no].points }); });
  try { KoExamCore.validate(rows); } catch(e){ msg('ka-msg-q', e.message, true); return; }
  var payload = {}; rows.forEach(function(r){ payload[r.no] = { answer:String(r.answer), points:+r.points }; });
  msg('ka-msg-q', '저장중...');
  try {
    var r = await rpc('ko_exam_save_keys', { p_actor_id:actor(), p_exam_id:_ka.exam.id, p_keys:payload });
    _ka.keys = payload;
    msg('ka-msg-q', '✓ 저장 완료 — 만점 ' + r.total_score + '점');
    await kaLoadExams();
  } catch(e){ msg('ka-msg-q', '저장 실패: ' + (e.message||e), true); }
};

/* ── 응시 현황 탭 ───────────────────────────────────────── */
window.kaLoadSubs = async function(){
  if(!_ka.exam) return;
  var t = $('ka-st');
  t.innerHTML = '<tbody><tr><td class="empty">불러오는 중...</td></tr></tbody>';
  try {
    var rows = await rpc('ko_sub_list', { p_actor_id:actor(), p_exam_id:_ka.exam.id }) || [];
    $('ka-sub-sum').textContent = '제출 ' + rows.filter(function(r){ return r.submitted_at; }).length + '명 · 진행 중 ' + rows.filter(function(r){ return !r.submitted_at; }).length + '명';
    if(!rows.length){ t.innerHTML = '<tbody><tr><td class="empty">아직 시작한 학생이 없습니다</td></tr></tbody>'; return; }
    t.innerHTML = '<thead><tr><th>이름</th><th>학교</th><th>학년</th><th>상태</th><th>점수</th><th>맞은 문항</th><th>제출 시각</th><th>이탈</th><th>초기화</th></tr></thead><tbody>'
      + rows.map(function(s){
        var at = s.submitted_at ? String(s.submitted_at).replace('T',' ').slice(0,16) : '';
        var st = s.submitted_at ? (s.auto_submitted ? '자동 제출' : '제출') : '<b style="color:#b91c1c">응시 중</b>';
        return '<tr><td><b>'+esc(s.name)+'</b></td><td>'+esc(s.school||'')+'</td><td>'+esc(s.grade||'')+'</td><td>'+st+'</td>'
          + '<td><b>'+(s.score != null ? s.score : '')+'</b></td><td>'+(s.correct_count != null ? s.correct_count : '')+'</td><td>'+esc(at)+'</td><td>'+(s.away_count||0)+'</td>'
          + '<td><button class="btn btn-sm btn-danger" onclick="kaReset(\''+s.student_id+'\',\''+esc(s.name).replace(/'/g,"\\'")+'\')">초기화</button></td></tr>';
      }).join('') + '</tbody>';
  } catch(e){ t.innerHTML = '<tbody><tr><td class="empty" style="color:#dc2626">불러오기 실패: '+esc(e.message||e)+'</td></tr></tbody>'; }
};
window.kaReset = async function(studentId, name){
  var reason = prompt(name + ' 학생의 응시를 초기화합니다.\n사유를 입력하세요 (기록에 남습니다)');
  if(reason === null) return;
  try {
    var r = await rpc('ko_sub_reset', { p_actor_id:actor(), p_exam_id:_ka.exam.id, p_student_id:studentId, p_reason:reason });
    if(!r || r.ok === false){ alert('초기화할 응시 기록이 없습니다.'); return; }
    await kaLoadSubs(); await kaLoadExams();
  } catch(e){ alert('초기화 실패: ' + (e.message||e)); }
};

/* 관리자 인증(baBoot)이 끝나면 회차를 읽는다 */
window.kaInit = function(){ kaLoadSessions(); };
})();
