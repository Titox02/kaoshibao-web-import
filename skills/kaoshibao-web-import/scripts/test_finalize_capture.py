import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from finalize_capture import validate_capture
from import_bank import build


def signed(row):
    fields=[row['bankTitle'],row['number'],row['total'],row.get('id') or '',row['question'],row['options'],row['answer'],row['analysis'],row.get('qtype'),row.get('analysisMissing')]
    row['fingerprint']=hashlib.sha256(json.dumps(fields,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return row


def fixture():
    return {'name':'测试题库','expectedCount':2,'questions':[signed({'bankTitle':'测试题库','number':n,'total':2,'id':str(n),'question':'题干'+str(n),'options':[{'Key':'A','Value':'一'},{'Key':'B','Value':'二'}],'qtype':'1','answer':'A','analysis':'原解析'+str(n),'analysisMissing':False,'quality':'stable-visible-dom'}) for n in (1,2)]}


class CaptureTests(unittest.TestCase):
    def test_complete_capture_flows_into_practice_site(self):
        data=fixture();self.assertTrue(validate_capture(data)['countComplete'])
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);source=p/'capture.json';source.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            result=build([source],p/'practice',2)
            self.assertEqual(result['questions'],2)
            self.assertIn('原解析1',(p/'practice/questions.json').read_text())
            self.assertTrue((p/'practice/index.html').is_file())

    def test_partial_capture_needs_explicit_flag(self):
        data=fixture();data['questions'].pop()
        with self.assertRaises(ValueError):validate_capture(data)
        self.assertFalse(validate_capture(data,True)['countComplete'])

    def test_gaps_mixed_titles_tampering_and_missing_answers_fail(self):
        for field,value in [('number',4),('bankTitle','另一库'),('analysis','篡改'),('answer','')]:
            data=fixture();data['questions'][1][field]=value
            with self.assertRaises(ValueError):validate_capture(data)

    def test_missing_original_analysis_is_preserved_only_when_marked(self):
        data=fixture();r=data['questions'][0];r['analysis']='';signed(r)
        with self.assertRaises(ValueError):validate_capture(data)
        r['analysisMissing']=True;signed(r)
        self.assertEqual(validate_capture(data)['missingOriginalAnalysis'],1)


if __name__=='__main__':unittest.main()
