# -*- coding: utf-8 -*-
"""문제집 조립 — 원본 hwpx(서명 URL)와 변형 데이터를 받아 완성 hwpx 를 돌려준다.

원본에서 쪽 설정·서식·원문 그림·해설 그림을 물려받으므로 원본이 꼭 필요하다.
응답은 {hwpx_b64, stats} — 브라우저가 Blob 으로 바꿔 내려받는다.
"""
import sys, os, json, base64, urllib.request
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '_variant'))
from hwpx_parse import parse, tidy, add_figures
import io as _io


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            n = int(self.headers.get('content-length') or 0)
            body = json.loads(self.rfile.read(n) or b'{}')
            url = body.get('url') or ''
            gen = body.get('gen') or {}
            title = (body.get('title') or '포텐셜 변형문제집')[:120]
            if not url.startswith('https://'):
                raise ValueError('url 이 없거나 https 가 아님')
            if not gen:
                raise ValueError('변형이 없습니다 — 먼저 만들어 주세요')
            with urllib.request.urlopen(url, timeout=30) as r:
                src = r.read()
            # 원문은 서버가 원본에서 새로 읽는다 — 그림·해설그림까지 다 있는 정본
            probs = add_figures([tidy(p) for p in parse(_io.BytesIO(src))],
                                _io.BytesIO(src))
            from sheet_core import build_book
            data, stats = build_book(src, probs, gen, title)
            if len(data) > 4 * 1024 * 1024:
                raise ValueError('만든 파일이 너무 큼 (%.1f MB)' % (len(data) / 1048576))
            self._send(200, {'hwpx_b64': base64.b64encode(data).decode(),
                             'size': len(data), 'stats': stats})
        except Exception as e:
            self._send(500, {'error': '%s: %s' % (type(e).__name__, str(e)[:200])})

    def _send(self, code, obj):
        blob = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)
