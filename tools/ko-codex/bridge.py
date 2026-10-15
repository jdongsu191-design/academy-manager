"""Paired loopback-only worker for a trusted BMAPS administrator browser."""
import argparse
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import shutil
import socket
import threading
import time
import uuid
from urllib.parse import urlsplit

from pipeline import extract, review
from answers import parse_answers

LIMIT = 30*1024*1024


class ExclusiveServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def run_server(origin, root, codex, port=8765):
    parts = urlsplit(origin)
    if parts.scheme != 'https' or not parts.hostname or origin != f'https://{parts.netloc}':
        raise ValueError('정확한 HTTPS BMAPS origin을 지정하세요 (경로/끝 슬래시 제외).')
    root.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    jobs = {}
    # Completed results survive updates/restarts so the browser can resume its saved job ID.
    for resultfile in sorted(root.glob('*/result.json'),key=lambda p:p.stat().st_mtime)[-20:]:
        jobid=resultfile.parent.name
        if len(jobid)==32 and all(c in '0123456789abcdef' for c in jobid):
            jobs[jobid]={'status':'complete','message':'저장된 분석 결과를 불러왔습니다.','created':resultfile.stat().st_mtime}
    sessions = {}  # In-memory, origin-bound approvals; lost when the worker stops.
    lock = threading.RLock()

    def work(jobid, pdf, lo, hi, kind="korean"):
        folder = root/jobid
        folder.mkdir()
        def progress(message):
            with lock:
                jobs[jobid]['message'] = message
        try:
            progress('Python 원본 영역 분석 중')
            if kind == 'exam':
                from exam_pipeline import extract_exam
                result = extract_exam(pdf,folder,codex,progress)
            elif kind == 'naje':
                from naje_pipeline import extract_naje
                result = extract_naje(pdf,folder,codex,progress)
            else:
                result = extract(pdf,lo,hi)
                result = review(result,pdf,folder,codex,progress)
            blob = json.dumps(result,ensure_ascii=False).encode('utf-8')
            if len(blob)>80*1024*1024:
                raise ValueError('결과가 큽니다. 문항 범위를 나누어 분석하세요.')
            (folder/'result.json').write_bytes(blob)
            with lock:
                jobs[jobid].update(status='complete',message='원본·Codex 검토 완료. 등록 전 결과를 확인하세요.')
        except Exception as e:
            with lock:
                jobs[jobid].update(status='failed',message=str(e)[:400])

    class Handler(BaseHTTPRequestHandler):
        def approved_origin(self, value):
            with lock:
                expired=[key for key,s in sessions.items() if s['expires']<=time.time()]
                for key in expired: sessions.pop(key,None)
                return value==origin or any(s['origin']==value for s in sessions.values())

        def log_message(self,*args):
            pass  # Never log pairing credentials or document contents.

        def send(self,status,payload):
            blob=json.dumps(payload,ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            if self.approved_origin(self.headers.get('Origin')):
                self.send_header('Access-Control-Allow-Origin',self.headers.get('Origin'))
                self.send_header('Vary','Origin')
            self.send_header('Content-Length',str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

        def trusted(self,auth=True):
            local_origin=f'http://127.0.0.1:{port}'
            request_origin=self.headers.get('Origin')
            local_request=request_origin==local_origin or (not request_origin and self.headers.get('Sec-Fetch-Site')=='same-origin')
            if self.headers.get('Host') != f'127.0.0.1:{port}' or not (self.approved_origin(request_origin) or local_request):
                self.send(403,{'error':'허용되지 않은 웹사이트입니다.'});return False
            credential=self.headers.get('Authorization','')
            master=hmac.compare_digest(credential,'Bearer '+token) and (local_request or request_origin==origin)
            with lock:
                session=sessions.get(credential.removeprefix('Bearer '),{})
                scoped=session.get('origin')==request_origin and session.get('expires',0)>time.time()
            if auth and not (master or scoped):
                self.send(401,{'error':'연결 코드를 확인하세요.'});return False
            return True

        def do_OPTIONS(self):
            if not self.trusted(False):return
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin',self.headers.get('Origin'))
            self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type')
            self.send_header('Access-Control-Allow-Private-Network','true')
            self.send_header('Vary','Origin')
            self.end_headers()

        def do_GET(self):
            if self.path in ('/','/connect'):
                if self.headers.get('Host') != f'127.0.0.1:{port}':
                    self.send(403,{'error':'허용되지 않은 주소'});return
                nonce=secrets.token_urlsafe(20)
                template=Path(__file__).with_name('connect.html').read_text(encoding='utf-8')
                blob=template.replace('__TOKEN__',json.dumps(token)).replace('__NONCE__',nonce).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Cache-Control','no-store')
                self.send_header('X-BMAPS-Bridge-Version','6')
                self.send_header('X-Frame-Options','DENY')
                self.send_header('Content-Security-Policy',f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
                self.send_header('Content-Length',str(len(blob)));self.end_headers();self.wfile.write(blob);return
            if not self.trusted():return
            if self.path=='/health':
                self.send(200,{'ok':True,'version':6,'capabilities':['korean','naje','exam','exam-hwp']});return
            jobid=self.path.removeprefix('/jobs/')
            with lock:
                state=dict(jobs.get(jobid,{}))
            if not state:
                self.send(404,{'error':'작업이 없습니다. 처리 프로그램 재시작 후에는 다시 분석하세요.'});return
            if state['status']=='complete':
                state['result']=json.loads((root/jobid/'result.json').read_text(encoding='utf-8'))
            self.send(200,state)

        def do_POST(self):
            if not self.trusted():return
            if self.path=='/answers':
                try:
                    n=int(self.headers.get('Content-Length','0'))
                    if not 1<=n<=10*1024*1024 or self.headers.get('Content-Type')!='application/pdf':raise ValueError('10MB 이하 정답 PDF를 사용하세요.')
                    self.connection.settimeout(30)
                    self.send(200,parse_answers(self.rfile.read(n)))
                except Exception as e:self.send(400,{'error':str(e)[:300]})
                return
            if self.path in ('/sessions','/sessions/revoke'):
                if self.headers.get('Origin')!=f'http://127.0.0.1:{port}' or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                    self.send(403,{'error':'로컬 승인 창에서만 허용할 수 있습니다.'});return
                try:
                    n=int(self.headers.get('Content-Length','0'))
                    if not 1<=n<=2048: raise ValueError('잘못된 승인 요청')
                    data=json.loads(self.rfile.read(n))
                    if self.path=='/sessions/revoke':
                        with lock: sessions.pop(data.get('token',''),None)
                        self.send(200,{'ok':True});return
                    approved=data['origin'];parts=urlsplit(approved)
                    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or approved!=f'https://{parts.netloc}':
                        raise ValueError('HTTPS 사이트만 허용할 수 있습니다.')
                    key=secrets.token_urlsafe(32)
                    with lock:
                        if len(sessions)>=100: raise ValueError('승인 세션이 많습니다. 처리 프로그램을 재시작하세요.')
                        sessions[key]={'origin':approved,'expires':time.time()+12*60*60}
                    self.send(200,{'token':key});return
                except (ValueError,KeyError,TypeError) as e:
                    self.send(400,{'error':str(e)});return
            if self.path=='/shutdown':
                if self.headers.get('Origin')!=f'http://127.0.0.1:{port}':
                    self.send(403,{'error':'로컬 연결 창에서만 종료할 수 있습니다.'});return
                self.send(200,{'ok':True})
                threading.Thread(target=self.server.shutdown,daemon=True).start();return
            parsed=urlsplit(self.path)
            if parsed.path!='/jobs':self.send(404,{'error':'Not found'});return
            from urllib.parse import parse_qs
            try:
                params=parse_qs(parsed.query)
                kind=params.get('kind',['korean'])[0]
                if kind not in ('korean','naje','exam'):raise ValueError('지원하지 않는 분석 종류')
                lo=int(params.get('from',['1'])[0]);hi=int(params.get('to',['99'])[0])
                if not 1<=lo<=hi<=99:raise ValueError('문항 범위 오류')
                n=int(self.headers.get('Content-Length','0'))
                if not 1<=n<=LIMIT:raise ValueError('30MB 이하 PDF를 사용하세요.')
                expected_type = 'application/json' if kind == 'exam' else 'application/pdf'
                if self.headers.get('Content-Type')!=expected_type:raise ValueError('분석 입력 형식 오류')
                with lock:
                    if any(j['status']=='running' for j in jobs.values()):
                        self.send(409,{'error':'이미 처리 중인 작업이 있습니다.'});return
                    # Bound in-memory history; files remain locally until operator removes them.
                    if len(jobs)>=20:
                        jobs.pop(next(iter(jobs)))
                    jobid=uuid.uuid4().hex
                    jobs[jobid]={'status':'running','message':'파일 수신 중','created':time.time()}
                self.connection.settimeout(30)
                pdf=self.rfile.read(n)
                if len(pdf)!=n or (kind != 'exam' and not pdf.startswith(b'%PDF-')):
                    with lock:jobs.pop(jobid,None)
                    raise ValueError('유효한 PDF가 아닙니다.')
                if kind == 'exam':
                    from exam_pipeline import validate_request
                    pdf = json.loads(pdf)
                    validate_request(pdf)
                threading.Thread(target=work,args=(jobid,pdf,lo,hi,kind),daemon=True).start()
                self.send(202,{'id':jobid})
            except Exception as e:
                if 'jobid' in locals():
                    with lock:
                        if jobs.get(jobid,{}).get('message')=='파일 수신 중':jobs.pop(jobid,None)
                self.send(400,{'error':str(e)[:300]})

    try:
        server=ExclusiveServer(('127.0.0.1',port),Handler)
    except OSError as e:
        raise RuntimeError('이미 실행 중인 처리 프로그램이 있거나 포트를 사용할 수 없습니다. 기존 창을 확인하세요.') from e
    print('BMAPS origin: '+origin,flush=True)
    print('연결 코드 (브라우저 Codex 연결 설정에 입력): '+token,flush=True)
    print('이 창이 열려 있는 동안만 동작합니다. 종료: Ctrl+C',flush=True)
    try:server.serve_forever()
    finally:server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--origin',required=True)
    parser.add_argument('--codex',help='Local Codex executable resolved by the launcher')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data-dir',type=Path,default=Path.home()/'.bmaps-ko-worker')
    args=parser.parse_args()
    codex=shutil.which(args.codex or 'codex')
    if not codex:raise SystemExit('Codex CLI를 설치하고 codex login을 실행하세요.')
    run_server(args.origin,args.data_dir.resolve(),codex,args.port)
