/* ═══════════════════════════════════════════════════════════
   BMAPS 자동 새로고침 (공용) — 기본 매일 새벽 5시
   ───────────────────────────────────────────────────────────
   모든 페이지가 이 파일 하나를 불러 쓴다(HTML 마다 <script src> 한 줄).
   동작을 바꿀 일이 생기면 여기만 고치면 되고 HTML 은 다시 안 건드린다.

   설정: app_settings 테이블의 key='auto_reload' 행 (관리자 > 업데이트 알림에서 수정)
     { enabled:true, time:"05:00", roles:["teacher","desk",...,"anon"] }
     · 표가 없거나 못 읽으면 아래 DEFAULT 로 동작한다(기능이 죽지 않는다)
     · 10분마다 다시 읽으므로 설정을 바꾸면 하루 기다릴 필요 없이 반영된다

   역할 판정: localStorage.savedUserId → users.role 1회 조회.
     로그인 정보가 없으면 'anon'(키오스크·로비 TV)으로 본다.

   왜 setTimeout 이 아니라 주기적 시계 검사인가
     · 20시간짜리 setTimeout 은 절전/최대화 해제 후 밀리거나 안 뜬다.
       "지금이 목표를 지났나"를 주기적으로 보면 절전에서 깨어난 직후에도 맞는다.
   캐시
     · 배포 HTML 이 max-age=0, must-revalidate 라 일반 reload 로 최신을 받는다(실측).

   끄는 법: 페이지에서 window.BMAPS_NO_AUTO_RELOAD = true
   ═══════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  if (window.BMAPS_AUTO_RELOAD_ON) return;          // 중복 로드 방지
  window.BMAPS_AUTO_RELOAD_ON = true;

  var SB_URL = 'https://qtpftloyumtffvgurvqv.supabase.co';
  var SB_KEY = 'sb_publishable_XGP9n-2fuBQFuJlAA5MJ8w_R8JYIi9O';

  var DEFAULT = { enabled: true, time: '05:00',
                  roles: ['teacher', 'desk', 'admin', 'vice_director', 'student', 'anon'] };

  var CHECK_MS    = 30 * 1000;        // 시계 확인 주기
  var SETTINGS_MS = 10 * 60 * 1000;   // 설정 다시 읽는 주기
  var GRACE_MS    = 2 * 60 * 1000;    // 열자마자 다시 도는 일 방지

  var loadedAt = Date.now();
  var cfg      = DEFAULT;
  var myRole   = null;                // 아직 모름
  var target   = null;

  function api(path) {
    return fetch(SB_URL + '/rest/v1/' + path, {
      headers: { apikey: SB_KEY, Authorization: 'Bearer ' + SB_KEY }
    }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function label(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
      + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  /* 다음 목표 시각 — 오늘 그 시각이 이미 지났으면 내일 */
  function nextTarget(from) {
    var hm = String(cfg.time || DEFAULT.time).split(':');
    var h = parseInt(hm[0], 10), m = parseInt(hm[1], 10);
    if (isNaN(h)) h = 5;
    if (isNaN(m)) m = 0;
    var t = new Date(from);
    t.setHours(h, m, 0, 0);
    if (t.getTime() <= from.getTime()) t.setDate(t.getDate() + 1);
    return t;
  }

  function applies() {
    if (!cfg.enabled) return false;
    if (myRole === null) return false;                       // 역할을 아직 모르면 보류
    var roles = cfg.roles || DEFAULT.roles;
    return roles.indexOf(myRole) !== -1;
  }

  function reschedule(why) {
    var prev = target;
    target = nextTarget(new Date());
    if (!prev || prev.getTime() !== target.getTime()) {
      console.log('[BMAPS] 자동 새로고침 ' + (cfg.enabled ? '예약 — ' + label(target) : '꺼짐')
        + ' (역할 ' + myRole + (why ? ', ' + why : '') + ')');
    }
  }

  /* ── 내 역할 알아내기 ── */
  function loadRole() {
    var uid = null;
    try { uid = localStorage.getItem('savedUserId'); } catch (e) {}
    if (!uid) { myRole = 'anon'; reschedule('비로그인 화면'); return; }
    api('users?id=eq.' + encodeURIComponent(uid) + '&select=role').then(function (rows) {
      myRole = (rows && rows[0] && rows[0].role) ? rows[0].role : 'anon';
      reschedule();
    });
  }

  /* ── 설정 읽기 ── */
  function loadSettings() {
    api('app_settings?key=eq.auto_reload&select=value').then(function (rows) {
      var v = rows && rows[0] && rows[0].value;
      if (v && typeof v === 'object') {
        cfg = {
          enabled: v.enabled !== false,
          time:    v.time || DEFAULT.time,
          roles:   Array.isArray(v.roles) ? v.roles : DEFAULT.roles
        };
      } else {
        cfg = DEFAULT;      // 표가 없거나 행이 없으면 기본값
      }
      if (myRole !== null) reschedule();
    });
  }

  loadRole();
  loadSettings();
  setInterval(loadSettings, SETTINGS_MS);

  setInterval(function () {
    if (window.BMAPS_NO_AUTO_RELOAD) return;
    if (!applies() || !target) return;
    var now = Date.now();
    if (now - loadedAt < GRACE_MS) return;
    if (now < target.getTime()) return;
    console.log('[BMAPS] ' + cfg.time + ' — 화면을 새로 불러옵니다.');
    try { location.reload(); }
    catch (e) { location.href = location.href; }
  }, CHECK_MS);
})();
