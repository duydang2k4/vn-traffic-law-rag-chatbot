"""Apply the reviewed block-level concordance to the two supported DOCX pairs."""
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from tempfile import NamedTemporaryFile

from scripts import ROOT
from scripts.pipeline.parse_documents import parse


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


RULES = load(ROOT / 'registry/consolidation_edits.json')


def source_block(doc, position):
    block = dict(doc['blocks'][position - 1])
    block['source'] = {'document_id': doc['document_id'], 'position': position}
    # Hierarchy IDs in either input belong to the source edition.
    block['source']['unit_id'] = block.pop('unit_id', None)
    return block


def payload(amendment, rule):
    first, last = rule['payload']
    result = [source_block(amendment, pos) for pos in range(first, last + 1)]
    if rule['operation'] != 'annex':
        result[0]['text'] = result[0]['text'].lstrip().lstrip('"“')
        result[-1]['text'] = re.sub(r'["”][.;]?\s*$', '', result[-1]['text'].rstrip())
    for block in result:
        block['source']['instruction_positions'] = [rule['instruction']]
    return result


def edit_phrase(blocks, rule):
    first, last = rule['base']
    pattern = r'\s+'.join(re.escape(word) for word in rule['anchor'].split())
    total = 0
    for pos in range(first, last + 1):
        block = blocks[pos]
        original = block['text']
        matches = list(re.finditer(pattern, original, re.I))
        for match in reversed(matches):
            left, right = original[:match.start()], original[match.end():]
            old = match.group()
            value = rule.get('value', '')
            op = rule['operation']
            if op == 'phrase_after':
                value = old + ('' if value.startswith((',', ';')) else ' ') + value
            elif op == 'phrase_before':
                value += ' ' + old
            elif op == 'phrase_drop':
                left = left.rstrip()
                if left and right and not right[0].isspace() and right[0] not in '.,;:':
                    value = ' '
            elif op != 'phrase_replace':
                raise ValueError(op)
            original = left + value + right
        if matches:
            block['text'] = original
            block['source'].setdefault('instruction_positions', []).append(rule['instruction'])
            total += len(matches)
    if total != rule['count'] or not total:
        raise ValueError(f"Unexpected phrase count at {rule['instruction']}, {rule['target']}: {total}")


def consolidate(base, amendment):
    spec = RULES[amendment['document_id']]
    if (base['document_id'], base['sha256'], amendment['sha256']) != (
            spec['base_document'], spec['base_sha256'], spec['amending_sha256']):
        raise ValueError('DOCX version changed; review the block concordance before rebuilding')
    for doc, key in ((base, 'base_blocks_sha256'), (amendment, 'amending_blocks_sha256')):
        encoded = json.dumps(doc['blocks'], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        if hashlib.sha256(encoded.encode('utf-8')).hexdigest() != spec[key]:
            raise ValueError('Parsed blocks changed; review block positions before rebuilding')
    original = {pos: source_block(base, pos) for pos in range(1, len(base['blocks']) + 1)}
    removed = set()
    before, after = defaultdict(list), defaultdict(list)
    actions = []
    for rule in spec['actions']:
        num = rule['instruction']
        op = rule['operation']
        action = dict(rule, instruction_position=num, instruction=amendment['blocks'][num - 1]['text'].strip(),
                      status='external_document' if op == 'external' else 'applied_draft')
        actions.append(action)
        if op == 'external':
            continue
        first, last = rule['base']
        if op.startswith('phrase_'):
            if any(pos in removed for pos in range(first, last + 1)):
                raise ValueError(f'Phrase target already replaced: {num}')
            edit_phrase(original, rule)
        elif op == 'after':
            after[last].extend(payload(amendment, rule))
        elif op == 'before':
            before[first].extend(payload(amendment, rule))
        elif op in ('annex', 'replace', 'repeal'):
            region = set(range(first, last + 1))
            if removed & region:
                raise ValueError(f'Overlapping replacements: {num}')
            removed.update(region)
            if op != 'repeal':
                before[first].extend(payload(amendment, rule))
        else:
            raise ValueError(op)

    result = []
    for pos, block in original.items():
        result.extend(before[pos])
        if pos not in removed:
            result.append(block)
        result.extend(after[pos])
    for pos, block in enumerate(result, 1):
        block['position'] = pos
    start, end = spec['implementation_blocks']
    return {'schema_version': 2, 'status': 'textual_consolidation_draft',
            'notice': 'Bản ghép toàn bộ sửa đổi trong bộ DOCX. Bao gồm quy định có ngày áp dụng riêng. Xem điều khoản thi hành và chuyển tiếp khi tra cứu theo ngày.',
            'base_document': base['document_id'], 'base_sha256': base['sha256'],
            'amending_document': amendment['document_id'], 'amending_sha256': amendment['sha256'],
            'implementation_provisions': [source_block(amendment, i) for i in range(start, end + 1)],
            'actions': actions, 'blocks': result}


def checked_input(doc_id):
    doc = load(ROOT / 'data/processed' / (doc_id + '.json'))
    fresh = parse(ROOT / 'data/raw' / (doc_id + '.docx'))
    if doc != fresh:
        raise ValueError(f'Stale processed document: {doc_id}')
    return doc


def main():
    output = ROOT / 'data/consolidated'
    results = [consolidate(checked_input(spec['base_document']), checked_input(doc_id))
               for doc_id, spec in RULES.items()]
    output.mkdir(exist_ok=True)
    for result in results:
        dest = output / (result['base_document'] + '.json')
        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=output, delete=False) as tmp:
            json.dump(result, tmp, ensure_ascii=False, indent=2)
            tmp.write('\n')
        Path(tmp.name).replace(dest)
        print(f"{dest.name}: {len(result['blocks'])} blocks, {len(result['actions'])} mapped operations")


if __name__ == '__main__':
    main()

