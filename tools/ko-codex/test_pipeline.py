import unittest
from pathlib import Path
import json
import tempfile
from unittest.mock import patch
import pipeline


class ReviewTests(unittest.TestCase):
    def fixture(self):
        import pymupdf
        doc=pymupdf.open();doc.new_page()
        return doc.tobytes(),{'sets':[{'range':'1','area':'독서','sourceRegions':[{'page':1,'column':0,'rect':[0,0,100,100]}],'qs':[]}]}

    def test_failed_codex_never_returns_success(self):
        pdf,result=self.fixture()
        with tempfile.TemporaryDirectory() as d, patch('pipeline.subprocess.run') as run:
            run.return_value.returncode=1
            with self.assertRaises(RuntimeError):pipeline.review(result,pdf,Path(d),'codex',lambda x:None)
        self.assertNotIn('codexReview',result)

    def test_review_command_and_structured_result(self):
        pdf,result=self.fixture()
        def fake(cmd,**kw):
            self.assertIn('read-only',cmd)
            self.assertIn('features.shell_tool=false',cmd)
            self.assertEqual(cmd[-1],'-')
            Path(cmd[cmd.index('-o')+1]).write_text(json.dumps({'issues':['check border'],'summary':'reviewed'}))
            return type('Run',(),{'returncode':0})()
        with tempfile.TemporaryDirectory() as d, patch('pipeline.subprocess.run',side_effect=fake):
            out=pipeline.review(result,pdf,Path(d),'codex',lambda x:None)
        self.assertEqual(out['codexReview'][0]['pages'],[1])
        self.assertEqual(out['codexReview'][0]['issues'],['check border'])

    def test_scan_rejected(self):
        pdf,_=self.fixture()
        with self.assertRaises(ValueError):pipeline.extract(pdf)

    def test_capacity_retries_then_success(self):
        pdf,result=self.fixture()
        calls=[]
        def fake(cmd,**kw):
            calls.append(cmd)
            if len(calls)==1:
                kw['stderr'].write('ERROR: Selected model is at capacity. Please try a different model.\n')
                return type('Run',(),{'returncode':1})()
            Path(cmd[cmd.index('-o')+1]).write_text(json.dumps({'issues':[],'summary':'ok'}))
            return type('Run',(),{'returncode':0})()
        with tempfile.TemporaryDirectory() as d, patch('pipeline.subprocess.run',side_effect=fake), patch('pipeline.time.sleep') as sleep:
            pipeline.review(result,pdf,Path(d),'codex',lambda x:None)
            self.assertEqual(len(calls),2)
            sleep.assert_called_once_with(10)

    def test_capacity_stops_after_three_attempts(self):
        pdf,result=self.fixture()
        def fake(cmd,**kw):
            kw['stderr'].write('ERROR: Selected model is at capacity.\n')
            return type('Run',(),{'returncode':1})()
        with tempfile.TemporaryDirectory() as d, patch('pipeline.subprocess.run',side_effect=fake) as run, patch('pipeline.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'모델 서버가 혼잡'):
                pipeline.review(result,pdf,Path(d),'codex',lambda x:None)
            self.assertEqual(run.call_count,3)
        self.assertNotIn('codexReview',result)


if __name__=='__main__':unittest.main()
