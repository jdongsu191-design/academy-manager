import json
import socket
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.request
import urllib.error


class PairingTests(unittest.TestCase):
    def test_origin_token_host_and_preflight(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0))
            port=probe.getsockname()[1]
        with tempfile.TemporaryDirectory() as directory:
            proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('bridge.py')),'--origin','https://test.bmaps.example','--data-dir',directory,'--port',str(port)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env={**__import__('os').environ,'PYTHONIOENCODING':'utf-8'})
            try:
                proc.stdout.readline()
                token=proc.stdout.readline().strip().split(': ',1)[1]
                def request(origin='https://test.bmaps.example',auth=token,method='GET',host=None):
                    req=urllib.request.Request(f'http://127.0.0.1:{port}/health',method=method,headers={'Origin':origin,'Host':host or f'127.0.0.1:{port}','Authorization':'Bearer '+auth})
                    try:
                        with urllib.request.urlopen(req,timeout=5) as r:return r.status,dict(r.headers)
                    except urllib.error.HTTPError as e:
                        result=e.code,dict(e.headers)
                        e.close()
                        return result
                self.assertEqual(request()[0],200)
                self.assertEqual(request(auth='wrong')[0],401)
                self.assertEqual(request(origin='https://evil.example')[0],403)
                self.assertEqual(request(host='evil.example')[0],403)
                status,headers=request(method='OPTIONS',auth='')
                self.assertEqual(status,204)
                self.assertEqual(headers['Access-Control-Allow-Origin'],'https://test.bmaps.example')
                local=f'http://127.0.0.1:{port}'
                def grant_call(endpoint, data, request_origin=local, auth=token):
                    req=urllib.request.Request(local+endpoint,data=json.dumps(data).encode(),headers={'Origin':request_origin,'Authorization':'Bearer '+auth,'Content-Type':'application/json'})
                    with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)
                approved='https://new-preview.example'
                session=grant_call('/sessions',{'origin':approved})['token']
                # No popup/window is involved in subsequent health and upload requests.
                self.assertEqual(request(origin=approved,auth=session)[0],200)
                self.assertEqual(request(origin=approved,auth=token)[0],401)
                self.assertEqual(request(origin='https://test.bmaps.example',auth=session)[0],401)
                self.assertEqual(request(origin=approved,method='OPTIONS',auth='')[1]['Access-Control-Allow-Origin'],approved)
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    grant_call('/sessions',{'origin':'https://evil.example'},approved,session)
                self.assertEqual(denied.exception.code,403)
                denied.exception.close()
                req=urllib.request.Request(local+'/jobs?kind=exam',data=json.dumps({'operation':'analysis','prompt':'test','units':['test'],'pdf':'not base64!'}).encode(),headers={'Origin':approved,'Authorization':'Bearer '+session,'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as invalid:
                    urllib.request.urlopen(req,timeout=5)
                self.assertEqual(invalid.exception.code,400)
                self.assertIn('PDF',json.load(invalid.exception)['error'])
                invalid.exception.close()
                grant_call('/sessions/revoke',{'token':session})
                self.assertEqual(request(origin=approved,auth=session)[0],403)
            finally:
                proc.terminate();proc.communicate(timeout=10)


if __name__=='__main__':unittest.main()
