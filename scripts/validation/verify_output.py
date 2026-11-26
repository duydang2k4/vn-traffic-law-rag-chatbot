"""Check source hashes, block coverage, and structural references."""
import hashlib
import json

from scripts import ROOT
from scripts.pipeline.parse_documents import RAW, OUT, parse


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    registry = read(ROOT / 'registry/document_registry.json')
    files = sorted(RAW.glob('*.docx'))
    assert {d['id'] for d in registry['documents']} == {p.stem for p in files}
    for entry in registry['documents']:
        path = ROOT / entry['raw_file']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == entry['sha256'], entry['id']
        doc = read(OUT / (entry['id'] + '.json'))
        assert doc['sha256'] == digest
        fresh = parse(path)
        assert doc['blocks'] == fresh['blocks'], entry['id']
        ids = {u['id'] for u in doc['units']}
        assert len(ids) == len(doc['units'])
        assert any(u['type'] == 'article' for u in doc['units'])
        assert all(not u['parent_id'] or u['parent_id'] in ids for u in doc['units'])
        assert all(not b['unit_id'] or b['unit_id'] in ids for b in doc['blocks'])
    print(f'OK: {len(files)} files, hashes, source blocks and references')


if __name__ == '__main__':
    main()
