# -*- coding: utf-8 -*-
"""변형 생성·해설 재작성 — 60초 제한에 맞춰 등급 하나씩 브라우저가 부른다.

  mode=gen    : {prob{statement,answer_script,type,points}, grade_label, level,
                 png_b64?, retry_note?, temp?} → 변형 하나 (손질·표 달기까지 끝난 것)
  mode=resol  : {statement, answer, grade_label} → 헤맨 해설 다시 쓰기
  mode=resol2 : {statement, answer, over[], grade_label} → 그 학년 도구로 다시 쓰기
재작성 둘은 **답이 검산으로 확인된 것에만** 부를 것 — 브라우저가 지킨다.
"""
import sys, os, json
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '_variant'))
from gen_core import make_one
from resol_core import rewrite, rewrite_curr


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            n = int(self.headers.get('content-length') or 0)
            body = json.loads(self.rfile.read(n) or b'{}')
            mode = body.get('mode') or 'gen'

            if mode == 'gen':
                v = make_one(body.get('prob') or {},
                             body.get('grade_label') or '',
                             body.get('level') or 'V1',
                             png_b64=body.get('png_b64'),
                             retry_note=body.get('retry_note') or '',
                             temp=float(body.get('temp') or 0.35))
                self._send(200, v)
                return

            if mode == 'resol':
                r = rewrite(body.get('statement') or '', body.get('answer') or '',
                            body.get('grade_label') or '')
                self._send(200, r)
                return

            if mode == 'resol2':
                r = rewrite_curr(body.get('statement') or '', body.get('answer') or '',
                                 body.get('over') or [], body.get('grade_label') or '')
                self._send(200, r)
                return

            raise ValueError('mode 는 gen / resol / resol2')
        except Exception as e:
            self._send(500, {'error': '%s: %s' % (type(e).__name__, str(e)[:200])})

    def _send(self, code, obj):
        blob = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)
