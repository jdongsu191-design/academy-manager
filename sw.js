/* BMAPS 서비스워커 — 설치형 웹앱(PWA) 조건을 채우기 위한 최소 구현.
   ⚠ 아무것도 캐시하지 않는다. 모든 요청을 네트워크로 그대로 보낸다.
      (배포 HTML 이 max-age=0 이고 새벽 자동 새로고침이 최신본을 받는 구조를 그대로 둔다) */
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', function (e) { e.respondWith(fetch(e.request)); });
