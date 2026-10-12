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


if __name__=='__main__':unittest.main()
