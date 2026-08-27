# -*- coding: utf-8 -*-
"""포텐셜 hwpx 파싱 — Storage 서명 URL 을 받아 문항 12개로 편다.

몸통(파서)은 로컬에서 실측 검증된 pt_parse2 이식판(_variant/hwpx_parse.py)이다.
파일이 4.5MB 제한을 넘을 수 있어 본문에 싣지 않고 URL 로 받는다.
"""
import sys, os, json, urllib.request
from http.server import BaseHTTPRequestHandler

# _variant 안 모듈들은 서로 평면 임포트(from vg_spec import …)를 쓴다 — 폴더를 경로에 얹는다
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '_variant'))
from hwpx_parse import parse_potential


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            n = int(self.headers.get('content-length') or 0)
            body = json.loads(self.rfile.read(n) or b'{}')
            url = body.get('url') or ''
            if not url.startswith('https://'):
                raise ValueError('url 이 없거나 https 가 아님')
            with urllib.request.urlopen(url, timeout=30) as r:
                data = r.read()
            if len(data) > 25 * 1024 * 1024:
                raise ValueError('파일이 너무 큼 (25MB 초과)')
            out = parse_potential(data)
            self._send(200, out)
        except Exception as e:
            self._send(500, {'error': '%s: %s' % (type(e).__name__, str(e)[:200])})

    def _send(self, code, obj):
        blob = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)
