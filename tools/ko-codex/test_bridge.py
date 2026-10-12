import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.request
import urllib.error


class PairingTests(unittest.TestCase):
    def test_origin_token_host_and_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('bridge.py')),'--origin','https://test.bmaps.example','--data-dir',directory],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env={**__import__('os').environ,'PYTHONIOENCODING':'utf-8'})
            try:
                proc.stdout.readline()
                token=proc.stdout.readline().strip().split(': ',1)[1]
                def request(origin='https://test.bmaps.example',auth=token,method='GET',host='127.0.0.1:8765'):
                    req=urllib.request.Request('http://127.0.0.1:8765/health',method=method,headers={'Origin':origin,'Host':host,'Authorization':'Bearer '+auth})
                    try:
                        with urllib.request.urlopen(req,timeout=5) as r:return r.status,dict(r.headers)
                    except urllib.error.HTTPError as e:return e.code,dict(e.headers)
                self.assertEqual(request()[0],200)
                self.assertEqual(request(auth='wrong')[0],401)
                self.assertEqual(request(origin='https://evil.example')[0],403)
                self.assertEqual(request(host='evil.example')[0],403)
                status,headers=request(method='OPTIONS',auth='')
                self.assertEqual(status,204)
                self.assertEqual(headers['Access-Control-Allow-Origin'],'https://test.bmaps.example')
            finally:
                proc.terminate();proc.communicate(timeout=10)


if __name__=='__main__':unittest.main()
