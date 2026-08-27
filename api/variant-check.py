# -*- coding: utf-8 -*-
"""검산 — 좌표 검산기(오탐 0 실측)를 문항 단위로 부른다.

함수 시간 제한(60초) 때문에 한 문항의 검산을 쪼갠다. 브라우저가 지휘한다:
  mode=run     : 온도 하나로 명세를 받아 푼다 (AI 호출 1~2번 + 수치 풀이)
  mode=combine : run 결과 두셋을 원판 규칙대로 합쳐 판정한다 (AI 호출 없음)
                 need_third=true 로 오면 온도 0.35 로 한 번 더 run 한 뒤 다시 combine.
"""
import sys, os, json, base64
from http.server import BaseHTTPRequestHandler

# _variant 안 모듈들은 서로 평면 임포트(from vg_spec import …)를 쓴다 — 폴더를 경로에 얹는다
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '_variant'))
from vg_core import run_once, combine


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            n = int(self.headers.get('content-length') or 0)
            body = json.loads(self.rfile.read(n) or b'{}')
            mode = body.get('mode') or 'run'

            if mode == 'run':
                stmt = body.get('statement') or ''
                if not stmt.strip():
                    raise ValueError('statement 가 비었음')
                png = None
                if body.get('png_b64'):
                    png = base64.b64decode(body['png_b64'])
                    if len(png) > 2 * 1024 * 1024:
                        raise ValueError('그림이 너무 큼 (2MB 초과)')
                r = run_once(stmt, png, temp=float(body.get('temp') or 0.15))
                r.pop('spec', None)          # 응답을 가볍게 — 명세는 판정에 이미 반영됨
                self._send(200, r)
                return

            if mode == 'combine':
                rs = body.get('runs') or []
                if not (2 <= len(rs) <= 3):
                    raise ValueError('runs 는 2~3개여야 함')
                out = combine(rs, body.get('answer_script') or None)
                self._send(200, out)
                return

            raise ValueError('mode 는 run 또는 combine')
        except Exception as e:
            self._send(500, {'error': '%s: %s' % (type(e).__name__, str(e)[:200])})

    def _send(self, code, obj):
        blob = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)
