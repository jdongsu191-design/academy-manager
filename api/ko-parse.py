# -*- coding: utf-8 -*-
"""국어 시험지 PDF → 구조(JSON).  몸통은 _ko/ko_parse.py (로컬에서 두 시험지로 실측 검증).

파일이 4.5MB 본문 제한을 넘을 수 있어 variant-parse 처럼 Storage URL 로 받는다.
  POST {url, from?, to?}  →  {sets, figs, tables, stats}
"""
import sys, os, json, urllib.request
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '_ko'))
from ko_parse import parse


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
            if len(data) > 30 * 1024 * 1024:
                raise ValueError('파일이 너무 큼 (30MB 초과)')
            lo = int(body.get('from') or 1)
            hi = int(body.get('to') or 99)
            self._send(200, parse(data, lo, hi))
        except Exception as e:
            self._send(500, {'error': '%s: %s' % (type(e).__name__, str(e)[:300])})

    def _send(self, code, obj):
        blob = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)
