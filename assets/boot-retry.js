/* BMAPS 공용 — 자동 로그인(저장된 계정 확인) 보강  (2026-11-19)
   서버가 잠깐 멈추거나 5xx 를 주면 페이지가 "계정 조회 실패"로 막히거나 로그인이 풀리던 문제.
   · bmapsFetchUser(db, id, cols) : 요청마다 8초 제한, 최대 3번 시도.
       성공  → { data: 행 또는 null(그런 계정 없음), error: null, unreachable: false }
       실패  → { data: null, error: 마지막 오류, unreachable: true }   ← 서버·네트워크 문제. 로그인 정보를 지우면 안 된다
   · bmapsBootFail() : "서버에 연결하지 못했습니다" 덮개 + [다시 시도](새로고침) · [닫기]
   메인(index.html)은 같은 규칙을 자체 구현(tryAutoLogin)으로 갖고 있다. */
(function () {
  'use strict';
  var TIMEOUT_MS = 8000, TRIES = 3, WAIT_MS = 1500;

  window.bmapsFetchUser = async function (db, id, cols) {
    var lastErr = null;
    for (var attempt = 1; attempt <= TRIES; attempt++) {
      try {
        var res = await Promise.race([
          db.from('users').select(cols || '*').eq('id', id).maybeSingle(),
          new Promise(function (_, rej) { setTimeout(function () { rej(new Error('timeout')); }, TIMEOUT_MS); })
        ]);
        if (res.error) throw res.error;
        return { data: res.data || null, error: null, unreachable: false };
      } catch (e) {
        lastErr = e;
        console.warn('[bmapsFetchUser] ' + attempt + '번째 시도 실패:', e && e.message ? e.message : e);
        if (attempt < TRIES) await new Promise(function (r) { setTimeout(r, WAIT_MS); });
      }
    }
    return { data: null, error: lastErr || new Error('unreachable'), unreachable: true };
  };

  window.bmapsBootFail = function () {
    if (document.getElementById('bmaps-boot-fail')) return;
    var ov = document.createElement('div');
    ov.id = 'bmaps-boot-fail';
    ov.style.cssText = 'position:fixed;inset:0;z-index:2147483000;background:rgba(15,23,42,.72);display:flex;align-items:center;justify-content:center;padding:20px;font-family:inherit';
    var btn = 'margin:0 4px;padding:10px 18px;border-radius:9px;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit;';
    ov.innerHTML = '<div style="background:#fff;border-radius:14px;padding:26px 24px;max-width:340px;width:100%;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,.3)">'
      + '<div style="font-size:16px;font-weight:800;color:#1e293b;margin-bottom:8px">서버에 연결하지 못했습니다</div>'
      + '<div style="font-size:13px;color:#64748b;line-height:1.6;margin-bottom:18px">잠시 후 다시 시도해 주세요.<br>로그인 정보는 그대로 유지됩니다.</div>'
      + '<button type="button" style="' + btn + 'background:#1e3a8a;color:#fff;border:none" onclick="location.reload()">다시 시도</button>'
      + '<button type="button" style="' + btn + 'background:#fff;color:#475569;border:1px solid #cbd5e1" onclick="this.closest(\'#bmaps-boot-fail\').remove()">닫기</button>'
      + '</div>';
    (document.body || document.documentElement).appendChild(ov);
  };
})();
