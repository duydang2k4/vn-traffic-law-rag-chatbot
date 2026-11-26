"""Split the provisional parse into ordered, lossless article/clause chunks."""
import json

from scripts import ROOT



def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    registry = read(ROOT / 'registry/document_registry.json')
    output = ROOT / 'data/chunks'
    output.mkdir(parents=True, exist_ok=True)
    total = 0
    for entry in registry['documents']:
        doc = read(ROOT / 'data/processed' / (entry['id'] + '.json'))
        if doc['sha256'] != entry['sha256']:
            raise ValueError('Stale input: ' + entry['id'])
        units = {u['id']: u for u in doc['units']}

        def ancestry(unit_id):
            result, seen = [], set()
            while unit_id:
                if unit_id in seen or unit_id not in units:
                    raise ValueError('Invalid hierarchy: ' + unit_id)
                seen.add(unit_id)
                unit = units[unit_id]
                result.insert(0, unit)
                unit_id = unit['parent_id']
            return result

        chunks = []
        for block in doc['blocks']:
            parents = ancestry(block['unit_id'])
            article = next((u for u in parents if u['type'] == 'article'), None)
            clause = next((u for u in parents if u['type'] == 'clause'), None)
            key = (clause or article or {}).get('id', 'unstructured')
            if not chunks or chunks[-1]['group_key'] != key:
                def descriptor(unit):
                    return {k: unit[k] for k in ('id', 'number', 'heading')} if unit else None

                chunks.append({
                    'id': f"{entry['id']}:chunk:{len(chunks) + 1:06d}",
                    'group_key': key, 'document_id': entry['id'],
                    'document_number': entry['number'], 'document_title': entry['title'],
                    'source_sha256': doc['sha256'], 'article': descriptor(article),
                    'clause': descriptor(clause),
                    'parent_context': [{k: u[k] for k in ('id', 'type', 'number', 'heading')}
                                       for u in parents if u['type'] in ('chapter', 'section', 'article')],
                    'effective': {'valid_from': None, 'valid_until_exclusive': None,
                                  'status': 'unverified', 'document_effective_date': entry['effective_date']},
                    'classification': 'provisional_article_or_clause' if article else 'unstructured',
                    'blocks': [],
                })
            chunks[-1]['blocks'].append(block)
        if [b for c in chunks for b in c['blocks']] != doc['blocks']:
            raise ValueError('Coverage mismatch: ' + entry['id'])
        result = {'schema_version': 1, 'document_id': entry['id'], 'source_sha256': doc['sha256'],
                  'caveats': ['Phân cấp kế thừa bước 1, chưa xác minh; văn bản sửa đổi có thể nhận nhầm đoạn trích và phụ lục.',
                              'Hiệu lực từng quy định chưa được xác minh; ngày hiệu lực văn bản chỉ để tham khảo.',
                              'Ngữ cảnh cha là metadata, không thuộc danh sách khối nội dung.'], 'chunks': chunks}
        (output / (entry['id'] + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        total += len(chunks)
    print(f'OK: {len(registry["documents"])} documents, {total} chunks; all source blocks preserved in order')


if __name__ == '__main__':
    main()
