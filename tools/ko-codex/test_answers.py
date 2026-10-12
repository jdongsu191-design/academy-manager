import unittest
from unittest.mock import patch
from answers import parse_answers


class AnswerTests(unittest.TestCase):
    def test_elective_columns_do_not_overwrite(self):
        class Rect:
            def __init__(self,x):self.x0=x;self.x1=x+40;self.y1=20
        class Page:
            def search_for(self,label):return [Rect(300 if label=='화법과 작문' else 400)]
            def get_text(self,mode):
                return [[x,50,x+10,60,t] for x,t in [(10,'1'),(30,'④'),(50,'2'),(300,'35'),(320,'②'),(340,'3'),(400,'35'),(420,'⑤'),(440,'2')]]
        class Doc(list):is_encrypted=False
        with patch('answers.pymupdf.open',return_value=Doc([Page()])):
            rows=parse_answers(b'pdf')['rows']
        self.assertEqual([(r['elective'],r['no'],r['answer']) for r in rows],[('공통',1,4),('화법과 작문',35,2),('언어와 매체',35,5)])

    def test_empty_scan_fails(self):
        class Doc(list):is_encrypted=False
        with patch('answers.pymupdf.open',return_value=Doc([])):
            with self.assertRaisesRegex(ValueError,'정답표를 읽지 못했습니다'):parse_answers(b'pdf')

if __name__=='__main__':unittest.main()
