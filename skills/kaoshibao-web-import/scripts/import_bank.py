#!/usr/bin/env python3
"""Local-only question import; stdout is a bounded JSON summary."""
import argparse
import csv
import hashlib
import html
import io
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import unquote, urlsplit


class ImportErrorDetail(ValueError):
    pass


def serialized(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def load(path):
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() == '.csv':
        return list(csv.DictReader(io.StringIO(text))), {}
    if path.suffix.lower() in ('.jsonl', '.ndjson'):
        rows = []
        for number, line in enumerate(text.splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    raise ImportErrorDetail(f'{path.name}: JSONL 第 {number} 行格式错误')
        return rows, {}
    if path.suffix.lower() == '.js':
        match = re.fullmatch(r'\s*window\.CAPM_BANK\s*=\s*(\{.*\})\s*;?\s*', text, re.S)
        if not match:
            raise ImportErrorDetail('只支持固定 JSON 包装的 CAPM bank.js，不执行 JavaScript')
        text = match.group(1)
    data = json.loads(text)
    meta = data if isinstance(data, dict) else {}
    rows = meta.get('questions') if meta else data
    if isinstance(rows, dict):
        rows = [dict(value, key=key) for key, value in rows.items()]
    if not isinstance(rows, list):
        raise ImportErrorDetail(f'{path.name}: 需要题目数组或 questions 字段')
    return rows, meta


def choose(record, *names, default=''):
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return default


def option_list(record):
    options = record.get('options')
    if isinstance(options, str):
        options = json.loads(options) if options.strip() else []
    if options is None:
        options = {k: record[k] for k in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if record.get(k)}
    if isinstance(options, dict):
        options = [{'key': k, 'html': v} for k, v in options.items()]
    if not isinstance(options, list):
        raise ImportErrorDetail('options 应为 JSON 列表或字典')
    result = []
    for i, value in enumerate(options):
        if isinstance(value, str):
            if i >= 26:
                raise ImportErrorDetail('无字母选项超过 26 个')
            key, content = chr(65+i), value
        elif isinstance(value, dict):
            key = str(choose(value, 'key', 'Key')).strip()
            content = choose(value, 'html', 'Value', 'value', 'text')
        else:
            raise ImportErrorDetail('选项必须是字符串或对象')
        if not re.fullmatch('[A-Z]', key) or not isinstance(content, str):
            raise ImportErrorDetail('选项需原始 A-Z 字母及文本内容')
        result.append({'key': key, 'html': content})
    return result


class Cleaner(HTMLParser):
    tags = set('div p br span b strong em i u sub sup table thead tbody tr th td ul ol li math mrow mi mn mo mtext msub msup msubsup mfrac msqrt mroot mfenced mover munder munderover mtable mtr mtd mspace mstyle mpadded mphantom menclose semantics'.split())
    attributes = set('display mathvariant stretchy fence separator accent accentunder linethickness columnalign rowalign columnspacing rowspacing notation height width depth lspace rspace scriptlevel displaystyle open close separators'.split())
    blocked = {'script', 'style', 'iframe', 'object', 'svg', 'annotation', 'annotation-xml'}

    def __init__(self, image):
        super().__init__(convert_charrefs=True)
        self.parts, self.plain, self.skip = [], [], []
        self.image = image

    def handle_starttag(self, tag, attrs):
        if tag in self.blocked:
            self.skip.append(tag)
            return
        if self.skip:
            return
        attrs = dict(attrs)
        if tag == 'img':
            source = self.image(attrs.get('src', ''))
            self.parts.append(f'<img src="{html.escape(source, quote=True)}" alt="题库原图">' if source else '<span>[图片未保存]</span>')
            self.plain.append('[图片]')
        elif tag in self.tags:
            safe = ''.join(f' {k}="{html.escape(v or "", quote=True)}"' for k,v in attrs.items() if k in self.attributes and len(v or '') < 150)
            self.parts.append(f'<{tag}{safe}>')
            if tag in ('br','p','div','tr','li'):
                self.plain.append(' ')

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.pop()
            return
        if tag in self.tags and tag != 'br':
            self.parts.append(f'</{tag}>')

    def handle_data(self, value):
        if not self.skip:
            self.parts.append(html.escape(value))
            self.plain.append(value)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag != 'img' and tag != 'br':
            self.handle_endtag(tag)


def build(inputs, output, expected=None, media_map=None):
    output = output.expanduser().resolve()
    if output.exists():
        raise ImportErrorDetail('输出目录已存在，请使用新目录以保留旧库和进度')
    output.parent.mkdir(parents=True, exist_ok=True)
    mapping, map_parent = {}, None
    if media_map:
        media_map = media_map.expanduser().resolve()
        mapping = json.loads(media_map.read_text(encoding='utf-8-sig'))
        if not isinstance(mapping, dict):
            raise ImportErrorDetail('图片映射应为 JSON 对象')
        map_parent = media_map.parent
    stage = Path(tempfile.mkdtemp(prefix='.quiz-import-', dir=output.parent))
    report = {'sources': [], 'warnings': [], 'missingImages': [], 'manual': [], 'emptyAnalysis': [], 'copiedImages': 0}
    questions, hashes = [], set()
    try:
        for file_number, path in enumerate(inputs, 1):
            path = path.expanduser().resolve()
            rows, meta = load(path)
            if not rows:
                raise ImportErrorDetail(f'{path.name}: 空题库')
            declared = choose(meta, 'expectedCount', 'exportedCount', default=None)
            if meta.get('complete') is False or (declared is not None and int(declared) != len(rows)):
                report['warnings'].append({'source': path.name, 'issue': '来源标记不完整或题数不符', 'loaded': len(rows), 'expected': declared})
            seen = set()
            report['sources'].append({'file': path.name, 'questions': len(rows)})
            for ordinal, record in enumerate(rows, 1):
                location = f'{path.name}:{ordinal}'
                if not isinstance(record, dict):
                    raise ImportErrorDetail(f'{location}: 题目应为对象')
                source_id = str(next((record[k] for k in ('key', 'id') if record.get(k) not in (None, '')), f'row-{ordinal}'))
                if source_id in seen:
                    raise ImportErrorDetail(f'{location}: 同一来源 ID 重复，停止以避免丢题')
                seen.add(source_id)

                def image(source):
                    candidate = None
                    if source in mapping:
                        value = mapping[source]
                        name = value.get('path') if isinstance(value, dict) else value
                        if isinstance(name, str):
                            candidate = Path(name).expanduser()
                            if not candidate.is_absolute():
                                candidate = map_parent / candidate
                            if not candidate.is_file() and isinstance(value, dict) and value.get('assetName'):
                                candidate = map_parent / 'images' / Path(value['assetName']).name
                    else:
                        parsed = urlsplit(source)
                        if not parsed.scheme and not parsed.netloc and source:
                            local = (path.parent / unquote(parsed.path)).resolve()
                            if local.is_relative_to(path.parent):
                                candidate = local
                    if candidate and candidate.is_file():
                        data = candidate.read_bytes()
                        suffix = '.png' if data.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg' if data.startswith(b'\xff\xd8\xff') else '.gif' if data.startswith((b'GIF87a', b'GIF89a')) else '.webp' if data.startswith(b'RIFF') and data[8:12] == b'WEBP' else None
                        if suffix and len(data) <= 25*1024*1024:
                            digest = hashlib.sha256(data).hexdigest()
                            relative = f'assets/{digest}{suffix}'
                            (stage/'assets').mkdir(exist_ok=True)
                            (stage/relative).write_bytes(data)
                            hashes.add(digest)
                            return relative
                    report['missingImages'].append({'location': location, 'source': source})
                    return None

                def clean(value):
                    parser = Cleaner(image)
                    parser.feed(str(value or ''))
                    parser.close()
                    return ''.join(parser.parts), ''.join(parser.plain).strip()

                stem, plain = clean(choose(record, 'question', 'stem', 'questionHtml'))
                if not plain and '<img ' not in stem:
                    raise ImportErrorDetail(f'{location}: 题干为空')
                try:
                    options = option_list(record)
                except (ValueError, TypeError) as error:
                    raise ImportErrorDetail(f'{location}: {error}')
                for option in options:
                    option['html'], _ = clean(option['html'])
                answer_raw = choose(record, 'answer', 'answerKeys', 'answerHtml')
                answer = ''.join(str(x) for x in answer_raw) if isinstance(answer_raw,list) else str(answer_raw)
                answer_html, answer_text = clean(answer)
                compact = re.sub(r'[\s,，、;；]+', '', answer_text)
                answer_keys = sorted(set(compact)) if re.fullmatch('[A-Z]+',compact) else []
                qtype = str(choose(record, 'qtype', 'type'))
                kind = 'single' if qtype in ('1','single','单选题') else 'multiple' if qtype in ('2','multiple','多选题') else 'manual'
                keys = [o['key'] for o in options]
                option_texts = [re.sub(r'<[^>]*>', '', o['html']).strip() for o in options]
                manual = str(record.get('manualReason') or '')
                if kind == 'manual' or not answer_keys or not set(answer_keys) <= set(keys) or len(keys) != len(set(keys)) or len(option_texts) != len(set(option_texts)) or len(keys) < 2 or (kind == 'single' and len(answer_keys) != 1):
                    manual = manual or '题型、选项或原答案需要自行核对'
                if manual:
                    report['manual'].append(location)
                if not answer_text and '<img ' not in answer_html:
                    report['warnings'].append({'location': location, 'issue': '原答案缺失'})
                analysis, analysis_plain = clean(choose(record, 'analysis', 'explanation', 'analysisHtml'))
                if not analysis_plain and '<img ' not in analysis:
                    report['emptyAnalysis'].append(location)
                ai = record.get('ai')
                ai = ai.get('text','') if isinstance(ai,dict) else ai if isinstance(ai,str) else ''
                questions.append({'key': f's{file_number}:{source_id}', 'source': path.name, 'sourceId': source_id,
                    'number': choose(record,'number',default=ordinal), 'language': choose(record,'language','lang'),
                    'stem':stem, 'options':options, 'answer':answer_html, 'answerKeys':answer_keys,
                    'type':kind, 'analysis':analysis, 'ai':ai, 'manualReason':manual, 'original':record})
        if expected is not None and len(questions) != expected:
            raise ImportErrorDetail(f'预期 {expected} 题，实际 {len(questions)}；未写入输出，请核对来源')
        bank = {'version':1, 'questions':questions}
        bank['id'] = 'import-' + hashlib.sha256(serialized(bank).encode()).hexdigest()[:20]
        report.update({'questions':len(questions),'copiedImages':len(hashes),'bankId':bank['id']})
        (stage/'questions.json').write_text(serialized(bank),encoding='utf-8')
        (stage/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        # The HTML contains only sanitized display fields, never executable source-record HTML.
        display = {**bank,'questions':[{k:v for k,v in q.items() if k!='original'} for q in questions]}
        payload = serialized(display).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
        template = (Path(__file__).resolve().parents[1]/'assets/viewer.html').read_text(encoding='utf-8')
        (stage/'index.html').write_text(template.replace('__QUIZ_DATA__',payload),encoding='utf-8')
        stage.rename(output)
        return {'ok':True,'questions':len(questions),'manual':len(report['manual']),'missingImages':len(report['missingImages']),
                'emptyAnalysis':len(report['emptyAnalysis']),'warnings':len(report['warnings']),'output':str(output)}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs',nargs='+',type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--expected',type=int)
    parser.add_argument('--media-map',type=Path)
    args = parser.parse_args()
    try:
        summary = build(args.inputs,args.out,args.expected,args.media_map)
        print(serialized(summary))
    except (ValueError,OSError,TypeError,KeyError) as error:
        print(serialized({'ok':False,'error':str(error)[:400]}),file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
