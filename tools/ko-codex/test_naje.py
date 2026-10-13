import unittest
from unittest.mock import patch
import pymupdf
from naje_pipeline import rect, build_result, safe_crop


class NajeTests(unittest.TestCase):
    def setUp(self):
        self.doc = pymupdf.open()
        self.doc.new_page(width=600, height=800)
        self.doc.new_page(width=600, height=800)

    def tearDown(self):
        self.doc.close()

    def page(self, pn=1, kind='questions', questions=None, answers=None):
        return dict(page=pn, kind=kind, questions=questions or [], answers=answers or [], issues=[])

    def q(self, number=1):
        return dict(number=number, rect=[50, 100, 450, 400], qrRect=[350, 410, 450, 500])

    def test_original_numbers_and_missing_answers_are_not_renumbered(self):
        with patch('naje_pipeline.decode_qr', return_value='https://youtu.be/example'):
            result = build_result(self.doc, [self.page(kind='concept'), self.page(2, questions=[self.q(3)])], 'hash')
        self.assertEqual([p['number'] for p in result['problems']], [3])
        self.assertEqual(result['problems'][0]['pageNum'], 2)
        self.assertIn('3번 정답 미인식', '\n'.join(result['issues']))
        self.assertIn('1,2', '\n'.join(result['issues']))

    def test_duplicate_or_conflicting_answers_fail(self):
        with patch('naje_pipeline.decode_qr', return_value=None):
            with self.assertRaises(ValueError):
                build_result(self.doc, [self.page(questions=[self.q(), self.q()])], 'hash')
            with self.assertRaises(ValueError):
                build_result(self.doc, [self.page(questions=[self.q()]), self.page(2, 'answers', answers=[{'number':1,'answer':'①'},{'number':1,'answer':'②'}])], 'hash')

    def test_out_of_page_nan_and_inverted_regions_fail(self):
        for coords in ([0,0,1001,500], [500,100,300,400], [0,float('nan'),100,400]):
            with self.assertRaises(ValueError):
                rect(coords, self.doc[0])

    def test_concept_must_not_contain_questions(self):
        with self.assertRaises(ValueError):
            build_result(self.doc, [self.page(kind='concept', questions=[self.q()])], 'hash')

    def test_glyph_touching_model_boundary_is_preserved(self):
        page = self.doc[0]
        page.insert_text((100, 100), 'fraction')
        word = pymupdf.Rect(page.get_text('words')[0][:4])
        proposed = pymupdf.Rect(word.x0, word.y0+3, word.x1-3, word.y1-3)
        self.assertTrue(safe_crop(page, proposed).contains(word))


if __name__ == '__main__':
    unittest.main()
