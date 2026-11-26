import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from import_bank import build, ImportErrorDetail


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.q = {'id':'original-1','qtype':'1','question':'题干','options':[{'Key':'A','Value':'一'},{'Key':'B','Value':'二'}],'answer':'B','analysis':'原解析\n保留第二行'}

    def source(self, data, name='bank.json'):
        path=self.root/name
        path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        return path

    def test_originals_and_namespaces_survive_without_guessing(self):
        a=self.source({'questions':[self.q],'complete':False})
        b=self.source([dict(self.q,answer='未知',analysis='')],'english.json')
        out=self.root/'out';result=build([a,b],out,2)
        bank=json.loads((out/'questions.json').read_text())
        self.assertEqual(result['questions'],2)
        self.assertEqual(result['warnings'],1)
        self.assertEqual(result['manual'],1)
        self.assertEqual(bank['questions'][0]['original'],self.q)
        self.assertEqual(bank['questions'][1]['answer'],'未知')
        self.assertNotEqual(bank['questions'][0]['key'],bank['questions'][1]['key'])
        with self.assertRaises(ImportErrorDetail):build([a],out)

    def test_html_is_inert_and_only_explicit_local_images_are_copied(self):
        image=self.root/'image.png';image.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        q=dict(self.q,question='<script>alert(1)</script><img src="image.png" onerror="evil()"><img src="https://example.org/missing.png"><img src="../outside.png"><math><mi>x</mi></math><a href="javascript:evil()">题干</a>')
        source=self.source([q]);out=self.root/'out';result=build([source],out)
        bank=json.loads((out/'questions.json').read_text());stem=bank['questions'][0]['stem']
        self.assertNotIn('<script',stem);self.assertNotIn('onerror',stem);self.assertNotIn('javascript:',stem)
        self.assertIn('<math>',stem);self.assertEqual(result['missingImages'],2)
        self.assertEqual(len(list((out/'assets').glob('*.png'))),1)
        self.assertNotIn('alert(1)',(out/'index.html').read_text())
        self.assertEqual(bank['questions'][0]['original'],q)

    def test_count_and_id_conflicts_fail_without_partial_output(self):
        source=self.source([self.q]);out=self.root/'out'
        with self.assertRaises(ImportErrorDetail):build([source],out,2)
        self.assertFalse(out.exists())
        source=self.source([self.q,self.q])
        with self.assertRaises(ImportErrorDetail):build([source],out)
        self.assertFalse(out.exists())
        self.assertEqual(list(self.root.glob('.quiz-import-*')),[])

    def test_csv_multiline_and_empty_ids_are_preserved(self):
        source=self.root/'input.csv'
        with source.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['id','question','A','B','answer','type','analysis'])
            writer.writeheader()
            for question in ('第一题\n第二行','第二题'):
                writer.writerow({'id':'','question':question,'A':'一','B':'二','answer':'B','type':'single','analysis':'原解析\n下一行'})
        out=self.root/'out';build([source],out,2)
        bank=json.loads((out/'questions.json').read_text())
        self.assertEqual(bank['questions'][0]['original']['question'],'第一题\n第二行')
        self.assertEqual(bank['questions'][0]['original']['analysis'],'原解析\n下一行')
        other=self.root/'other';build([source],other)
        self.assertEqual(bank['id'],json.loads((other/'questions.json').read_text())['id'])

    def test_javascript_is_never_executed(self):
        source=self.root/'bank.js';source.write_text('window.CAPM_BANK='+json.dumps({'questions':{'zh-1':self.q}})+';')
        build([source],self.root/'out',1)
        source.write_text('window.CAPM_BANK={};alert(1)')
        with self.assertRaises(ImportErrorDetail):build([source],self.root/'bad')
        self.assertFalse((self.root/'bad').exists())


if __name__=='__main__':unittest.main()
