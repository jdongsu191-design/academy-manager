/* BMAPS 안드로이드 앱 자체 업데이트 (2026-10-23)
   앱(Capacitor)으로 열렸을 때만 동작한다. 브라우저·설치형 웹앱에서는 아무것도 하지 않는다.
   - 앱이 자기 패키지(com.bestian.bmaps / .preview)와 versionCode 를 알려준다 (App 플러그인)
   - /app/version.json 의 같은 flavor 항목과 비교해 새 versionCode 면 상단 배너를 띄운다
   - [업데이트 받기] → 기본 브라우저(크롬)로 APK 를 내려받아 설치 화면으로 (WebView 는 APK 다운로드를 못 하므로 밖으로 연다)
   - [나중에] 는 그 버전을 기기에 기억해 다시 묻지 않는다. 더 새 버전이 나오면 다시 뜬다
   웹 코드 수정은 이 장치와 무관하게 자동 반영된다 — 이건 앱 껍데기(권한·아이콘·푸시 설정)가 바뀔 때만 쓰인다. */
(function () {
  var cap = window.Capacitor;
  if (!cap || typeof cap.isNativePlatform !== 'function' || !cap.isNativePlatform()) return;
  /* 앱(Capacitor)으로 열렸다는 표시 — 앱에서만 다르게 보일 CSS 는 html.bmaps-app 아래에 쓴다 (PC·웹앱 무영향) */
  try { document.documentElement.classList.add('bmaps-app'); } catch (e) {}
  var App = cap.Plugins && cap.Plugins.App;
  if (!App || !App.getInfo) return;

  /* 안드로이드 뒤로가기: 리스너가 없으면 Capacitor 가 앱을 바로 닫는다.
     이전 화면(예: 베티 OMR → BMAPS 홈)이 있으면 돌아가고, 열린 모달이 있으면 닫고, 첫 화면이면 종료 대신 홈 화면으로 내린다(실수 종료 방지) */
  if (App.addListener) {
    App.addListener('backButton', function (ev) {
      var openModal = document.querySelector('.modal-backdrop.open, [id^="modal-"][style*="display: flex"], [id^="modal-"][style*="display:flex"]');
      if (openModal) {
        var closeBtn = openModal.querySelector('[onclick*="closeModal"], [onclick*="close"], button[aria-label="닫기"]');
        if (closeBtn) { closeBtn.click(); return; }
        openModal.style.display = 'none'; openModal.classList.remove('open'); return;
      }
      if (ev && ev.canGoBack) { window.history.back(); return; }
      /* 학생 화면에서 질문 탭이 아닌 탭(N제 등)에 있으면 먼저 질문 탭으로 */
      var ss = document.getElementById('studentScreen');
      if (ss && ss.classList.contains('active')) {
        var home = document.getElementById('snav-question');
        if (home && !home.classList.contains('active')) { home.click(); return; }
      }
      if (App.minimizeApp) App.minimizeApp(); else if (App.exitApp) App.exitApp();
    });
  }

  function flavorOf(pkg) { return /\.preview$/.test(pkg || '') ? 'preview' : 'prod'; }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

  function showBanner(info, latest, flavor) {
    if (document.getElementById('bmaps-app-update')) return;
    var box = document.createElement('div');
    box.id = 'bmaps-app-update';
    box.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:99999;background:#1F3A51;color:#fff;padding:10px 14px;font-size:13px;display:flex;align-items:center;gap:10px;box-shadow:0 2px 10px rgba(0,0,0,.3);font-family:inherit';
    box.innerHTML = '<div style="flex:1;min-width:0;line-height:1.4"><b>앱 업데이트</b> ' + esc(latest.versionName) + (flavor === 'preview' ? ' (테스트)' : '')
      + (latest.notes ? '<br><span style="opacity:.85;font-size:12px">' + esc(latest.notes) + '</span>' : '')
      + '<br><span style="opacity:.7;font-size:11px">현재 ' + esc(info.version) + ' · 받은 뒤 설치 창에서 [설치]를 누르세요</span></div>'
      + '<button id="bmaps-app-update-go" style="background:#fff;color:#1F3A51;border:none;border-radius:8px;padding:8px 12px;font-weight:800;font-size:12.5px;white-space:nowrap">업데이트 받기</button>'
      + '<button id="bmaps-app-update-later" style="background:transparent;color:#fff;border:1px solid rgba(255,255,255,.5);border-radius:8px;padding:8px 10px;font-size:12px;white-space:nowrap">나중에</button>';
    document.body.appendChild(box);
    var url = location.origin + latest.file + '?v=' + latest.versionCode;
    document.getElementById('bmaps-app-update-go').onclick = function () {
      /* 안드로이드의 App.openUrl 은 구현이 없어(iOS 전용) Browser 플러그인(크롬 탭)으로 연다. 크롬이 APK 를 내려받고 설치 창을 띄운다 */
      var Browser = cap.Plugins && cap.Plugins.Browser;
      var p = Browser && Browser.open ? Browser.open({ url: url }) : Promise.reject(new Error('no Browser plugin'));
      p.catch(function () { return App.openUrl ? App.openUrl({ url: url }) : Promise.reject(); })
       .catch(function () { window.open(url, '_system'); });
    };
    document.getElementById('bmaps-app-update-later').onclick = function () {
      try { localStorage.setItem('bmaps_app_update_skip', String(latest.versionCode)); } catch (e) {}
      box.remove();
    };
  }

  function check() {
    App.getInfo().then(function (info) {
      var flavor = flavorOf(info.id);
      return fetch('/app/version.json?ts=' + Date.now(), { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (ver) {
          var latest = ver && ver[flavor]; if (!latest) return;
          var mine = parseInt(info.build, 10) || 0, theirs = parseInt(latest.versionCode, 10) || 0;
          if (theirs <= mine) return;
          var skip = 0; try { skip = parseInt(localStorage.getItem('bmaps_app_update_skip') || '0', 10); } catch (e) {}
          if (skip >= theirs) return;
          showBanner(info, latest, flavor);
        });
    }).catch(function (e) { console.warn('[app-update]', e); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(check, 1500); });
  else setTimeout(check, 1500);
  /* 앱을 백그라운드에서 다시 열 때도 확인 */
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') check(); });
})();
