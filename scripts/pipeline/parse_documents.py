"""Extract DOCX body blocks and provisional legal structure using the standard library."""
import hashlib
import json
import re
import zipfile
from xml.etree import ElementTree as ET

from scripts import ROOT

RAW = ROOT / 'data' / 'raw'
OUT = ROOT / 'data' / 'processed'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
PATTERNS = [
    ('chapter', re.compile(r'^Chương\s+([IVXLCDM]+|\d+[a-z]?)\s*[.:]?(?:\s|$)')),
    ('section', re.compile(r'^Mục\s+(\d+[a-z]?)\s*[.:]?(?:\s|$)')),
    ('article', re.compile(r'^Điều\s+(\d+[a-z]?)\s*[.:]')),
    ('clause', re.compile(r'^(\d+[a-z]?)\.\s+')),
    ('point', re.compile(r'^([a-zđ])\)\s*')),
]
LEVELS = [p[0] for p in PATTERNS]


def text_of(element):
    values = []
    for node in element.iter():
        if node.tag == W + 't':
            values.append(node.text or '')
        elif node.tag == W + 'tab':
            values.append('\t')
        elif node.tag in (W + 'br', W + 'cr'):
            values.append('\n')
    return ''.join(values)


def parse(path):
    with zipfile.ZipFile(path) as z:
        names = {n.replace('\\', '/'): n for n in z.namelist()}
        xml = ET.fromstring(z.read(names['word/document.xml']))
        extras = {}
        for part in ('footnotes', 'endnotes'):
            name = f'word/{part}.xml'
            if name in names:
                root = ET.fromstring(z.read(names[name]))
                extras[part] = [{'id': n.get(W + 'id'), 'text': text_of(n)} for n in root]
        media = [n for n in names if n.startswith('word/media/')]
    context = dict.fromkeys(LEVELS)
    blocks, units = [], []
    for el in xml.find(W + 'body'):
        if el.tag not in (W + 'p', W + 'tbl'):
            continue
        position = len(blocks) + 1
        is_table = el.tag == W + 'tbl'
        if is_table:
            rows = [[text_of(c) for c in row.findall(W + 'tc')] for row in el.findall(W + 'tr')]
            content = '\n'.join('\t'.join(row) for row in rows)
        else:
            rows = None
            content = text_of(el)
            for level, pattern in PATTERNS:
                if level == 'clause' and not context['article']:
                    continue
                if level == 'point' and not context['clause']:
                    continue
                match = pattern.match(content.strip())
                if not match:
                    continue
                idx = LEVELS.index(level)
                for child in LEVELS[idx + 1:]:
                    context[child] = None
                parent = next((context[x] for x in reversed(LEVELS[:idx]) if context[x]), None)
                uid = f'{path.stem}:{level}:{position:06d}'
                context[level] = uid
                units.append(dict(id=uid, type=level, number=match.group(1), parent_id=parent,
                                  heading=content, source_block=position))
                break
        block = dict(position=position, type='table' if is_table else 'paragraph', text=content,
                     unit_id=next((context[x] for x in reversed(LEVELS) if context[x]), None),
                     automatic_numbering=el.find('./' + W + 'pPr/' + W + 'numPr') is not None)
        if rows is not None:
            block['rows'] = rows
        blocks.append(block)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(document_id=path.stem, source_file=path.name, sha256=digest,
                source_location='word/document.xml; body block index (1-based)', units=units,
                blocks=blocks, notes=extras, media_parts=media,
                caveats=['Cấu trúc phân cấp được nhận dạng theo mẫu; cần kiểm tra thủ công, đặc biệt trong văn bản sửa đổi và phụ lục.',
                         'Số tự động và bố cục, ô gộp, hình ảnh chưa được khôi phục đầy đủ.'])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    for path in sorted(RAW.glob('*.docx')):
        doc = parse(path)
        (OUT / (path.stem + '.json')).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
        report.append(dict(file=path.name, blocks=len(doc['blocks']),
                           tables=sum(b['type'] == 'table' for b in doc['blocks']),
                           automatic_numbering_paragraphs=sum(b['automatic_numbering'] for b in doc['blocks']),
                           units=len(doc['units']), articles=sum(u['type'] == 'article' for u in doc['units']),
                           source_sha256=doc['sha256']))
    (OUT / 'inventory.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Parsed {len(report)} DOCX files')


if __name__ == '__main__':
    main()
