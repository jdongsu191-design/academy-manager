import base64
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET
import pymupdf
from source_pipeline import validate_request, extract_source, check_region


def pdf(pages=8):
    with pymupdf.open() as doc:
        for n in range(pages):
            doc.new_page().insert_text((40,40), f'Question {n+1}: x + 1 = 2')
        return base64.b64encode(doc.tobytes()).decode()


def question(page=2):
    return dict(number='1',printed_page='10',unit='방정식',statement='값을 구하시오. $x+1=2$',
                answer='$1$',solution='$x=1$',warning='',regions=[dict(page=page,box=[0.05,0.05,0.8,0.5])],figures=[])


class SourceTests(unittest.TestCase):
    def test_range_bounds_and_long_book(self):
        data=dict(operation='extract',pdf=pdf(116),start=110,end=114)
        self.assertTrue(validate_request(data))
        for lo,hi in ((1,6),(0,1),(115,117)):
            with self.assertRaises(ValueError):validate_request(dict(data,start=lo,end=hi))

    def test_extract_neighbor_pages_no_invented_ready_status(self):
        with tempfile.TemporaryDirectory() as tmp, patch('source_pipeline.ask',return_value={'items':[question()], 'issues':['확인 필요']}) as ask:
            out=extract_source(dict(operation='extract',pdf=pdf(),start=2,end=3),Path(tmp),'codex',lambda _:None)
            self.assertEqual(len(ask.call_args.args[-1]),4)
            self.assertEqual(out['items'][0]['status'],'review')
            self.assertEqual(out['items'][0]['regions'][0]['page'],2)

    def test_context_only_questions_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, patch('source_pipeline.ask',return_value={'items':[question(1)],'issues':[]}):
            with self.assertRaises(ValueError):extract_source(dict(operation='extract',pdf=pdf(),start=2,end=3),Path(tmp),'codex',lambda _:None)

    def test_region_validation(self):
        for box in ([0,0,float('nan'),1],[0,0,2,1],[0.8,0,0.2,1]):
            with self.assertRaises(ValueError):check_region(dict(page=1,box=box),1,2)

    def test_export_real_equations_and_review_gate(self):
        q=dict(question(),status='review',figure_images=[])
        with self.assertRaises(ValueError):validate_request(dict(operation='export',items=[q]))
        q['status']='ready'
        with tempfile.TemporaryDirectory() as tmp:
            out=extract_source(dict(operation='export',items=[q],title='원본 검수 테스트'),Path(tmp),None,lambda _:None)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(out['hwpx']))) as z:
                for name in z.namelist():
                    if name.endswith(('.xml','.hpf','.rdf')):ET.fromstring(z.read(name))
                section=z.read('Contents/section0.xml').decode()
                self.assertIn('<hp:equation',section)
                self.assertIn('x+1=2',section)
                self.assertIn('값을 구하시오',section)


if __name__=='__main__':unittest.main()
