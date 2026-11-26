#!/usr/bin/env python3
"""Validate a visible-DOM capture before making a portable practice site."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from import_bank import build, serialized


def validate_capture(data, allow_partial=False):
    if not isinstance(data, dict) or not isinstance(data.get('questions'),list):
        raise ValueError('需要扩展导出的 capture.json，不能直接使用网页源码')
    expected=data.get('expectedCount')
    rows=data['questions']
    if type(expected) is not int or expected<1 or not rows:
        raise ValueError('题库总数无效或没有题目')
    if 'exportedCount' in data and data['exportedCount']!=len(rows):
        raise ValueError('导出条数元信息与实际题数不一致')
    if 'complete' in data and data['complete']!=(len(rows)==expected):
        raise ValueError('完整标记与实际题数不一致')
    seen=set()
    title=None
    for n,r in enumerate(rows,1):
        if not isinstance(r,dict) or r.get('number')!=n or r.get('total')!=expected:
            raise ValueError(f'第 {n} 条题号/总数错位或有缺题')
        if not isinstance(r.get('bankTitle'),str) or not r['bankTitle'].strip():
            raise ValueError(f'第 {n} 条缺少页面题库标题')
        title=title or r['bankTitle']
        if r['bankTitle']!=title:
            raise ValueError(f'第 {n} 条混入另一份题库')
        if not r.get('question') or not isinstance(r.get('answer'),str) or not r['answer'].strip():
            raise ValueError(f'第 {n} 条题干或正确答案缺失')
        if not isinstance(r.get('analysis'),str) or (not r['analysis'].strip() and r.get('analysisMissing') is not True):
            raise ValueError(f'第 {n} 条原解析未完成读取')
        if r.get('quality')!='stable-visible-dom' or not isinstance(r.get('fingerprint'),str) or len(r['fingerprint'])!=64:
            raise ValueError(f'第 {n} 条缺少稳定读取记录')
        canonical=[r['bankTitle'],r['number'],r['total'],r.get('id') or '',r['question'],r['options'],r['answer'],r['analysis'],r.get('qtype'),r.get('analysisMissing')]
        fingerprint=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        if fingerprint!=r['fingerprint']:
            raise ValueError(f'第 {n} 条内容指纹不符，未导入')
        identifier=str(r.get('id') or n)
        if identifier in seen:
            raise ValueError(f'第 {n} 条原始 ID 重复，不自动丢题')
        seen.add(identifier)
        if not isinstance(r.get('options'),list):
            raise ValueError(f'第 {n} 条选项缺失')
        keys=[o.get('Key') for o in r['options'] if isinstance(o,dict)]
        if len(keys)!=len(r['options']) or len(keys)!=len(set(keys)):
            raise ValueError(f'第 {n} 条选项字母重复或格式错误')
        if r.get('qtype') in ('1','2') and (not r['answer'].isalpha() or not r['answer'].isascii() or not set(r['answer'])<=set(keys) or (r['qtype']=='1' and len(r['answer'])!=1)):
            raise ValueError(f'第 {n} 条正确答案与原选项不一致')
    if len(rows)!=expected and not allow_partial:
        raise ValueError(f'只有 {len(rows)}/{expected} 题；未导入。续采或显式使用 --allow-partial 保存不完整预览')
    return {'questions':len(rows),'expected':expected,'countComplete':len(rows)==expected,
            'missingOriginalAnalysis':sum(not r['analysis'].strip() for r in rows),
            'verification':'DOM 稳定性记录，仍需人工抽查；不代表原答案学术校订'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--media-map',type=Path)
    parser.add_argument('--allow-partial',action='store_true')
    args=parser.parse_args()
    try:
        data=json.loads(args.capture.read_text(encoding='utf-8-sig'))
        report=validate_capture(data,args.allow_partial)
        result=build([args.capture],args.out,None if args.allow_partial else report['expected'],args.media_map)
        (args.out/'capture-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(serialized({**result,**report}))
        return 0
    except (ValueError,OSError,TypeError,KeyError) as error:
        print(serialized({'ok':False,'error':str(error)[:400]}),file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
