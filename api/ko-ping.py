# -*- coding: utf-8 -*-
"""pymupdf 가 Vercel 파이썬 함수에서 돌아가는지 보는 시험 함수.

국어 시험지 추출을 브라우저(pdf.js)에서 서버(pymupdf)로 옮기기 전에
설치 · 파싱 · 렌더링 세 가지만 확인한다. 확인이 끝나면 지운다.
"""
import sys, json, time, platform
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        t0 = time.time()
        out = {'python': sys.version.split()[0], 'os': platform.platform()}
        try:
            import pymupdf
            out['pymupdf'] = pymupdf.version[0]
            out['mupdf'] = pymupdf.version[1]

            # ① 파싱 — 빈 문서에 한글을 넣고 다시 읽는다
            d = pymupdf.open()
            p = d.new_page(width=595, height=842)
            try:
                p.insert_text((72, 100), '국어 영역 시험 123', fontname='korea', fontsize=14)
                out['font'] = 'korea'
            except Exception:
                p.insert_text((72, 100), 'korean test 123', fontname='helv', fontsize=14)
                out['font'] = 'helv'
            p.draw_line((72, 110), (200, 110))
            out['text'] = p.get_text().strip()
            out['drawings'] = len(p.get_drawings())
            spans = [s for b in p.get_text('dict')['blocks']
                     for l in b.get('lines', []) for s in l['spans']]
            out['spans'] = [(s['font'], round(s['size'], 1)) for s in spans][:3]

            # ② 렌더링 — 브라우저 pdf.js 가 75초 넘게 걸리던 바로 그 작업
            pix = p.get_pixmap(dpi=150)
            out['pixmap'] = '%dx%d' % (pix.width, pix.height)
            out['png_bytes'] = len(pix.tobytes('png'))
            out['ok'] = True
        except Exception as e:
            out['ok'] = False
            out['error'] = '%s: %s' % (type(e).__name__, str(e)[:300])
        out['ms'] = int((time.time() - t0) * 1000)
        self._send(200 if out.get('ok') else 500, out)

    def _send(self, code, obj):
        blob = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)
