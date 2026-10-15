import base64
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import pymupdf
from hwp_convert import validate_document, to_pdf
from exam_pipeline import validate_request, extract_exam


class HwpTests(unittest.TestCase):
    def test_format_checks(self):
        validate_document(b'%PDF-test', 'pdf')
        validate_document(bytes.fromhex('d0cf11e0a1b11ae1'), 'hwp')
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as z: z.writestr('Contents/content.hpf', '<test/>')
        validate_document(archive.getvalue(), 'hwpx')
        for blob, ext in [(b'%PDF-test','hwp'), (b'invalid','hwpx'),(b'fake','exe')]:
            with self.assertRaises(ValueError): validate_document(blob, ext)
        request=dict(operation='analysis',prompt='분석',units=['a'],format='hwpx',pdf=base64.b64encode(archive.getvalue()).decode())
        self.assertEqual(validate_request(request),archive.getvalue())

    def test_hwp_runs_conversion_before_analysis(self):
        with pymupdf.open() as document:
            document.new_page();pdf=document.tobytes()
        blob=bytes.fromhex('d0cf11e0a1b11ae1')
        request=dict(operation='range',prompt='분석',units=['단원'],format='hwp',pdf=base64.b64encode(blob).decode())
        with tempfile.TemporaryDirectory() as folder, patch('exam_pipeline.to_pdf', return_value=pdf) as convert, patch('exam_pipeline.ask',return_value={'units':[{'name':'단원','evidence':'1번'}]}):
            result=extract_exam(request,Path(folder),'codex',lambda _:None)
            self.assertEqual(convert.call_args.args[:2],(blob,'hwp'))
            self.assertEqual(result['output']['units'][0]['name'],'단원')

    def test_pdf_is_not_converted(self):
        self.assertEqual(to_pdf(b'%PDF-test','pdf',Path('.'),print),b'%PDF-test')


if __name__ == '__main__': unittest.main()
