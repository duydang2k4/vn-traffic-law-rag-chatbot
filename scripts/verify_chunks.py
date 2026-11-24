"""Verify chunk files against the independently loaded parsed source blocks."""
from chunk_documents import ROOT, read


def main():
    registry = read(ROOT / 'registry/document_registry.json')
    count = 0
    for entry in registry['documents']:
        source = read(ROOT / 'data/processed' / (entry['id'] + '.json'))
        result = read(ROOT / 'data/chunks' / (entry['id'] + '.json'))
        assert result['source_sha256'] == source['sha256'] == entry['sha256']
        chunks = result['chunks']
        assert [b for c in chunks for b in c['blocks']] == source['blocks'], entry['id']
        assert len({c['id'] for c in chunks}) == len(chunks)
        for chunk in chunks:
            assert chunk['blocks'] and chunk['document_id'] == entry['id']
            assert chunk['effective']['status'] == 'unverified'
            assert chunk['effective']['valid_from'] is None
            assert chunk['effective']['valid_until_exclusive'] is None
        count += len(chunks)
    print(f'OK: {len(registry["documents"])} documents, {count} chunks, exact ordered block coverage')


if __name__ == '__main__':
    main()
