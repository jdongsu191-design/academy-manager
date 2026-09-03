/* ═══════════════════════════════════════════════════════════
   BMAPS 자동 새로고침 — 매일 새벽 5시 정각
   ───────────────────────────────────────────────────────────
   모든 페이지가 이 파일 하나를 불러 쓴다(HTML 마다 <script src> 한 줄).
   동작을 바꿀 일이 생기면 여기만 고치면 되고 HTML 은 다시 안 건드린다.

   왜 서버 신호가 아니라 각 페이지의 시계인가
     · 별도 서버·구독이 필요 없고, 오래 켜 둔 화면(키오스크·로비 TV)에서
       가장 확실하게 동작한다.
   왜 setTimeout 이 아니라 30초 간격 검사인가
     · 20시간짜리 setTimeout 은 절전/최대화 해제 후 밀리거나 안 뜬다.
       "지금 시각이 목표를 지났나"를 주기적으로 보면 절전에서 깨어난 직후에도 맞는다.
   캐시
     · 배포 HTML 이 `max-age=0, must-revalidate` 라 일반 reload 로도 최신을 받는다.
       (2026-09-03 실측) 그래서 URL 에 캐시무력화 파라미터를 붙이지 않는다.

   끄는 법: 페이지에서 window.BMAPS_NO_AUTO_RELOAD = true 로 두면 동작하지 않는다.
   ═══════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var HOUR = 5, MINUTE = 0;      // 새벽 5시 정각
  var CHECK_MS = 30 * 1000;      // 30초마다 시계 확인
  var GRACE_MS = 2 * 60 * 1000;  // 열자마자 다시 도는 일 방지(시계 이상 대비)

  if (window.BMAPS_AUTO_RELOAD_ON) return;   // 중복 로드 방지
  window.BMAPS_AUTO_RELOAD_ON = true;

  var loadedAt = Date.now();

  function nextTarget(from) {
    var t = new Date(from);
    t.setHours(HOUR, MINUTE, 0, 0);
    if (t.getTime() <= from.getTime()) t.setDate(t.getDate() + 1);
    return t;
  }

  var target = nextTarget(new Date());

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function label(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
      + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  console.log('[BMAPS] 자동 새로고침 예약 — ' + label(target));

  setInterval(function () {
    if (window.BMAPS_NO_AUTO_RELOAD) return;
    var now = new Date();
    if (now.getTime() - loadedAt < GRACE_MS) return;
    if (now.getTime() < target.getTime()) return;
    console.log('[BMAPS] 새벽 ' + HOUR + '시 — 화면을 새로 불러옵니다.');
    try { location.reload(); }
    catch (e) { location.href = location.href; }
  }, CHECK_MS);
})();
