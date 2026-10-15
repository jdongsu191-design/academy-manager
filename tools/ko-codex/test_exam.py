import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf
from exam_pipeline import extract_exam, validate_request, validate_items


def item(**changes):
    return dict(dict(order=1, number_label='객관식1', score=100, is_essay=False,
                     unit='방정식', difficulty=1, type_description='일차방정식 풀이'), **changes)


class ExamTests(unittest.TestCase):
    def test_input_and_result_validation(self):
        for request in [{}, {'operation':'shell','prompt':'x'}, {'operation':'analysis','prompt':'x','units':['a'],'pdf':'no'}]:
            with self.assertRaises(ValueError): validate_request(request)
        validate_items([item()], ['방정식'])
        for items in [[item(), item()], [item(score=float('nan'))], [item(difficulty=4)], [item(unit='임의 단원')], [item(order=2)]]:
            with self.assertRaises(ValueError): validate_items(items, ['방정식'])

    def test_inventory_is_independent_and_retained_for_review(self):
        with pymupdf.open() as doc:
            doc.new_page().insert_text((40, 40), '1. Solve x + 1 = 2. [100 points]')
            pdf = doc.tobytes()
        request = dict(operation='analysis', prompt='문항 분석', units=['방정식'], pdf=base64.b64encode(pdf).decode())
        audit = dict(questions=[dict(number_label='객관식1', page=1, score=90)], issues=['배점 확인'])
        with tempfile.TemporaryDirectory() as folder, patch('exam_pipeline.ask', side_effect=[audit, {'items':[item()]}]) as ask:
            result = extract_exam(request, Path(folder), 'codex', lambda _: None)
            self.assertEqual(ask.call_count, 2)
            self.assertNotIn('90', ask.call_args_list[1].args[3])
            self.assertEqual(result['output']['audit'], audit)
            self.assertEqual(result['output']['items'][0]['score'], 100)

    def test_summary_does_not_require_original_pdf(self):
        with tempfile.TemporaryDirectory() as folder, patch('exam_pipeline.ask', return_value=dict(difficulty='쉬움', discrimination='문항1', strategy='복습')) as ask:
            result = extract_exam(dict(operation='summary',prompt='검수표'),Path(folder),'codex',lambda _:None)
            self.assertEqual(result['operation'],'summary')
            self.assertEqual(ask.call_args.args[-1], [])


if __name__ == '__main__': unittest.main()
